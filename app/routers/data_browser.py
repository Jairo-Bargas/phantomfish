"""Visor de tablas en crudo (solo lectura), para controlar la base 'como un Excel'."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.auth import get_current_partner
from app.database import engine, get_db
from app.models import Partner
from app.web import render

router = APIRouter(prefix="/datos")

_HIDDEN_COLUMNS = {"password_hash"}
_PAGE_SIZE = 200


def _table_names() -> list[str]:
    return sorted(inspect(engine).get_table_names())


@router.get("")
async def index(
    request: Request,
    tabla: str | None = None,
    pagina: int = 1,
    partner: Partner = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    tables = _table_names()
    selected = tabla if tabla in tables else (tables[0] if tables else None)
    rows: list[dict] = []
    columns: list[str] = []
    total = 0
    pagina = max(1, pagina)

    if selected:
        insp = inspect(engine)
        columns = [
            c["name"] for c in insp.get_columns(selected) if c["name"] not in _HIDDEN_COLUMNS
        ]
        total = db.scalar(text(f'SELECT COUNT(*) FROM "{selected}"')) or 0
        col_sql = ", ".join(f'"{c}"' for c in columns)
        offset = (pagina - 1) * _PAGE_SIZE
        result = db.execute(
            text(f'SELECT {col_sql} FROM "{selected}" ORDER BY 1 LIMIT :lim OFFSET :off'),
            {"lim": _PAGE_SIZE, "off": offset},
        )
        rows = [dict(r._mapping) for r in result]

    return render(
        request,
        "data_browser.html",
        {
            "partner": partner,
            "active_nav": "socios",
            "tables": tables,
            "selected": selected,
            "columns": columns,
            "rows": rows,
            "total": total,
            "pagina": pagina,
            "page_size": _PAGE_SIZE,
            "has_next": selected is not None and pagina * _PAGE_SIZE < total,
        },
    )
