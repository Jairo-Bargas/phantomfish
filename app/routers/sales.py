"""Ventas / ingresos (precio x cantidad se calcula solo)."""

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
from app.money import CENT, ZERO, dsum, money
from app.models import Partner, Sale, SaleItem
from app.services.documents import attach_files, list_documents
from app.services.payments import parse_date
from app.services.vat import DEFAULT_VAT_RATE, parse_rate, vat_from_total
from app.web import flash, redirect, render

router = APIRouter(prefix="/ventas")


def _load(db: Session, sale_id: int) -> Sale | None:
    return db.scalar(
        select(Sale).options(selectinload(Sale.items)).where(Sale.id == sale_id)
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


def _apply_vat(sale: Sale, form: dict) -> None:
    """Fija sale.vat_amount / vat_net / vat_rate según el form y el total actual.

    Neto e IVA se cargan tal cual la factura; si no se tocan, se calculan del
    total con la alícuota. El resto del total son percepciones / otros conceptos.
    """
    if not form.get("vat_discrimina"):
        sale.vat_amount = sale.vat_net = sale.vat_rate = None
        return
    rate_pct = parse_rate(form.get("vat_rate")) or DEFAULT_VAT_RATE
    total = sale.total_ars
    net = _num(form.get("vat_neto", ""), "Neto gravado")
    iva = _num(form.get("vat_iva", ""), "IVA")
    if net <= ZERO and iva <= ZERO:
        iva = vat_from_total(total, rate_pct)
        net = money(total - iva)
    elif iva <= ZERO:
        iva = money(net * rate_pct / Decimal(100))
    elif net <= ZERO:
        net = money(total - iva)
    if money(net + iva) > money(total + CENT):
        raise ValueError("Neto + IVA no puede superar el total de la venta.")
    sale.vat_amount = iva
    sale.vat_net = net
    sale.vat_rate = rate_pct


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
            items.append({"product_name": name, "quantity": qty, "unit_price_ars": price})
        idx += 1
    return items


@router.get("")
async def list_sales(
    request: Request,
    partner: Partner = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    sales = list(
        db.scalars(
            select(Sale)
            .options(selectinload(Sale.items))
            .order_by(Sale.date.desc(), Sale.id.desc())
        )
    )
    total_ars = dsum(s.total_ars for s in sales)
    return render(
        request,
        "sales/list.html",
        {"partner": partner, "active_nav": "ventas", "sales": sales, "total_ars": total_ars},
    )


@router.get("/nueva")
async def new_sale(
    request: Request,
    partner: Partner = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    return render(
        request,
        "sales/form.html",
        {
            "partner": partner,
            "active_nav": "ventas",
            "sale": None,
            "form": {
                "date": dt.date.today().isoformat(),
                "channel": "mayorista",
                "payment_method": "transferencia",
                "status": "cobrado",
            },
            "items": [],
        },
    )


@router.post("")
async def create_sale(
    request: Request,
    partner: Partner = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    form_data = await request.form()
    form = dict(form_data.multi_items())
    files: list[UploadFile] = form_data.getlist("comprobantes")  # type: ignore
    try:
        sale = _build_from_form(form)
        items = _parse_items(form)
    except ValueError as exc:
        flash(request, str(exc), "error")
        return _rerender(request, partner, form, status_code=400)
    if not items:
        flash(request, "Agregá al menos un producto vendido.", "error")
        return _rerender(request, partner, form, status_code=400)

    for it in items:
        sale.items.append(SaleItem(**it))
    try:
        _apply_vat(sale, form)
    except ValueError as exc:
        flash(request, str(exc), "error")
        return _rerender(request, partner, form, status_code=400)
    db.add(sale)
    db.flush()
    saved, errors = await attach_files(
        db, files=files, entity_type="sale", entity_id=sale.id,
        label=sale.customer or "venta", on_date=sale.date, uploaded_by=partner.username,
    )
    for e in errors:
        flash(request, e, "error")
    record(db, obj=sale, action="insert", changed_by=partner.username,
           summary=f"Alta de venta ({sale.customer or 'sin cliente'})")
    db.commit()
    return redirect(f"/ventas/{sale.id}", request,
                    f"Venta cargada ({saved} comprobante/s)." if saved else "Venta cargada.")


def _build_from_form(form: dict) -> Sale:
    channel = form.get("channel") or None
    if channel and channel not in valid_codes("sale_channel"):
        raise ValueError("Canal inválido.")
    method = form.get("payment_method") or "transferencia"
    if method not in valid_codes("payment_method"):
        raise ValueError("Medio de pago inválido.")
    status = form.get("status") or "cobrado"
    if status not in valid_codes("sale_status"):
        raise ValueError("Estado inválido.")
    return Sale(
        date=parse_date(form.get("date")),
        customer=(form.get("customer") or "").strip() or None,
        channel=channel,
        payment_method=method,
        status=status,
        invoice_number=(form.get("invoice_number") or "").strip() or None,
        notes=(form.get("notes") or "").strip() or None,
    )


def _rerender(request, partner, form, *, status_code=200, sale=None):
    return render(
        request,
        "sales/form.html",
        {
            "partner": partner,
            "active_nav": "ventas",
            "sale": sale,
            "form": form,
            "items": _parse_items(form),
        },
        status_code=status_code,
    )


@router.get("/{sale_id}")
async def sale_detail(
    sale_id: int,
    request: Request,
    partner: Partner = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    sale = _load(db, sale_id)
    if not sale:
        flash(request, "No se encontró la venta.", "error")
        return redirect("/ventas")
    return render(
        request,
        "sales/detail.html",
        {
            "partner": partner,
            "active_nav": "ventas",
            "sale": sale,
            "documents": list_documents(db, "sale", sale.id),
        },
    )


@router.get("/{sale_id}/editar")
async def edit_sale(
    sale_id: int,
    request: Request,
    partner: Partner = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    sale = _load(db, sale_id)
    if not sale:
        flash(request, "No se encontró la venta.", "error")
        return redirect("/ventas")
    return render(
        request,
        "sales/form.html",
        {
            "partner": partner,
            "active_nav": "ventas",
            "sale": sale,
            "form": {
                "date": sale.date.isoformat(),
                "customer": sale.customer or "",
                "channel": sale.channel or "",
                "payment_method": sale.payment_method,
                "status": sale.status,
                "invoice_number": sale.invoice_number or "",
                "vat_discrimina": "1" if sale.vat_amount is not None else "",
                "vat_rate": (f"{sale.vat_rate.normalize():f}" if sale.vat_rate is not None else "21"),
                "vat_neto": (f"{sale.net_amount:.2f}" if sale.vat_amount is not None else ""),
                "vat_iva": (f"{sale.vat_amount:.2f}" if sale.vat_amount is not None else ""),
                "notes": sale.notes or "",
            },
            "items": [
                {
                    "product_name": i.product_name,
                    "quantity": i.quantity,
                    "unit_price_ars": i.unit_price_ars,
                }
                for i in sale.items
            ],
        },
    )


@router.post("/{sale_id}")
async def update_sale(
    sale_id: int,
    request: Request,
    partner: Partner = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    sale = _load(db, sale_id)
    if not sale:
        flash(request, "No se encontró la venta.", "error")
        return redirect("/ventas")
    form = dict((await request.form()).multi_items())
    before = snapshot(sale)
    try:
        data = _build_from_form(form)
        items = _parse_items(form)
    except ValueError as exc:
        flash(request, str(exc), "error")
        return _rerender(request, partner, form, status_code=400, sale=sale)
    if not items:
        flash(request, "Agregá al menos un producto vendido.", "error")
        return _rerender(request, partner, form, status_code=400, sale=sale)

    for field in (
        "date", "customer", "channel", "payment_method", "status", "invoice_number", "notes",
    ):
        setattr(sale, field, getattr(data, field))
    sale.items.clear()
    for it in items:
        sale.items.append(SaleItem(**it))
    try:
        _apply_vat(sale, form)  # usa sale.total_ars con los ítems nuevos
    except ValueError as exc:
        flash(request, str(exc), "error")
        return _rerender(request, partner, form, status_code=400, sale=sale)
    record(db, obj=sale, action="update", changed_by=partner.username,
           summary=f"Edición de venta #{sale.id}", old=before)
    db.commit()
    return redirect(f"/ventas/{sale.id}", request, "Venta actualizada.")


@router.post("/{sale_id}/eliminar")
async def delete_sale(
    sale_id: int,
    request: Request,
    partner: Partner = Depends(require_owner),
    db: Session = Depends(get_db),
):
    sale = _load(db, sale_id)
    if not sale:
        flash(request, "No se encontró la venta.", "error")
        return redirect("/ventas")
    from app.models import Document
    from app.storage import delete_file

    for doc in db.scalars(
        select(Document).where(Document.entity_type == "sale", Document.entity_id == sale.id)
    ):
        delete_file(doc.file_reference)
        db.delete(doc)
    record(db, obj=sale, action="delete", changed_by=partner.username,
           summary=f"Baja de venta #{sale.id}", old=snapshot(sale))
    db.delete(sale)
    db.commit()
    return redirect("/ventas", request, "Venta eliminada.")
