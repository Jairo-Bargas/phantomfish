"""Productos (señuelos), editables desde la app — para el desplegable de ventas."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Product, SaleItem


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
