"""Login / logout / cambio de contraseña."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session

from app.auth import (
    authenticate,
    get_current_partner,
    hash_password,
    login_session,
    logout_session,
    verify_password,
)
from app.database import get_db
from app.models import Partner
from app.web import flash, redirect, render

router = APIRouter()


@router.get("/login")
async def login_form(request: Request, db: Session = Depends(get_db)):
    if request.session.get("partner_id"):
        return redirect("/")
    return render(request, "login.html")


@router.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    partner = authenticate(db, username, password)
    if not partner:
        flash(request, "Usuario o contraseña incorrectos.", "error")
        return render(request, "login.html", {"username": username}, status_code=401)
    login_session(request, partner)
    if partner.must_change_password:
        flash(request, "Elegí una contraseña nueva para tu cuenta.", "info")
        return redirect("/cuenta/password")
    return redirect("/", request, f"Hola, {partner.name}.")


@router.get("/logout")
@router.post("/logout")
async def logout(request: Request):
    logout_session(request)
    return redirect("/login", request, "Sesión cerrada.")


@router.get("/cuenta/password")
async def password_form(request: Request, partner: Partner = Depends(get_current_partner)):
    return render(request, "cuenta_password.html", {"partner": partner, "active_nav": "cuenta"})


@router.post("/cuenta/password")
async def password_submit(
    request: Request,
    current_password: str = Form(""),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    partner: Partner = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    errors = []
    if not partner.must_change_password and not verify_password(
        current_password, partner.password_hash
    ):
        errors.append("La contraseña actual no es correcta.")
    if len(new_password) < 6:
        errors.append("La contraseña nueva tiene que tener al menos 6 caracteres.")
    if new_password != confirm_password:
        errors.append("Las dos contraseñas nuevas no coinciden.")

    if errors:
        for e in errors:
            flash(request, e, "error")
        return render(
            request, "cuenta_password.html", {"partner": partner, "active_nav": "cuenta"},
            status_code=400,
        )

    partner.password_hash = hash_password(new_password)
    partner.must_change_password = False
    db.commit()
    return redirect("/", request, "Contraseña actualizada.")
