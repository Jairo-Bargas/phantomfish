"""Creación de tablas y carga inicial de los dos socios."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import hash_password
from app.config import get_settings
from app.constants import PAYMENT_CATEGORIES
from app.database import Base, SessionLocal, engine
from app.migrate import run_migrations
from app.models import Category, Partner


def create_all() -> None:
    Base.metadata.create_all(bind=engine)


def seed_categories(db: Session) -> None:
    """Carga inicial de categorías. No pisa las que el usuario haya agregado/editado."""
    if db.scalar(select(Category).limit(1)):
        return
    for order, (code, label) in enumerate(PAYMENT_CATEGORIES, start=1):
        db.add(Category(code=code, label=label, active=True, sort_order=order * 10))
    db.commit()


def seed_partners(db: Session) -> list[Partner]:
    settings = get_settings()
    existing = list(db.scalars(select(Partner)))
    if existing:
        return existing

    created = []
    for idx, (name, pct, username) in enumerate(settings.seed_partners):
        partner = Partner(
            name=name,
            pct_share=Decimal(pct),
            username=username,
            password_hash=hash_password(settings.seed_password),
            must_change_password=True,
            active=True,
            is_owner=(idx == 0),  # el primero (Jairo) es el administrador
        )
        db.add(partner)
        created.append(partner)
    db.commit()
    return created


def ensure_owner(db: Session) -> None:
    """Garantiza que haya al menos un administrador (el socio de menor id)."""
    if db.scalar(select(Partner).where(Partner.is_owner.is_(True))):
        return
    first = db.scalar(select(Partner).order_by(Partner.id).limit(1))
    if first:
        first.is_owner = True
        db.commit()


def init_db() -> None:
    create_all()
    applied = run_migrations(engine)
    if applied:
        print("Migraciones aplicadas:", ", ".join(applied))
    with SessionLocal() as db:
        seed_partners(db)
        seed_categories(db)
        ensure_owner(db)


if __name__ == "__main__":
    init_db()
    print("Base de datos lista.")
