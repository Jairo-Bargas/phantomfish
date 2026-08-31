"""Pedidos de importación: costo real por señuelo y precio sugerido."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.money import CENT, ZERO, money, to_decimal
from app.models import Order, Purchase


def next_number(db: Session) -> int:
    return (db.scalar(select(func.max(Order.number))) or 0) + 1


def list_orders(db: Session) -> list[Order]:
    return list(
        db.scalars(
            select(Order)
            .options(
                selectinload(Order.purchases).selectinload(Purchase.items),
                selectinload(Order.payments),
            )
            .order_by(Order.number.desc())
        )
    )


def load_order(db: Session, order_id: int) -> Order | None:
    return db.scalar(
        select(Order)
        .options(
            selectinload(Order.purchases).selectinload(Purchase.items),
            selectinload(Order.payments),
        )
        .where(Order.id == order_id)
    )


@dataclass
class ModelCost:
    name: str
    qty: Decimal
    supplier_unit_usd: Decimal  # precio del proveedor
    landed_unit_usd: Decimal  # + flete/aduana repartido
    landed_unit_ars: Decimal


@dataclass
class OrderCosting:
    units: Decimal = ZERO
    merch_usd: Decimal = ZERO  # valor de la mercadería a precio proveedor
    payments_usd: Decimal = ZERO  # total pagos del pedido (USD)
    payments_ars: Decimal = ZERO  # total pagos del pedido (ARS) = lo realmente gastado
    extra_usd: Decimal = ZERO  # flete + aduana + comisiones (USD)
    extra_per_unit_usd: Decimal = ZERO
    blended_rate: Decimal = ZERO  # ARS por USD promedio del pedido
    avg_landed_usd: Decimal = ZERO
    avg_landed_ars: Decimal = ZERO
    models: list[ModelCost] = field(default_factory=list)
    incomplete: bool = False  # faltan datos para el costo final
    note: str = ""


def compute_costing(order: Order) -> OrderCosting:
    c = OrderCosting()

    # --- mercadería (de las compras vinculadas) ---
    agg: dict[str, dict] = {}
    for pur in order.purchases:
        for it in pur.items:
            qty = to_decimal(it.quantity, CENT)
            price = money(it.unit_price_usd)
            row = agg.setdefault(it.product_name.strip(), {"qty": ZERO, "usd": ZERO})
            row["qty"] = money(row["qty"] + qty)
            row["usd"] = money(row["usd"] + qty * price)

    c.units = money(sum((r["qty"] for r in agg.values()), ZERO))
    c.merch_usd = money(sum((r["usd"] for r in agg.values()), ZERO))

    # --- pagos del pedido ---
    c.payments_usd = money(sum((money(p.amount_usd) for p in order.payments), ZERO))
    c.payments_ars = money(sum((money(p.amount_ars) for p in order.payments), ZERO))

    if c.payments_usd > ZERO:
        c.blended_rate = money(c.payments_ars / c.payments_usd)

    # --- flete/aduana/comisiones a repartir ---
    c.extra_usd = money(c.payments_usd - c.merch_usd)
    if c.extra_usd < ZERO:
        c.extra_usd = ZERO
        c.incomplete = True
        c.note = "Los pagos cargados no cubren el valor de la mercadería. Cargá los pagos del pedido para ver el costo final."
    if c.units <= ZERO:
        c.incomplete = True
        c.note = c.note or "Agregá una compra con el detalle de modelos y cantidades para calcular el costo."
    elif not order.payments:
        c.incomplete = True
        c.note = c.note or "Todavía no hay pagos vinculados a este pedido."

    if c.units > ZERO:
        c.extra_per_unit_usd = money(c.extra_usd / c.units)
        c.avg_landed_usd = money((c.merch_usd + c.extra_usd) / c.units)
        c.avg_landed_ars = money(c.payments_ars / c.units) if c.payments_ars > ZERO else (
            money(c.avg_landed_usd * c.blended_rate)
        )

    for name, r in sorted(agg.items()):
        supplier_unit = money(r["usd"] / r["qty"]) if r["qty"] > ZERO else ZERO
        landed_usd = money(supplier_unit + c.extra_per_unit_usd)
        landed_ars = money(landed_usd * c.blended_rate) if c.blended_rate > ZERO else ZERO
        c.models.append(
            ModelCost(
                name=name,
                qty=r["qty"],
                supplier_unit_usd=supplier_unit,
                landed_unit_usd=landed_usd,
                landed_unit_ars=landed_ars,
            )
        )
    return c


def price_scenarios(cost: Decimal, factors=(Decimal(2), Decimal("2.5"), Decimal(3))) -> list[dict]:
    cost = money(cost)
    return [{"factor": f, "price": money(cost * f)} for f in factors]


def suggested_price(cost: Decimal, markup_pct: Decimal) -> Decimal:
    return money(money(cost) * (Decimal(1) + to_decimal(markup_pct, CENT) / Decimal(100)))


def unassigned_purchases(db: Session) -> list[Purchase]:
    return list(
        db.scalars(
            select(Purchase)
            .options(selectinload(Purchase.items))
            .where(Purchase.order_id.is_(None))
            .order_by(Purchase.date.desc(), Purchase.id.desc())
        )
    )


def order_choices(db: Session) -> list[Order]:
    return list(db.scalars(select(Order).order_by(Order.number.desc())))
