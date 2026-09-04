"""Acceso de solo lectura para la contadora: facturas recibidas (pagos) y
emitidas (ventas), por fecha. Sin aportes de socios, sin pedidos, sin compras
al proveedor, sin movimientos entre socios."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.auth import (
    authenticate_accountant,
    get_current_accountant_optional,
    hash_password,
    login_accountant_session,
    logout_accountant_session,
    verify_password,
)
from app.database import get_db
from app.models import Accountant, Payment, Sale
from app.money import dsum
from app.services.documents import list_documents
from app.services.periods import month_bounds, month_label, month_options, this_month
from app.web import flash, redirect, render

router = APIRouter(prefix="/contadora")


def _require(request: Request, db: Session) -> Accountant | None:
    return get_current_accountant_optional(request, db)


@router.get("/login")
async def login_form(request: Request, db: Session = Depends(get_db)):
    if request.session.get("accountant_id"):
        return redirect("/contadora")
    return render(request, "accountant/login.html")


@router.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    acc = authenticate_accountant(db, username, password)
    if not acc:
        flash(request, "Usuario o contraseña incorrectos.", "error")
        return render(request, "accountant/login.html", {"username": username}, status_code=401)
    login_accountant_session(request, acc)
    if acc.must_change_password:
        return redirect("/contadora/password")
    return redirect("/contadora", request, f"Hola, {acc.name}.")


@router.get("/salir")
@router.post("/salir")
async def logout(request: Request):
    logout_accountant_session(request)
    return redirect("/contadora/login", request, "Sesión cerrada.")


@router.get("/password")
async def password_form(request: Request, db: Session = Depends(get_db)):
    acc = _require(request, db)
    if not acc:
        return redirect("/contadora/login")
    return render(request, "accountant/password.html", {"accountant": acc})


@router.post("/password")
async def password_submit(
    request: Request,
    current_password: str = Form(""),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db),
):
    acc = _require(request, db)
    if not acc:
        return redirect("/contadora/login")
    errors = []
    if not acc.must_change_password and not verify_password(current_password, acc.password_hash):
        errors.append("La contraseña actual no es correcta.")
    if len(new_password) < 6:
        errors.append("La contraseña nueva tiene que tener al menos 6 caracteres.")
    if new_password != confirm_password:
        errors.append("Las dos contraseñas nuevas no coinciden.")
    if errors:
        for e in errors:
            flash(request, e, "error")
        return render(request, "accountant/password.html", {"accountant": acc}, status_code=400)
    acc.password_hash = hash_password(new_password)
    acc.must_change_password = False
    db.commit()
    return redirect("/contadora", request, "Contraseña actualizada.")


@router.get("")
async def dashboard(
    request: Request,
    mes: str | None = None,
    desde: str | None = None,
    hasta: str | None = None,
    db: Session = Depends(get_db),
):
    acc = _require(request, db)
    if not acc:
        return redirect("/contadora/login")

    use_range = bool(desde or hasta)
    if not use_range:
        mes = mes or this_month()
        date_from, date_to = month_bounds(mes)
        titulo = month_label(mes)
    else:
        date_from = dt.date.fromisoformat(desde) if desde else None
        date_to = dt.date.fromisoformat(hasta) if hasta else None
        titulo = "Período elegido"

    pay_stmt = select(Payment).options(selectinload(Payment.order))
    if date_from:
        pay_stmt = pay_stmt.where(Payment.date >= date_from)
    if date_to:
        pay_stmt = pay_stmt.where(Payment.date <= date_to)
    payments = list(db.scalars(pay_stmt.order_by(Payment.date, Payment.id)))

    sale_stmt = select(Sale).options(selectinload(Sale.items))
    if date_from:
        sale_stmt = sale_stmt.where(Sale.date >= date_from)
    if date_to:
        sale_stmt = sale_stmt.where(Sale.date <= date_to)
    sales = list(db.scalars(sale_stmt.order_by(Sale.date, Sale.id)))

    pay_docs = {p.id: list_documents(db, "payment", p.id) for p in payments}
    sale_docs = {s.id: list_documents(db, "sale", s.id) for s in sales}

    return render(
        request,
        "accountant/dashboard.html",
        {
            "accountant": acc,
            "titulo": titulo,
            "mes": mes or "",
            "desde": desde or "",
            "hasta": hasta or "",
            "use_range": use_range,
            "months": month_options(mes),
            "payments": payments,
            "sales": sales,
            "pay_docs": pay_docs,
            "sale_docs": sale_docs,
            "total_pagos": dsum(p.amount_ars for p in payments),
            "total_ventas": dsum(s.total_ars for s in sales),
        },
        db=db,
    )
