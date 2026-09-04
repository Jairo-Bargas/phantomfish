"""Autenticación simple por usuario/contraseña con sesión en cookie firmada."""

from __future__ import annotations

import bcrypt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Accountant, Partner

SESSION_KEY = "partner_id"
ACCOUNTANT_SESSION_KEY = "accountant_id"


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def authenticate(db: Session, username: str, password: str) -> Partner | None:
    partner = db.scalar(
        select(Partner).where(func.lower(Partner.username) == username.strip().lower())
    )
    if partner and partner.active and verify_password(password, partner.password_hash):
        return partner
    return None


def login_session(request: Request, partner: Partner) -> None:
    request.session[SESSION_KEY] = partner.id


def logout_session(request: Request) -> None:
    request.session.pop(SESSION_KEY, None)


def get_current_partner_optional(
    request: Request, db: Session = Depends(get_db)
) -> Partner | None:
    pid = request.session.get(SESSION_KEY)
    if not pid:
        return None
    partner = db.get(Partner, pid)
    if partner is None or not partner.active:
        request.session.pop(SESSION_KEY, None)
        return None
    return partner


def get_current_partner(
    partner: Partner | None = Depends(get_current_partner_optional),
) -> Partner:
    if partner is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No autenticado",
            headers={"Location": "/login"},
        )
    return partner


def require_owner(partner: Partner = Depends(get_current_partner)) -> Partner:
    """Solo el administrador puede eliminar registros."""
    if not getattr(partner, "is_owner", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo el administrador puede eliminar registros.",
        )
    return partner


# --------------------------------------------------------------- contadora (solo lectura)


def authenticate_accountant(db: Session, username: str, password: str) -> Accountant | None:
    acc = db.scalar(
        select(Accountant).where(func.lower(Accountant.username) == username.strip().lower())
    )
    if acc and acc.active and verify_password(password, acc.password_hash):
        return acc
    return None


def login_accountant_session(request: Request, acc: Accountant) -> None:
    request.session[ACCOUNTANT_SESSION_KEY] = acc.id


def logout_accountant_session(request: Request) -> None:
    request.session.pop(ACCOUNTANT_SESSION_KEY, None)


def get_current_accountant_optional(
    request: Request, db: Session = Depends(get_db)
) -> Accountant | None:
    aid = request.session.get(ACCOUNTANT_SESSION_KEY)
    if not aid:
        return None
    acc = db.get(Accountant, aid)
    if acc is None or not acc.active:
        request.session.pop(ACCOUNTANT_SESSION_KEY, None)
        return None
    return acc
