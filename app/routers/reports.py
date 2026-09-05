"""Reporte por mes / período."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.auth import get_current_partner
from app.database import get_db
from app.money import ZERO, money
from app.models import Partner, Payment
from app.services.periods import month_bounds, month_label, month_options
from app.services.settlements import list_settlements
from app.services.summary import build_summary
from app.services.vat import vat_by_month, vat_totals
from app.web import render

router = APIRouter()


def _date(value: str | None) -> dt.date | None:
    try:
        return dt.date.fromisoformat(value) if value else None
    except ValueError:
        return None


@router.get("/reporte")
async def monthly_report(
    request: Request,
    mes: str | None = None,
    desde: str | None = None,
    hasta: str | None = None,
    partner: Partner = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    # Sin filtro por defecto: se ve todo el histórico. El usuario elige el mes.
    use_range = bool(desde or hasta)
    if use_range:
        date_from, date_to = _date(desde), _date(hasta)
        titulo = "Período personalizado"
    elif mes:
        date_from, date_to = month_bounds(mes)
        titulo = month_label(mes) or "Reporte"
    else:
        date_from = date_to = None
        titulo = "Todo el histórico"

    summary = build_summary(db, date_from=date_from, date_to=date_to)

    # Los gastos personales de un socio no son costo del negocio.
    pay_stmt = select(Payment).options(selectinload(Payment.contributions)).where(
        Payment.expense_type != "personal"
    )
    if date_from:
        pay_stmt = pay_stmt.where(Payment.date >= date_from)
    if date_to:
        pay_stmt = pay_stmt.where(Payment.date <= date_to)
    payments = list(db.scalars(pay_stmt.order_by(Payment.date, Payment.id)))

    by_category: dict[str, dict] = {}
    by_type = {
        "importacion": {"ars": ZERO, "usd": ZERO, "count": 0},
        "operativo": {"ars": ZERO, "usd": ZERO, "count": 0},
    }
    for p in payments:
        row = by_category.setdefault(p.category, {"ars": ZERO, "usd": ZERO, "count": 0})
        row["ars"] = money(row["ars"] + p.amount_ars)
        row["usd"] = money(row["usd"] + p.amount_usd)
        row["count"] += 1
        t = by_type["importacion"] if p.order_id else by_type["operativo"]
        t["ars"] = money(t["ars"] + p.amount_ars)
        t["usd"] = money(t["usd"] + p.amount_usd)
        t["count"] += 1
    by_category_sorted = sorted(by_category.items(), key=lambda kv: kv[1]["ars"], reverse=True)

    settlements = list_settlements(db, date_from=date_from, date_to=date_to)

    export_qs = ""
    if use_range:
        parts = [f"desde={desde}" if desde else "", f"hasta={hasta}" if hasta else ""]
        export_qs = "&".join(x for x in parts if x)
    elif mes:
        export_qs = f"mes={mes}"

    return render(
        request,
        "reports/monthly.html",
        {
            "partner": partner,
            "active_nav": "reporte",
            "titulo": titulo,
            "mes": mes or "",
            "desde": desde or "",
            "hasta": hasta or "",
            "use_range": use_range,
            "summary": summary,
            "payments": payments,
            "by_category": by_category_sorted,
            "by_type": by_type,
            "settlements": settlements,
            "months": month_options(mes),
            "export_qs": export_qs,
            "vat_period": vat_totals(db, date_from=date_from, date_to=date_to),
            "vat_total": vat_totals(db),
            "vat_months": vat_by_month(db, 12),
        },
        db=db,
    )
