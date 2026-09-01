"""Compras al proveedor (importación) + detalle de mercadería."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.audit import record, snapshot
from app.auth import get_current_partner, require_owner
from app.constants import valid_codes
from app.database import get_db
from app.money import ZERO, dsum
from app.models import Order, Partner, Payment, Purchase, PurchaseItem
from app.services.documents import attach_files, list_documents
from app.services.orders import order_choices
from app.services.payments import parse_date
from app.web import flash, redirect, render

router = APIRouter(prefix="/compras")


def _load(db: Session, purchase_id: int) -> Purchase | None:
    return db.scalar(
        select(Purchase)
        .options(
            selectinload(Purchase.items),
            selectinload(Purchase.payment),
            selectinload(Purchase.order),
        )
        .where(Purchase.id == purchase_id)
    )


def _num(value: str, field: str, quant: Decimal = Decimal("0.01")) -> Decimal:
    v = str(value or "").strip().replace(" ", "")
    if not v:
        return ZERO
    if "," in v and v.rfind(",") > v.rfind("."):
        v = v.replace(".", "").replace(",", ".")
    else:
        v = v.replace(",", "")
    try:
        return Decimal(v).quantize(quant)
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field}: número inválido ({value!r}).") from None


def _parse_items(form: dict) -> list[dict]:
    items: list[dict] = []
    idx = 0
    while True:
        name = form.get(f"item_name_{idx}")
        if name is None:
            break
        name = name.strip()
        if name:
            qty = _num(form.get(f"item_qty_{idx}", ""), f"Cantidad fila {idx + 1}")
            price = _num(form.get(f"item_price_{idx}", ""), f"Precio fila {idx + 1}")
            items.append({"product_name": name, "quantity": qty, "unit_price_usd": price})
        idx += 1
    return items


@router.get("")
async def list_purchases(
    request: Request,
    partner: Partner = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    purchases = list(
        db.scalars(
            select(Purchase)
            .options(selectinload(Purchase.items), selectinload(Purchase.order))
            .order_by(Purchase.date.desc(), Purchase.id.desc())
        )
    )
    total_usd = dsum(p.total_usd for p in purchases)
    return render(
        request,
        "purchases/list.html",
        {
            "partner": partner,
            "active_nav": "pedidos",
            "purchases": purchases,
            "total_usd": total_usd,
        },
    )


@router.get("/nueva")
async def new_purchase(
    request: Request,
    partner: Partner = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    payments = list(db.scalars(select(Payment).order_by(Payment.date.desc()).limit(50)))
    return render(
        request,
        "purchases/form.html",
        {
            "partner": partner,
            "active_nav": "pedidos",
            "purchase": None,
            "payments": payments,
            "orders": order_choices(db),
            "form": {
                "date": dt.date.today().isoformat(),
                "shipment_status": "pendiente_pedido",
                "order_id": request.query_params.get("pedido", ""),
            },
            "items": [],
        },
    )


@router.post("")
async def create_purchase(
    request: Request,
    partner: Partner = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    form_data = await request.form()
    form = dict(form_data.multi_items())
    files: list[UploadFile] = form_data.getlist("comprobantes")  # type: ignore

    try:
        purchase = _build_from_form(db, form)
        items = _parse_items(form)
    except ValueError as exc:
        flash(request, str(exc), "error")
        return _rerender(request, db, partner, form, status_code=400)

    for it in items:
        purchase.items.append(PurchaseItem(**it))
    db.add(purchase)
    db.flush()

    saved, errors = await attach_files(
        db, files=files, entity_type="purchase", entity_id=purchase.id,
        label=purchase.supplier, on_date=purchase.date, uploaded_by=partner.username,
    )
    for e in errors:
        flash(request, e, "error")
    record(db, obj=purchase, action="insert", changed_by=partner.username,
           summary=f"Alta de compra a {purchase.supplier}")
    db.commit()
    return redirect(f"/compras/{purchase.id}", request,
                    f"Compra cargada ({saved} comprobante/s)." if saved else "Compra cargada.")


def _build_from_form(db: Session, form: dict) -> Purchase:
    supplier = (form.get("supplier") or "").strip()
    if not supplier:
        raise ValueError("Poné el proveedor.")
    shipment = form.get("shipment_status") or "pendiente_pedido"
    if shipment not in valid_codes("shipment_status"):
        raise ValueError("Estado de envío inválido.")
    payment_id = form.get("payment_id") or None
    if payment_id:
        try:
            payment_id = int(payment_id)
            if not db.get(Payment, payment_id):
                raise ValueError
        except (ValueError, TypeError):
            raise ValueError("El pago vinculado no existe.") from None
    order_id = form.get("order_id") or None
    if order_id:
        try:
            order_id = int(order_id)
            if not db.get(Order, order_id):
                order_id = None
        except (ValueError, TypeError):
            order_id = None
    return Purchase(
        date=parse_date(form.get("date")),
        supplier=supplier,
        invoice_number=(form.get("invoice_number") or "").strip() or None,
        payment_id=payment_id or None,
        order_id=order_id or None,
        shipment_status=shipment,
        notes=(form.get("notes") or "").strip() or None,
    )


def _rerender(request, db, partner, form, *, status_code=200, purchase=None):
    payments = list(db.scalars(select(Payment).order_by(Payment.date.desc()).limit(50)))
    return render(
        request,
        "purchases/form.html",
        {
            "partner": partner,
            "active_nav": "pedidos",
            "purchase": purchase,
            "payments": payments,
            "orders": order_choices(db),
            "form": form,
            "items": _parse_items(form),
        },
        status_code=status_code,
    )


@router.get("/{purchase_id}")
async def purchase_detail(
    purchase_id: int,
    request: Request,
    partner: Partner = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    purchase = _load(db, purchase_id)
    if not purchase:
        flash(request, "No se encontró la compra.", "error")
        return redirect("/compras")
    return render(
        request,
        "purchases/detail.html",
        {
            "partner": partner,
            "active_nav": "pedidos",
            "purchase": purchase,
            "documents": list_documents(db, "purchase", purchase.id),
        },
    )


@router.get("/{purchase_id}/editar")
async def edit_purchase(
    purchase_id: int,
    request: Request,
    partner: Partner = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    purchase = _load(db, purchase_id)
    if not purchase:
        flash(request, "No se encontró la compra.", "error")
        return redirect("/compras")
    payments = list(db.scalars(select(Payment).order_by(Payment.date.desc()).limit(50)))
    return render(
        request,
        "purchases/form.html",
        {
            "partner": partner,
            "active_nav": "pedidos",
            "purchase": purchase,
            "payments": payments,
            "orders": order_choices(db),
            "form": {
                "date": purchase.date.isoformat(),
                "supplier": purchase.supplier,
                "invoice_number": purchase.invoice_number or "",
                "payment_id": str(purchase.payment_id or ""),
                "order_id": str(purchase.order_id or ""),
                "shipment_status": purchase.shipment_status,
                "notes": purchase.notes or "",
            },
            "items": [
                {
                    "product_name": i.product_name,
                    "quantity": i.quantity,
                    "unit_price_usd": i.unit_price_usd,
                }
                for i in purchase.items
            ],
        },
    )


@router.post("/{purchase_id}")
async def update_purchase(
    purchase_id: int,
    request: Request,
    partner: Partner = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    purchase = _load(db, purchase_id)
    if not purchase:
        flash(request, "No se encontró la compra.", "error")
        return redirect("/compras")
    form = dict((await request.form()).multi_items())
    before = snapshot(purchase)
    try:
        data = _build_from_form(db, form)
        items = _parse_items(form)
    except ValueError as exc:
        flash(request, str(exc), "error")
        return _rerender(request, db, partner, form, status_code=400, purchase=purchase)

    for field in (
        "date", "supplier", "invoice_number", "payment_id", "order_id",
        "shipment_status", "notes",
    ):
        setattr(purchase, field, getattr(data, field))
    purchase.items.clear()
    for it in items:
        purchase.items.append(PurchaseItem(**it))

    record(db, obj=purchase, action="update", changed_by=partner.username,
           summary=f"Edición de compra #{purchase.id}", old=before)
    db.commit()
    return redirect(f"/compras/{purchase.id}", request, "Compra actualizada.")


@router.post("/{purchase_id}/eliminar")
async def delete_purchase(
    purchase_id: int,
    request: Request,
    partner: Partner = Depends(require_owner),
    db: Session = Depends(get_db),
):
    purchase = _load(db, purchase_id)
    if not purchase:
        flash(request, "No se encontró la compra.", "error")
        return redirect("/compras")
    from app.models import Document
    from app.storage import delete_file

    for doc in db.scalars(
        select(Document).where(
            Document.entity_type == "purchase", Document.entity_id == purchase.id
        )
    ):
        delete_file(doc.file_reference)
        db.delete(doc)
    record(db, obj=purchase, action="delete", changed_by=partner.username,
           summary=f"Baja de compra #{purchase.id}", old=snapshot(purchase))
    db.delete(purchase)
    db.commit()
    return redirect("/compras", request, "Compra eliminada.")
