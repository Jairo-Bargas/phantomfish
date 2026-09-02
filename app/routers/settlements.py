"""Movimientos entre socios (devoluciones / pagos de una parte al otro).

Es solo un registro con comprobantes: NO afecta ningún cálculo de la app.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import record, snapshot
from app.auth import get_current_partner, require_owner
from app.constants import valid_codes
from app.database import get_db
from app.money import money, rate
from app.models import Partner, Payment, Settlement
from app.services.documents import attach_files, list_documents
from app.services.payments import settlement_ars
from app.services.settlements import last_rate, list_settlements, load_settlement
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


def _recent_payments(db: Session) -> list[Payment]:
    return list(
        db.scalars(select(Payment).order_by(Payment.date.desc(), Payment.id.desc()).limit(60))
    )


def _form_ctx(db: Session, partner: Partner, form: dict, settlement=None):
    partners = list(db.scalars(select(Partner).order_by(Partner.id)))
    return {
        "partner": partner,
        "active_nav": "socios",
        "partners": partners,
        "settlement": settlement,
        "form": form,
        "payments": _recent_payments(db),
        "last_usd": last_rate(db, "USD"),
        "last_uyu": last_rate(db, "UYU"),
    }


def _parse_settlement(db: Session, form: dict) -> dict:
    ids = {p.id for p in db.scalars(select(Partner))}
    from_id = int(form.get("from_partner_id") or 0)
    to_id = int(form.get("to_partner_id") or 0)
    if from_id not in ids or to_id not in ids:
        raise ValueError("Elegí los dos socios.")
    if from_id == to_id:
        raise ValueError("El que paga y el que recibe no pueden ser el mismo socio.")

    currency = (form.get("currency") or "ARS").upper()
    if currency not in valid_codes("settlement_currency"):
        currency = "ARS"
    amount_original = _parse_amount(str(form.get("amount_original") or form.get("amount_ars") or ""))
    if currency == "ARS":
        exch = rate(1)
    else:
        exch = rate(str(form.get("exchange_rate") or "0").replace(",", "."))
        if exch <= 0:
            raise ValueError("Poné la cotización a pesos argentinos (cuántos $ por cada unidad).")
    amount_ars = settlement_ars(currency, amount_original, exch)

    method = form.get("method") or "transferencia"
    if method not in valid_codes("settlement_method"):
        method = "otro"

    payment_id = None
    raw_pay = form.get("payment_id")
    if raw_pay:
        try:
            pid = int(raw_pay)
            if db.get(Payment, pid):
                payment_id = pid
        except (ValueError, TypeError):
            payment_id = None

    return {
        "date": dt.date.fromisoformat(form.get("date") or dt.date.today().isoformat()),
        "from_partner_id": from_id,
        "to_partner_id": to_id,
        "currency": currency,
        "amount_original": amount_original,
        "exchange_rate": exch,
        "amount_ars": amount_ars,
        "method": method,
        "payment_id": payment_id,
        "concept": (form.get("concept") or "").strip() or None,
        "notes": (form.get("notes") or "").strip() or None,
    }


# --------------------------------------------------------------------------- list


@router.get("")
async def list_view(
    request: Request,
    partner: Partner = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    return render(
        request,
        "settlements/list.html",
        {"partner": partner, "active_nav": "socios", "settlements": list_settlements(db)},
        db=db,
    )


# ---------------------------------------------------------------------------- new


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
    form = {
        "date": dt.date.today().isoformat(),
        "from_partner_id": str(other.id),
        "to_partner_id": str(partner.id),
        "method": "transferencia",
        "currency": "ARS",
        "payment_id": request.query_params.get("pago", ""),
    }
    return render(request, "settlements/form.html", _form_ctx(db, partner, form), db=db)


@router.post("")
async def create_view(
    request: Request,
    partner: Partner = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    form_data = await request.form()
    form = dict(form_data.multi_items())
    files: list[UploadFile] = form_data.getlist("comprobantes")  # type: ignore
    try:
        data = _parse_settlement(db, form)
    except ValueError as exc:
        flash(request, str(exc), "error")
        return render(request, "settlements/form.html", _form_ctx(db, partner, form),
                      status_code=400, db=db)

    settlement = Settlement(created_by=partner.username, **data)
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
           summary=f"Movimiento entre socios: {money(settlement.amount_ars)} ARS")
    db.commit()
    msg = f"Movimiento registrado ({saved} comprobante/s)." if saved else "Movimiento registrado."
    return redirect(f"/socios/movimientos/{settlement.id}", request, msg)


# --------------------------------------------------------------------------- edit


@router.get("/{settlement_id}/editar")
async def edit_view(
    settlement_id: int,
    request: Request,
    partner: Partner = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    s = load_settlement(db, settlement_id)
    if not s:
        return redirect("/socios/movimientos")
    form = {
        "date": s.date.isoformat(),
        "from_partner_id": str(s.from_partner_id),
        "to_partner_id": str(s.to_partner_id),
        "method": s.method,
        "currency": s.currency or "ARS",
        "amount_original": f"{(s.amount_original or s.amount_ars):.2f}",
        "exchange_rate": f"{(s.exchange_rate or Decimal(1)).normalize():f}",
        "payment_id": str(s.payment_id or ""),
        "concept": s.concept or "",
        "notes": s.notes or "",
    }
    return render(request, "settlements/form.html", _form_ctx(db, partner, form, s), db=db)


@router.post("/{settlement_id}")
async def update_view(
    settlement_id: int,
    request: Request,
    partner: Partner = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    s = load_settlement(db, settlement_id)
    if not s:
        return redirect("/socios/movimientos")
    form = dict((await request.form()).multi_items())
    before = snapshot(s)
    try:
        data = _parse_settlement(db, form)
    except ValueError as exc:
        flash(request, str(exc), "error")
        return render(request, "settlements/form.html", _form_ctx(db, partner, form, s),
                      status_code=400, db=db)
    for k, v in data.items():
        setattr(s, k, v)
    record(db, obj=s, action="update", changed_by=partner.username,
           summary=f"Edición de movimiento entre socios #{s.id}", old=before)
    db.commit()
    return redirect(f"/socios/movimientos/{s.id}", request, "Movimiento actualizado.")


# -------------------------------------------------------------------------- detail


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
    linked = db.get(Payment, settlement.payment_id) if settlement.payment_id else None
    return render(
        request,
        "settlements/detail.html",
        {
            "partner": partner,
            "active_nav": "socios",
            "settlement": settlement,
            "linked_payment": linked,
            "documents": list_documents(db, "settlement", settlement.id),
        },
        db=db,
    )


@router.post("/{settlement_id}/eliminar")
async def delete_view(
    settlement_id: int,
    request: Request,
    partner: Partner = Depends(require_owner),
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
