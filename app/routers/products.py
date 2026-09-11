"""Productos, administrables desde la app (desplegable de ventas)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session

from app.audit import record
from app.auth import get_current_partner
from app.database import get_db
from app.models import Partner, Product
from app.services.products import all_products, create_product, sales_using
from app.web import flash, redirect, render

router = APIRouter(prefix="/productos")


@router.get("")
async def list_products(
    request: Request,
    partner: Partner = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    products = all_products(db)
    usage = {p.name: sales_using(db, p.name) for p in products}
    return render(
        request,
        "products/list.html",
        {"partner": partner, "active_nav": "socios", "products_all": products, "usage": usage},
        db=db,
    )


@router.post("")
async def add_product(
    request: Request,
    name: str = Form(...),
    partner: Partner = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    try:
        product = create_product(db, name)
    except ValueError as exc:
        flash(request, str(exc), "error")
        return redirect("/productos")
    db.flush()
    record(db, obj=product, action="insert", changed_by=partner.username,
           summary=f"Nuevo producto: {product.name}")
    db.commit()
    return redirect("/productos", request, f"Producto '{product.name}' agregado.")


@router.post("/{product_id}")
async def edit_product(
    product_id: int,
    request: Request,
    name: str = Form(""),
    accion: str = Form(""),
    partner: Partner = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    product = db.get(Product, product_id)
    if not product:
        return redirect("/productos")

    if accion == "toggle":
        product.active = not product.active
        estado = "activado" if product.active else "ocultado"
        record(db, obj=product, action="update", changed_by=partner.username,
               summary=f"Producto {estado}: {product.name}")
        db.commit()
        return redirect("/productos", request, f"Producto '{product.name}' {estado}.")

    new_name = name.strip()
    if new_name and new_name != product.name:
        old = product.name
        product.name = new_name[:200]
        record(db, obj=product, action="update", changed_by=partner.username,
               summary=f"Producto renombrado: {old} → {product.name}")
        db.commit()
        return redirect("/productos", request, "Producto renombrado.")
    return redirect("/productos")
