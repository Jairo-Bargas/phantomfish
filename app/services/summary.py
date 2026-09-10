"""Cálculos del tablero (equivalente a la hoja Resumen_Socios de la planilla)."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.money import CENT, ZERO, dsum, money, to_decimal
from app.models import Partner, Payment, Sale


@dataclass
class PartnerSummary:
    partner_id: int
    name: str
    pct_share: Decimal
    should_contribute: Decimal = ZERO  # le correspondía aportar
    did_contribute: Decimal = ZERO  # aportó realmente
    profit_share: Decimal = ZERO  # le corresponde de la ganancia

    @property
    def balance(self) -> Decimal:
        """aportó - correspondía en los pagos del período. Solo informativo."""
        return money(self.did_contribute - self.should_contribute)


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

    payments_count: int = 0
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

    # Los gastos personales de un socio (ej. su combustible) no son costo del
    # negocio ni entran en el reparto 35/65.
    pay_stmt = (
        select(Payment)
        .options(selectinload(Payment.contributions))
        .where(
            Payment.expense_type != "personal",
            *_between(Payment.date, date_from, date_to),
        )
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

    summary.partners = list(per_partner.values())
    return summary


@dataclass
class SociosSaldo:
    """Deuda real neteada entre los dos socios, por moneda (sin conversión).

    ars  = aportes netos de pagos compartidos + pasadas Colón en pesos.
    uyu  = pasadas Colón en pesos uruguayos.
    Para cada moneda, `deudor` le debe `monto` a `acreedor` (None si están a mano).
    """

    socio_a: str = ""   # el de menor id (el que en "aportes" tiene balance + si le deben)
    socio_b: str = ""
    aportes_ars: Decimal = ZERO
    pase_ars: Decimal = ZERO
    pase_uyu: Decimal = ZERO
    net_ars: Decimal = ZERO   # + => B le debe a A
    net_uyu: Decimal = ZERO

    def _dir(self, net: Decimal) -> dict | None:
        if net > Decimal("0.5"):
            return {"deudor": self.socio_b, "acreedor": self.socio_a, "monto": net}
        if net < Decimal("-0.5"):
            return {"deudor": self.socio_a, "acreedor": self.socio_b, "monto": -net}
        return None

    @property
    def ars(self) -> dict | None:
        return self._dir(self.net_ars)

    @property
    def uyu(self) -> dict | None:
        return self._dir(self.net_uyu)

    @property
    def hay_deuda(self) -> bool:
        return self.ars is not None or self.uyu is not None


@dataclass
class AporteItem:
    payment_id: int
    concept: str
    date: dt.date
    total: Decimal
    payer_name: str | None       # quién lo pagó (si se sabe)
    a_delta: Decimal             # + => el socio B le debe esto al socio A por este pago
    unallocated: bool            # aportes no cuadran con el total


def aportes_breakdown(db: Session, partners: list[Partner]) -> list[AporteItem]:
    """Detalle, pago por pago, de lo que forma la deuda por aportes."""
    out: list[AporteItem] = []
    if len(partners) != 2:
        return out
    a = partners[0]
    a_pct = to_decimal(a.pct_share, Decimal("0.01")) / Decimal(100)
    rows = db.scalars(
        select(Payment)
        .options(selectinload(Payment.contributions), selectinload(Payment.paid_by))
        .where(Payment.expense_type != "personal")
        .order_by(Payment.date.desc(), Payment.id.desc())
    )
    for pay in rows:
        total = money(pay.amount_ars)
        contributed = money(sum((c.amount_ars for c in pay.contributions), ZERO))
        unallocated = abs(contributed - total) > CENT
        a_put = money(
            sum((c.amount_ars for c in pay.contributions if c.partner_id == a.id), ZERO)
        )
        delta = ZERO if unallocated else money(a_put - money(total * a_pct))
        if not unallocated and abs(delta) <= CENT:
            continue  # 35/65 limpio: no aporta a la deuda
        out.append(
            AporteItem(
                payment_id=pay.id,
                concept=pay.concept,
                date=pay.date,
                total=total,
                payer_name=pay.paid_by.name if pay.paid_by else None,
                a_delta=delta,
                unallocated=unallocated,
            )
        )
    return out


def aportes_debt(db: Session, partners: list[Partner]) -> Decimal:
    """Deuda entre socios por los pagos compartidos, en ARS.

    + => el segundo socio (por id) le debe al primero.
    Solo cuentan los pagos donde la suma de aportes cuadra con el total (si no
    se sabe quién puso qué, no se puede atribuir una deuda). Un pago repartido
    35/65 no genera deuda; uno pagado 100% por un socio sí (el otro le debe su %).
    """
    if len(partners) != 2:
        return ZERO
    a = partners[0]
    a_pct = to_decimal(a.pct_share, Decimal("0.01")) / Decimal(100)
    rows = db.scalars(
        select(Payment)
        .options(selectinload(Payment.contributions))
        .where(Payment.expense_type != "personal")
    )
    net = ZERO
    for pay in rows:
        total = money(pay.amount_ars)
        contributed = money(sum((c.amount_ars for c in pay.contributions), ZERO))
        if abs(contributed - total) > CENT:
            continue  # pago sin repartir del todo -> no se atribuye
        a_put = money(
            sum((c.amount_ars for c in pay.contributions if c.partner_id == a.id), ZERO)
        )
        net += a_put - money(total * a_pct)
    return money(net)


def socios_saldo(db: Session) -> SociosSaldo:
    """Saldo total entre socios: aportes de pagos + pasadas Colón, sin fecha."""
    from app.services.pases import pase_saldo
    from app.services.payments import active_partners

    partners = active_partners(db)
    s = SociosSaldo()
    if len(partners) != 2:
        return s
    s.socio_a, s.socio_b = partners[0].name, partners[1].name

    s.aportes_ars = aportes_debt(db, partners)
    ps = pase_saldo(db, partners)
    s.pase_ars, s.pase_uyu = ps.net_ars, ps.net_uyu
    s.net_ars = money(s.aportes_ars + ps.net_ars)
    s.net_uyu = money(ps.net_uyu)
    return s
