"""Cálculos del tablero (equivalente a la hoja Resumen_Socios de la planilla)."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.money import ZERO, dsum, money, to_decimal
from app.models import Partner, Payment, Sale, Settlement


@dataclass
class PartnerSummary:
    partner_id: int
    name: str
    pct_share: Decimal
    should_contribute: Decimal = ZERO  # le correspondía aportar
    did_contribute: Decimal = ZERO  # aportó realmente
    profit_share: Decimal = ZERO  # le corresponde de la ganancia
    settled_out: Decimal = ZERO  # le transfirió al otro socio (devoluciones que hizo)
    settled_in: Decimal = ZERO  # el otro socio le transfirió (devoluciones que recibió)

    @property
    def balance(self) -> Decimal:
        """aportó - correspondía. Positivo => puso de más, el otro le debe."""
        return money(self.did_contribute - self.should_contribute)

    @property
    def net_balance(self) -> Decimal:
        """Saldo después de contar las devoluciones entre socios.

        Positivo => todavía le deben esa plata. Negativo => todavía debe esa plata.
        """
        return money(self.balance + self.settled_out - self.settled_in)


@dataclass
class Summary:
    date_from: dt.date | None
    date_to: dt.date | None
    partners: list[PartnerSummary] = field(default_factory=list)

    total_payments_ars: Decimal = ZERO
    total_payments_usd: Decimal = ZERO
    total_contributions_ars: Decimal = ZERO
    total_sales_ars: Decimal = ZERO
    net_result_ars: Decimal = ZERO
    total_settlements_ars: Decimal = ZERO

    payments_count: int = 0
    settlements_count: int = 0
    mismatched_payments: list[Payment] = field(default_factory=list)

    @property
    def control_ok(self) -> bool:
        return abs(self.total_payments_ars - self.total_contributions_ars) <= Decimal("0.01")

    @property
    def control_difference(self) -> Decimal:
        return money(self.total_payments_ars - self.total_contributions_ars)


def _between(column, date_from, date_to):
    conds = []
    if date_from:
        conds.append(column >= date_from)
    if date_to:
        conds.append(column <= date_to)
    return conds


def build_summary(
    db: Session,
    *,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
) -> Summary:
    partners = list(db.scalars(select(Partner).order_by(Partner.id)))
    summary = Summary(date_from=date_from, date_to=date_to)
    per_partner = {
        p.id: PartnerSummary(
            partner_id=p.id,
            name=p.name,
            pct_share=to_decimal(p.pct_share, Decimal("0.01")),
        )
        for p in partners
    }

    pay_stmt = (
        select(Payment)
        .options(selectinload(Payment.contributions))
        .where(*_between(Payment.date, date_from, date_to))
        .order_by(Payment.date, Payment.id)
    )
    payments = list(db.scalars(pay_stmt))

    for pay in payments:
        summary.payments_count += 1
        summary.total_payments_ars = money(summary.total_payments_ars + pay.amount_ars)
        summary.total_payments_usd = money(summary.total_payments_usd + pay.amount_usd)
        contributed = pay.contributed_total
        summary.total_contributions_ars = money(summary.total_contributions_ars + contributed)
        if not pay.control_ok:
            summary.mismatched_payments.append(pay)

        for ps in per_partner.values():
            ps.should_contribute = money(
                ps.should_contribute + pay.amount_ars * ps.pct_share / Decimal(100)
            )
        for c in pay.contributions:
            if c.partner_id in per_partner:
                per_partner[c.partner_id].did_contribute = money(
                    per_partner[c.partner_id].did_contribute + c.amount_ars
                )

    sales_stmt = (
        select(Sale)
        .options(selectinload(Sale.items))
        .where(*_between(Sale.date, date_from, date_to))
    )
    sales = list(db.scalars(sales_stmt))
    summary.total_sales_ars = dsum(s.total_ars for s in sales)

    summary.net_result_ars = money(summary.total_sales_ars - summary.total_payments_ars)
    for ps in per_partner.values():
        ps.profit_share = money(summary.net_result_ars * ps.pct_share / Decimal(100))

    settlements = list(
        db.scalars(select(Settlement).where(*_between(Settlement.date, date_from, date_to)))
    )
    for s in settlements:
        summary.settlements_count += 1
        summary.total_settlements_ars = money(summary.total_settlements_ars + s.amount_ars)
        if s.from_partner_id in per_partner:
            per_partner[s.from_partner_id].settled_out = money(
                per_partner[s.from_partner_id].settled_out + s.amount_ars
            )
        if s.to_partner_id in per_partner:
            per_partner[s.to_partner_id].settled_in = money(
                per_partner[s.to_partner_id].settled_in + s.amount_ars
            )

    summary.partners = list(per_partner.values())
    return summary
