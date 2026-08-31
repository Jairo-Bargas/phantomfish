"""Categorías de pagos, administrables desde la app."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session

from app.audit import record
from app.auth import get_current_partner
from app.database import get_db
from app.models import Category, Partner
from app.services.categories import (
    all_categories,
    create_category,
    payments_using,
)
from app.web import flash, redirect, render

router = APIRouter(prefix="/categorias")


@router.get("")
async def list_categories(
    request: Request,
    partner: Partner = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    cats = all_categories(db)
    usage = {c.code: payments_using(db, c.code) for c in cats}
    return render(
        request,
        "categories/list.html",
        {"partner": partner, "active_nav": "socios", "categorias_all": cats, "usage": usage},
        db=db,
    )


@router.post("")
async def add_category(
    request: Request,
    label: str = Form(...),
    partner: Partner = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    try:
        cat = create_category(db, label)
    except ValueError as exc:
        flash(request, str(exc), "error")
        return redirect("/categorias")
    db.flush()
    record(db, obj=cat, action="insert", changed_by=partner.username,
           summary=f"Nueva categoría: {cat.label}")
    db.commit()
    return redirect("/categorias", request, f"Categoría '{cat.label}' agregada.")


@router.post("/{cat_id}")
async def edit_category(
    cat_id: int,
    request: Request,
    label: str = Form(""),
    accion: str = Form(""),
    partner: Partner = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    cat = db.get(Category, cat_id)
    if not cat:
        return redirect("/categorias")

    if accion == "toggle":
        cat.active = not cat.active
        estado = "activada" if cat.active else "ocultada"
        record(db, obj=cat, action="update", changed_by=partner.username,
               summary=f"Categoría {estado}: {cat.label}")
        db.commit()
        return redirect("/categorias", request, f"Categoría '{cat.label}' {estado}.")

    new_label = label.strip()
    if new_label and new_label != cat.label:
        old = cat.label
        cat.label = new_label[:80]
        record(db, obj=cat, action="update", changed_by=partner.username,
               summary=f"Categoría renombrada: {old} → {cat.label}")
        db.commit()
        return redirect("/categorias", request, "Categoría renombrada.")
    return redirect("/categorias")
