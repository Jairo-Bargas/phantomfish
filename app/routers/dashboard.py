"""Tablero principal (equivalente a Resumen_Socios)."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import get_current_partner
from app.database import get_db
from app.models import Partner, Payment, Purchase, Sale, Settlement
from app.services.periods import last_month, month_bounds, month_label, this_month
from app.services.summary import build_summary
from app.web import render

router = APIRouter()


def _parse_date(value: str | None) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        return None


@router.get("/")
async def dashboard(
    request: Request,
    desde: str | None = None,
    hasta: str | None = None,
    mes: str | None = None,
    partner: Partner = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    if mes:
        m_from, m_to = month_bounds(mes)
        if m_from:
            desde, hasta = m_from.isoformat(), m_to.isoformat()
    date_from = _parse_date(desde)
    date_to = _parse_date(hasta)
    summary = build_summary(db, date_from=date_from, date_to=date_to)

    recent_payments = list(
        db.scalars(select(Payment).order_by(Payment.date.desc(), Payment.id.desc()).limit(5))
    )
    pending_shipments = list(
        db.scalars(
            select(Purchase)
            .where(Purchase.shipment_status != "recibido")
            .order_by(Purchase.date.desc())
            .limit(5)
        )
    )
    counts = {
        "payments": db.scalar(select(func.count()).select_from(Payment)),
        "purchases": db.scalar(select(func.count()).select_from(Purchase)),
        "sales": db.scalar(select(func.count()).select_from(Sale)),
        "settlements": db.scalar(select(func.count()).select_from(Settlement)),
    }

    return render(
        request,
        "dashboard.html",
        {
            "partner": partner,
            "active_nav": "dashboard",
            "summary": summary,
            "recent_payments": recent_payments,
            "pending_shipments": pending_shipments,
            "counts": counts,
            "desde": desde or "",
            "hasta": hasta or "",
            "mes": mes or "",
            "periodo_label": month_label(mes) if mes else "",
            "mes_actual": this_month(),
            "mes_pasado": last_month(),
        },
        db=db,
    )
