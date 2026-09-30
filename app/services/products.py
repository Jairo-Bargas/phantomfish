"""Productos (señuelos), editables desde la app — para el desplegable de ventas."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.money import ZERO
from app.models import Product, Sale, SaleItem


def all_products(db: Session) -> list[Product]:
    return list(db.scalars(select(Product).order_by(Product.name)))


def active_products(db: Session) -> list[Product]:
    return [p for p in all_products(db) if p.active]


def create_product(db: Session, name: str) -> Product:
    name = name.strip()
    if not name:
        raise ValueError("Escribí un nombre para el producto.")
    if len(name) > 200:
        raise ValueError("El nombre es demasiado largo.")
    existing = db.scalar(select(Product).where(func.lower(Product.name) == name.lower()))
    if existing:
        if not existing.active:
            existing.active = True
            return existing
        raise ValueError(f"Ya existe un producto parecido ('{existing.name}').")
    product = Product(name=name, active=True)
    db.add(product)
    return product


def sales_using(db: Session, name: str) -> int:
    return (
        db.scalar(select(func.count()).select_from(SaleItem).where(SaleItem.product_name == name))
        or 0
    )


@dataclass
class ProductTotal:
    name: str
    quantity: Decimal
    total_ars: Decimal


# Antes de tener el desplegable, el nombre del producto se escribía a mano en cada
# venta -> quedaron muchas variantes del mismo señuelo ("BANANAS", "Bananas",
# "Crank", "CRANK PALA CORTA", "Sub", "SUB SUPERFICIE", etc.). Para que el conteo
# junte todo bajo el producto real, se agrupa por palabra clave (sin tocar el
# nombre guardado en cada venta vieja, que sigue viéndose tal cual se cargó).
_PRODUCT_ALIASES: list[tuple[str, str]] = [
    ("banana", "Señuelo Banana"),
    ("crank", "Señuelo Crank"),
    ("sub", "Señuelo Sub Superficie"),
]


def canonical_product_name(raw: str) -> str:
    norm = (raw or "").strip().lower()
    for keyword, canonical in _PRODUCT_ALIASES:
        if keyword in norm:
            return canonical
    return (raw or "").strip()


def totals_by_product(sales: list[Sale]) -> list[ProductTotal]:
    """Suma cantidad y monto vendido de cada producto, a partir de ventas ya cargadas
    (con `.items` -- se recorren en Python, sin pegarle de nuevo a la base). Los
    nombres viejos escritos a mano se agrupan bajo el producto real (ver
    `canonical_product_name`)."""
    agg: dict[str, dict[str, Decimal]] = {}
    for sale in sales:
        for it in sale.items:
            name = canonical_product_name(it.product_name)
            row = agg.setdefault(name, {"quantity": ZERO, "total_ars": ZERO})
            row["quantity"] += it.quantity
            row["total_ars"] += it.total_ars
    totals = [ProductTotal(name=n, quantity=v["quantity"], total_ars=v["total_ars"]) for n, v in agg.items()]
    totals.sort(key=lambda p: p.quantity, reverse=True)
    return totals
