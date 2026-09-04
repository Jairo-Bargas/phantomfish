"""Subida, descarga y borrado de comprobantes."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.audit import record
from app.auth import get_current_accountant_optional, get_current_partner, get_current_partner_optional
from app.constants import ENTITY_TYPES
from app.database import get_db
from app.models import Accountant, Document, Partner, Payment, Purchase, Sale, Settlement
from app.services.documents import attach_files, remove_document
from app.storage import absolute_path
from app.web import flash, redirect

router = APIRouter(prefix="/comprobantes")

_MODEL = {"payment": Payment, "purchase": Purchase, "sale": Sale, "settlement": Settlement}
_BACK = {
    "payment": "/pagos",
    "purchase": "/compras",
    "sale": "/ventas",
    "settlement": "/socios/movimientos",
}


@router.post("/{entity_type}/{entity_id}")
async def upload(
    entity_type: str,
    entity_id: int,
    request: Request,
    partner: Partner = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    if entity_type not in ENTITY_TYPES:
        flash(request, "Tipo inválido.", "error")
        return redirect("/")
    entity = db.get(_MODEL[entity_type], entity_id)
    if not entity:
        flash(request, "No se encontró el registro.", "error")
        return redirect(_BACK[entity_type])

    form = await request.form()
    files: list[UploadFile] = form.getlist("comprobantes")  # type: ignore
    label = getattr(entity, "concept", None) or getattr(entity, "supplier", None) or (
        getattr(entity, "customer", None) or entity_type
    )
    on_date = getattr(entity, "date", dt.date.today())
    saved, errors = await attach_files(
        db, files=files, entity_type=entity_type, entity_id=entity_id,
        label=label, on_date=on_date, uploaded_by=partner.username,
    )
    for e in errors:
        flash(request, e, "error")
    if saved:
        record(db, obj=entity, action="update", changed_by=partner.username,
               summary=f"Adjuntó {saved} comprobante/s")
        db.commit()
        flash(request, f"{saved} comprobante/s subido/s.")
    return redirect(f"{_BACK[entity_type]}/{entity_id}")


_ACCOUNTANT_ENTITY_TYPES = {"payment", "sale"}


@router.get("/{doc_id}/ver")
async def view_document(
    doc_id: int,
    partner: Partner | None = Depends(get_current_partner_optional),
    accountant: Accountant | None = Depends(get_current_accountant_optional),
    db: Session = Depends(get_db),
):
    if partner is None and accountant is None:
        return redirect("/login")
    doc = db.get(Document, doc_id)
    if not doc:
        return redirect("/")
    if partner is None and doc.entity_type not in _ACCOUNTANT_ENTITY_TYPES:
        return redirect("/contadora")
    path = absolute_path(doc.file_reference)
    if not path.exists():
        return redirect("/")
    return FileResponse(
        path,
        media_type=doc.content_type or "application/octet-stream",
        filename=doc.original_filename,
        content_disposition_type="inline",
    )


@router.post("/{doc_id}/eliminar")
async def delete_document(
    doc_id: int,
    request: Request,
    partner: Partner = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    doc = db.get(Document, doc_id)
    if not doc:
        return redirect("/")
    entity_type, entity_id = doc.entity_type, doc.entity_id
    remove_document(db, doc)
    db.commit()
    flash(request, "Comprobante eliminado.")
    back = _BACK.get(entity_type, "/")
    return redirect(f"{back}/{entity_id}")
