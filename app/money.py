"""Manejo de plata con Decimal exacto y tipos SQLAlchemy que no pierden precisión.

En SQLite los NUMERIC se guardan como float y pierden centavos. Para evitarlo
guardamos los montos como texto y los convertimos a Decimal al leer. En
PostgreSQL usamos NUMERIC nativo.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from sqlalchemy import Numeric, String
from sqlalchemy.types import TypeDecorator

CENT = Decimal("0.01")
RATE_Q = Decimal("0.0001")
ZERO = Decimal("0.00")


def to_decimal(value: object, quant: Decimal = CENT) -> Decimal:
    """Convierte cualquier cosa razonable a Decimal cuantizado. None -> 0."""
    if value is None or value == "":
        return ZERO.quantize(quant)
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:  # pragma: no cover - defensivo
        raise ValueError(f"Monto inválido: {value!r}") from exc
    return d.quantize(quant, rounding=ROUND_HALF_UP)


def money(value: object) -> Decimal:
    return to_decimal(value, CENT)


def rate(value: object) -> Decimal:
    return to_decimal(value, RATE_Q)


def split_by_percentages(total: Decimal, pairs: list[tuple[int, Decimal]]) -> dict[int, Decimal]:
    """Reparte ``total`` según porcentajes ``[(partner_id, pct), ...]``.

    El último socio absorbe el redondeo para que la suma dé exactamente el total.
    """
    total = money(total)
    result: dict[int, Decimal] = {}
    running = ZERO
    for idx, (partner_id, pct) in enumerate(pairs):
        if idx == len(pairs) - 1:
            share = money(total - running)
        else:
            share = money(total * to_decimal(pct, Decimal("0.0001")) / Decimal(100))
            running += share
        result[partner_id] = share
    return result


def dsum(values) -> Decimal:
    """Suma exacta de una lista de valores monetarios."""
    acc = ZERO
    for v in values:
        acc += money(v)
    return money(acc)


class Money(TypeDecorator):
    """Monto con 2 decimales, exacto en SQLite y PostgreSQL."""

    impl = Numeric(18, 2)
    cache_ok = True

    def load_dialect_impl(self, dialect):  # noqa: ANN001
        if dialect.name == "sqlite":
            return dialect.type_descriptor(String(32))
        return dialect.type_descriptor(Numeric(18, 2))

    def process_bind_param(self, value, dialect):  # noqa: ANN001
        if value is None:
            return None
        d = money(value)
        return str(d) if dialect.name == "sqlite" else d

    def process_result_value(self, value, dialect):  # noqa: ANN001
        if value is None:
            return None
        return money(value)


class Rate(TypeDecorator):
    """Cotización con 4 decimales."""

    impl = Numeric(18, 4)
    cache_ok = True

    def load_dialect_impl(self, dialect):  # noqa: ANN001
        if dialect.name == "sqlite":
            return dialect.type_descriptor(String(32))
        return dialect.type_descriptor(Numeric(18, 4))

    def process_bind_param(self, value, dialect):  # noqa: ANN001
        if value is None:
            return None
        d = rate(value)
        return str(d) if dialect.name == "sqlite" else d

    def process_result_value(self, value, dialect):  # noqa: ANN001
        if value is None:
            return None
        return rate(value)
