"""Adjuntar / listar / borrar comprobantes de cualquier entidad."""

from __future__ import annotations

import datetime as dt

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Document
from app.storage import UploadError, delete_file, save_upload

_ENTITY_LABEL = {"payment": "pago", "purchase": "compra", "sale": "venta"}


async def attach_files(
    db: Session,
    *,
    files: list[UploadFile] | None,
    entity_type: str,
    entity_id: int,
    label: str,
    on_date: dt.date | None,
    uploaded_by: str | None,
) -> tuple[int, list[str]]:
    """Guarda los archivos válidos. Devuelve (cantidad_ok, [errores])."""
    saved = 0
    errors: list[str] = []
    for file in files or []:
        if not file or not file.filename:
            continue
        try:
            meta = await save_upload(
                file,
                entity_type=entity_type,
                entity_id=entity_id,
                label=label,
                on_date=on_date,
            )
        except UploadError as exc:
            errors.append(f"{file.filename}: {exc}")
            continue
        db.add(
            Document(
                entity_type=entity_type,
                entity_id=entity_id,
                uploaded_by=uploaded_by,
                **meta,
            )
        )
        saved += 1
    return saved, errors


def list_documents(db: Session, entity_type: str, entity_id: int) -> list[Document]:
    return list(
        db.scalars(
            select(Document)
            .where(Document.entity_type == entity_type, Document.entity_id == entity_id)
            .order_by(Document.id)
        )
    )


def remove_document(db: Session, doc: Document) -> None:
    delete_file(doc.file_reference)
    db.delete(doc)
