"""Exportar la planilla Excel con datos reales (opcionalmente filtrada por período)."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.auth import get_current_partner
from app.database import get_db
from app.models import Partner
from app.services.excel_export import build_workbook, filename
from app.services.periods import month_bounds

router = APIRouter()

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _date(value: str | None) -> dt.date | None:
    try:
        return dt.date.fromisoformat(value) if value else None
    except ValueError:
        return None


@router.get("/export/excel")
async def export_excel(
    mes: str | None = None,
    desde: str | None = None,
    hasta: str | None = None,
    partner: Partner = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    if mes and not (desde or hasta):
        date_from, date_to = month_bounds(mes)
    else:
        date_from, date_to = _date(desde), _date(hasta)

    content = build_workbook(db, date_from=date_from, date_to=date_to)
    return Response(
        content=content,
        media_type=XLSX_MIME,
        headers={
            "Content-Disposition": f'attachment; filename="{filename(date_from, date_to)}"'
        },
    )
