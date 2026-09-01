"""Lógica de cálculo de pagos y reparto de aportes entre socios."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.money import CENT, ZERO, money, rate, split_by_percentages, to_decimal
from app.models import Partner, Payment, PaymentContribution


@dataclass
class PaymentAmounts:
    amount_ars: Decimal
    amount_usd: Decimal
    exchange_rate: Decimal


_CURRENCIES = {"ARS", "USD", "UYU"}


def compute_amounts(
    *, currency_charged: str, amount_original: Decimal, exchange_rate: Decimal
) -> PaymentAmounts:
    """Calcula ARS y USD a partir de la moneda y la cotización confirmada.

    - USD: la cotización es ARS por dólar.  ARS = original * cotización; USD = original.
    - UYU: la cotización es ARS por peso uruguayo.  ARS = original * cotización; USD = 0.
    - ARS: la cotización es ARS por dólar (solo para el equivalente en USD).
    """
    currency_charged = currency_charged.upper()
    amount_original = money(amount_original)
    exchange_rate = rate(exchange_rate)

    if currency_charged not in _CURRENCIES:
        raise ValueError("Moneda inválida (usá pesos, dólares o pesos uruguayos).")
    if amount_original <= ZERO:
        raise ValueError("El monto tiene que ser mayor a cero.")
    if currency_charged != "ARS" and exchange_rate <= ZERO:
        raise ValueError("La cotización tiene que ser mayor a cero.")

    if currency_charged == "USD":
        amount_usd = amount_original
        amount_ars = money(amount_original * exchange_rate)
    elif currency_charged == "UYU":
        amount_ars = money(amount_original * exchange_rate)
        amount_usd = ZERO
    else:  # ARS
        amount_ars = amount_original
        amount_usd = money(amount_original / exchange_rate) if exchange_rate > ZERO else ZERO

    return PaymentAmounts(amount_ars=amount_ars, amount_usd=amount_usd, exchange_rate=exchange_rate)


def settlement_ars(currency: str, amount_original: Decimal, exchange_rate: Decimal) -> Decimal:
    """Convierte un movimiento entre socios a pesos argentinos (valor congelado)."""
    currency = (currency or "ARS").upper()
    amount_original = money(amount_original)
    if amount_original <= ZERO:
        raise ValueError("El monto tiene que ser mayor a cero.")
    if currency == "ARS":
        return amount_original
    r = rate(exchange_rate)
    if r <= ZERO:
        raise ValueError("La cotización tiene que ser mayor a cero.")
    return money(amount_original * r)


def active_partners(db: Session) -> list[Partner]:
    return list(
        db.scalars(select(Partner).where(Partner.active.is_(True)).order_by(Partner.id))
    )


def default_split(db: Session, total_ars: Decimal) -> dict[int, Decimal]:
    """Reparto automático Jairo 35 / Sebastián 65 (según pct_share de cada socio)."""
    partners = active_partners(db)
    pairs = [(p.id, to_decimal(p.pct_share, Decimal("0.01"))) for p in partners]
    return split_by_percentages(money(total_ars), pairs)


def apply_contributions(
    db: Session,
    payment: Payment,
    amounts_by_partner: dict[int, Decimal],
) -> None:
    """Reemplaza los aportes del pago por los montos indicados (por partner_id)."""
    existing = {c.partner_id: c for c in payment.contributions}
    seen: set[int] = set()

    for partner_id, amount in amounts_by_partner.items():
        amount = money(amount)
        seen.add(partner_id)
        if partner_id in existing:
            existing[partner_id].amount_ars = amount
        else:
            payment.contributions.append(
                PaymentContribution(partner_id=partner_id, amount_ars=amount)
            )

    for partner_id, contribution in list(existing.items()):
        if partner_id not in seen:
            payment.contributions.remove(contribution)


def parse_date(value: str | None) -> dt.date:
    if not value:
        return dt.date.today()
    return dt.date.fromisoformat(value)


def control_row(payment: Payment) -> dict:
    """Las dos celdas de control que pidió el usuario."""
    total = money(payment.amount_ars)
    aportes = payment.contributed_total
    diff = money(total - aportes)
    return {
        "total_pago": total,
        "suma_aportes": aportes,
        "diferencia": diff,
        "ok": abs(diff) <= CENT,
    }
