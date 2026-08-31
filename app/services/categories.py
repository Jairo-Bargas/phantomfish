"""Categorías de pago, editables desde la app."""

from __future__ import annotations

import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Category, Payment


def slug_code(label: str) -> str:
    text = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").lower()
    return text[:40] or "categoria"


def all_categories(db: Session) -> list[Category]:
    return list(db.scalars(select(Category).order_by(Category.sort_order, Category.label)))


def active_categories(db: Session) -> list[Category]:
    return [c for c in all_categories(db) if c.active]


def label_map(db: Session) -> dict[str, str]:
    return {c.code: c.label for c in all_categories(db)}


def valid_category_codes(db: Session) -> set[str]:
    return {c.code for c in all_categories(db)}


def by_code(db: Session, code: str) -> Category | None:
    return db.scalar(select(Category).where(Category.code == code))


def create_category(db: Session, label: str) -> Category:
    label = label.strip()
    if not label:
        raise ValueError("Escribí un nombre para la categoría.")
    if len(label) > 80:
        raise ValueError("El nombre es demasiado largo.")
    code = slug_code(label)
    existing = by_code(db, code)
    if existing:
        if not existing.active:
            existing.active = True
            return existing
        raise ValueError(f"Ya existe una categoría parecida ('{existing.label}').")
    max_order = max((c.sort_order for c in all_categories(db)), default=0)
    cat = Category(code=code, label=label, active=True, sort_order=max_order + 10)
    db.add(cat)
    return cat


def payments_using(db: Session, code: str) -> int:
    from sqlalchemy import func

    return db.scalar(select(func.count()).select_from(Payment).where(Payment.category == code)) or 0
