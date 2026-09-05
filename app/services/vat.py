"""IVA: discriminación en pagos/ventas y posición crédito vs débito.

- Crédito fiscal: IVA de las facturas A que recibimos (pagos).
- Débito fiscal: IVA de las facturas A que emitimos (ventas).
- Posición = crédito − débito. Positiva = a favor; negativa = a pagar.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.money import ZERO, dsum, money
from app.models import Payment, Sale
from app.services.periods import recent_months

# Alícuotas de IVA vigentes en Argentina.
VAT_RATES: list[tuple[str, str]] = [("21", "21%"), ("10.5", "10,5%"), ("27", "27%")]
DEFAULT_VAT_RATE = Decimal("21")


def parse_rate(value: str | None) -> Decimal | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        r = Decimal(str(value).strip().replace(",", "."))
    except (InvalidOperation, ValueError):
        return None
    return r if r > ZERO else None


def vat_from_total(total: Decimal, rate_pct: Decimal) -> Decimal:
    """IVA contenido en un total que YA incluye IVA.

    total = neto * (1 + r/100)  ->  iva = total − total / (1 + r/100)
    """
    total = money(total)
    r = Decimal(str(rate_pct or 0))
    if r <= ZERO or total <= ZERO:
        return ZERO
    neto = money(total / (Decimal(1) + r / Decimal(100)))
    return money(total - neto)


@dataclass
class VatPeriod:
    code: str  # "2026-09"  ("" = acumulado)
    label: str
    credito: Decimal = ZERO  # IVA de pagos (factura A recibida)
    debito: Decimal = ZERO  # IVA de ventas (factura A emitida)

    @property
    def posicion(self) -> Decimal:
        """crédito − débito. Positivo = a favor; negativo = a pagar."""
        return money(self.credito - self.debito)

    @property
    def a_favor(self) -> bool:
        return self.posicion >= ZERO


def _between(col, date_from, date_to):
    conds = []
    if date_from:
        conds.append(col >= date_from)
    if date_to:
        conds.append(col <= date_to)
    return conds


def vat_totals(
    db: Session,
    *,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
) -> VatPeriod:
    pays = db.scalars(
        select(Payment).where(
            Payment.vat_amount.is_not(None), *_between(Payment.date, date_from, date_to)
        )
    )
    sales = db.scalars(
        select(Sale).where(
            Sale.vat_amount.is_not(None), *_between(Sale.date, date_from, date_to)
        )
    )
    return VatPeriod(
        code="",
        label="Acumulado",
        credito=dsum(p.vat_amount for p in pays),
        debito=dsum(s.vat_amount for s in sales),
    )


def vat_by_month(db: Session, n: int = 12) -> list[VatPeriod]:
    """Últimos ``n`` meses (sin meses futuros), del más nuevo al más viejo."""
    codes = recent_months(n=n, ahead=0)
    buckets = {c: VatPeriod(code=c, label=lbl) for c, lbl in codes}
    for p in db.scalars(select(Payment).where(Payment.vat_amount.is_not(None))):
        code = f"{p.date.year:04d}-{p.date.month:02d}"
        if code in buckets:
            buckets[code].credito = money(buckets[code].credito + p.vat_amount)
    for s in db.scalars(select(Sale).where(Sale.vat_amount.is_not(None))):
        code = f"{s.date.year:04d}-{s.date.month:02d}"
        if code in buckets:
            buckets[code].debito = money(buckets[code].debito + s.vat_amount)
    return [buckets[c] for c, _ in codes]
