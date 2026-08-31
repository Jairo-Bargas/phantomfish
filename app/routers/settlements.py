"""Movimientos entre socios (devoluciones / pagos de una parte al otro)."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import record, snapshot
from app.auth import get_current_partner
from app.constants import valid_codes
from app.database import get_db
from app.money import money
from app.models import Partner, Settlement
from app.services.documents import attach_files, list_documents
from app.services.settlements import list_settlements, load_settlement
from app.services.summary import build_summary
from app.web import flash, redirect, render

router = APIRouter(prefix="/socios/movimientos")


def _parse_amount(value: str) -> Decimal:
    v = str(value or "").strip().replace(" ", "")
    if not v:
        raise ValueError("Falta el monto.")
    if "," in v and v.rfind(",") > v.rfind("."):
        v = v.replace(".", "").replace(",", ".")
    else:
        v = v.replace(",", "")
    try:
        d = money(v)
    except (InvalidOperation, ValueError):
        raise ValueError(f"Monto inválido ({value!r}).") from None
    if d <= 0:
        raise ValueError("El monto tiene que ser mayor a cero.")
    return d


@router.get("")
async def list_view(
    request: Request,
    partner: Partner = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    settlements = list_settlements(db)
    summary = build_summary(db)
    return render(
        request,
        "settlements/list.html",
        {
            "partner": partner,
            "active_nav": "socios",
            "settlements": settlements,
            "summary": summary,
        },
        db=db,
    )


@router.get("/nuevo")
async def new_view(
    request: Request,
    partner: Partner = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    partners = list(db.scalars(select(Partner).where(Partner.active.is_(True)).order_by(Partner.id)))
    if len(partners) < 2:
        return redirect("/socios", request, "Necesitás dos socios activos.", "error")
    other = next((p for p in partners if p.id != partner.id), partners[0])
    return render(
        request,
        "settlements/form.html",
        {
            "partner": partner,
            "active_nav": "socios",
            "partners": partners,
            "settlement": None,
            "form": {
                "date": dt.date.today().isoformat(),
                "from_partner_id": str(other.id),
                "to_partner_id": str(partner.id),
                "method": "transferencia",
            },
        },
        db=db,
    )


@router.post("")
async def create_view(
    request: Request,
    partner: Partner = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    form_data = await request.form()
    form = dict(form_data.multi_items())
    files: list[UploadFile] = form_data.getlist("comprobantes")  # type: ignore
    partners = list(db.scalars(select(Partner).order_by(Partner.id)))
    ids = {p.id for p in partners}

    try:
        from_id = int(form.get("from_partner_id") or 0)
        to_id = int(form.get("to_partner_id") or 0)
        if from_id not in ids or to_id not in ids:
            raise ValueError("Elegí los dos socios.")
        if from_id == to_id:
            raise ValueError("El que paga y el que recibe no pueden ser el mismo socio.")
        amount = _parse_amount(str(form.get("amount_ars") or ""))
        method = form.get("method") or "transferencia"
        if method not in valid_codes("settlement_method"):
            method = "otro"
        date = dt.date.fromisoformat(form.get("date") or dt.date.today().isoformat())
    except ValueError as exc:
        flash(request, str(exc), "error")
        return _rerender(request, db, partner, form, partners, 400)

    settlement = Settlement(
        date=date,
        from_partner_id=from_id,
        to_partner_id=to_id,
        amount_ars=amount,
        method=method,
        concept=(form.get("concept") or "").strip() or None,
        notes=(form.get("notes") or "").strip() or None,
        created_by=partner.username,
    )
    db.add(settlement)
    db.flush()

    saved, errors = await attach_files(
        db, files=files, entity_type="settlement", entity_id=settlement.id,
        label=settlement.concept or "devolucion-socio", on_date=settlement.date,
        uploaded_by=partner.username,
    )
    for e in errors:
        flash(request, e, "error")

    record(db, obj=settlement, action="insert", changed_by=partner.username,
           summary=f"Movimiento entre socios: {money(amount)} ARS")
    db.commit()
    msg = f"Movimiento registrado ({saved} comprobante/s)." if saved else "Movimiento registrado."
    return redirect(f"/socios/movimientos/{settlement.id}", request, msg)


def _rerender(request, db, partner, form, partners, status_code):
    return render(
        request,
        "settlements/form.html",
        {
            "partner": partner,
            "active_nav": "socios",
            "partners": partners,
            "settlement": None,
            "form": form,
        },
        status_code=status_code,
        db=db,
    )


@router.get("/{settlement_id}")
async def detail_view(
    settlement_id: int,
    request: Request,
    partner: Partner = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    settlement = load_settlement(db, settlement_id)
    if not settlement:
        return redirect("/socios/movimientos", request, "No se encontró el movimiento.", "error")
    docs = list_documents(db, "settlement", settlement.id)
    return render(
        request,
        "settlements/detail.html",
        {
            "partner": partner,
            "active_nav": "socios",
            "settlement": settlement,
            "documents": docs,
        },
        db=db,
    )


@router.post("/{settlement_id}/eliminar")
async def delete_view(
    settlement_id: int,
    request: Request,
    partner: Partner = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    settlement = load_settlement(db, settlement_id)
    if not settlement:
        return redirect("/socios/movimientos")
    from app.models import Document
    from app.storage import delete_file

    for doc in db.scalars(
        select(Document).where(
            Document.entity_type == "settlement", Document.entity_id == settlement.id
        )
    ):
        delete_file(doc.file_reference)
        db.delete(doc)

    record(db, obj=settlement, action="delete", changed_by=partner.username,
           summary=f"Baja de movimiento entre socios #{settlement.id}", old=snapshot(settlement))
    db.delete(settlement)
    db.commit()
    return redirect("/socios/movimientos", request, "Movimiento eliminado.")
