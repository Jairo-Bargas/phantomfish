"""Movimientos entre socios (cuenta corriente / devoluciones)."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Partner, Settlement


def list_settlements(
    db: Session,
    *,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    limit: int | None = None,
) -> list[Settlement]:
    stmt = (
        select(Settlement)
        .options(
            selectinload(Settlement.from_partner),
            selectinload(Settlement.to_partner),
        )
        .order_by(Settlement.date.desc(), Settlement.id.desc())
    )
    if date_from:
        stmt = stmt.where(Settlement.date >= date_from)
    if date_to:
        stmt = stmt.where(Settlement.date <= date_to)
    if limit:
        stmt = stmt.limit(limit)
    return list(db.scalars(stmt))


def load_settlement(db: Session, settlement_id: int) -> Settlement | None:
    return db.scalar(
        select(Settlement)
        .options(
            selectinload(Settlement.from_partner),
            selectinload(Settlement.to_partner),
        )
        .where(Settlement.id == settlement_id)
    )


def other_partner(db: Session, partner: Partner) -> Partner | None:
    return db.scalar(
        select(Partner).where(Partner.id != partner.id, Partner.active.is_(True)).order_by(Partner.id)
    )


def last_rate(db: Session, currency: str):
    """Última cotización usada en esa moneda — primero en movimientos, si no en pagos."""
    from app.services.payments import last_rate_for_currency

    r = db.scalar(
        select(Settlement.exchange_rate)
        .where(Settlement.currency == currency.upper(), Settlement.exchange_rate > 0)
        .order_by(Settlement.date.desc(), Settlement.id.desc())
        .limit(1)
    )
    if r and r > 1:
        return r
    return last_rate_for_currency(db, currency)
