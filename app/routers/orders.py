"""Pedidos de importación."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session

from app.audit import record, snapshot
from app.auth import get_current_partner, require_owner
from app.constants import valid_codes
from app.database import get_db
from app.models import Order, Partner
from app.services.documents import list_documents
from app.services.orders import (
    compute_costing,
    list_orders,
    load_order,
    next_number,
    price_scenarios,
    suggested_price,
    unassigned_purchases,
)
from app.services.payments import parse_date
from app.web import flash, redirect, render

router = APIRouter(prefix="/pedidos")


def _markup(value: str) -> Decimal:
    v = str(value or "").strip().replace(",", ".").replace("%", "")
    if not v:
        return Decimal(150)
    try:
        d = Decimal(v)
    except InvalidOperation:
        raise ValueError("Margen inválido.") from None
    if d < 0 or d > 100000:
        raise ValueError("El margen tiene que ser un porcentaje razonable.")
    return d.quantize(Decimal("0.01"))


@router.get("")
async def list_view(
    request: Request,
    partner: Partner = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    orders = list_orders(db)
    costing = {o.id: compute_costing(o) for o in orders}
    return render(
        request,
        "orders/list.html",
        {
            "partner": partner,
            "active_nav": "pedidos",
            "orders": orders,
            "costing": costing,
            "sueltas": unassigned_purchases(db),
        },
        db=db,
    )


@router.get("/nuevo")
async def new_view(
    request: Request,
    partner: Partner = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    return render(
        request,
        "orders/form.html",
        {
            "partner": partner,
            "active_nav": "pedidos",
            "order": None,
            "next_num": next_number(db),
            "form": {
                "date": dt.date.today().isoformat(),
                "status": "abierto",
                "markup_pct": "150",
            },
        },
        db=db,
    )


@router.post("")
async def create_view(
    request: Request,
    date: str = Form(""),
    title: str = Form(""),
    status: str = Form("abierto"),
    markup_pct: str = Form("150"),
    notes: str = Form(""),
    partner: Partner = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    try:
        if status not in valid_codes("order_status"):
            status = "abierto"
        order = Order(
            number=next_number(db),
            title=title.strip() or None,
            date=parse_date(date),
            status=status,
            markup_pct=_markup(markup_pct),
            notes=notes.strip() or None,
        )
    except ValueError as exc:
        flash(request, str(exc), "error")
        return redirect("/pedidos/nuevo")
    db.add(order)
    db.flush()
    record(db, obj=order, action="insert", changed_by=partner.username,
           summary=f"Nuevo {order.display_name}")
    db.commit()
    return redirect(f"/pedidos/{order.id}", request, f"{order.display_name} creado.")


@router.get("/{order_id}")
async def detail_view(
    order_id: int,
    request: Request,
    partner: Partner = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    order = load_order(db, order_id)
    if not order:
        return redirect("/pedidos", request, "No se encontró el pedido.", "error")
    costing = compute_costing(order)
    docs = []
    for pur in order.purchases:
        docs += [("compra", pur, d) for d in list_documents(db, "purchase", pur.id)]
    for pay in order.payments:
        docs += [("pago", pay, d) for d in list_documents(db, "payment", pay.id)]

    price_by_model = {
        m.name: {
            "ars": suggested_price(m.landed_unit_ars, order.markup_pct),
            "usd": suggested_price(m.landed_unit_usd, order.markup_pct),
            "scen_ars": price_scenarios(m.landed_unit_ars),
        }
        for m in costing.models
    }
    return render(
        request,
        "orders/detail.html",
        {
            "partner": partner,
            "active_nav": "pedidos",
            "order": order,
            "costing": costing,
            "documents": docs,
            "price_by_model": price_by_model,
        },
        db=db,
    )


@router.get("/{order_id}/editar")
async def edit_view(
    order_id: int,
    request: Request,
    partner: Partner = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    order = load_order(db, order_id)
    if not order:
        return redirect("/pedidos")
    return render(
        request,
        "orders/form.html",
        {
            "partner": partner,
            "active_nav": "pedidos",
            "order": order,
            "next_num": order.number,
            "form": {
                "date": order.date.isoformat(),
                "title": order.title or "",
                "status": order.status,
                "markup_pct": f"{order.markup_pct.normalize():f}",
                "notes": order.notes or "",
            },
        },
        db=db,
    )


@router.post("/{order_id}")
async def update_view(
    order_id: int,
    request: Request,
    date: str = Form(""),
    title: str = Form(""),
    status: str = Form("abierto"),
    markup_pct: str = Form("150"),
    notes: str = Form(""),
    partner: Partner = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    order = load_order(db, order_id)
    if not order:
        return redirect("/pedidos")
    before = snapshot(order)
    try:
        order.date = parse_date(date)
        order.title = title.strip() or None
        order.status = status if status in valid_codes("order_status") else order.status
        order.markup_pct = _markup(markup_pct)
        order.notes = notes.strip() or None
    except ValueError as exc:
        flash(request, str(exc), "error")
        return redirect(f"/pedidos/{order.id}/editar")
    record(db, obj=order, action="update", changed_by=partner.username,
           summary=f"Edición de {order.display_name}", old=before)
    db.commit()
    return redirect(f"/pedidos/{order.id}", request, "Pedido actualizado.")


@router.post("/{order_id}/eliminar")
async def delete_view(
    order_id: int,
    request: Request,
    partner: Partner = Depends(require_owner),
    db: Session = Depends(get_db),
):
    order = load_order(db, order_id)
    if not order:
        return redirect("/pedidos")
    # desvincula pagos y compras (no se borran, quedan "sueltos")
    for pay in order.payments:
        pay.order_id = None
    for pur in order.purchases:
        pur.order_id = None
    record(db, obj=order, action="delete", changed_by=partner.username,
           summary=f"Baja de {order.display_name}", old=snapshot(order))
    db.delete(order)
    db.commit()
    return redirect("/pedidos", request, "Pedido eliminado. Los pagos y compras quedaron sin asignar.")
