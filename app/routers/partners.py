"""Socios: ver y ajustar porcentajes de reparto."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import record
from app.auth import get_current_partner
from app.database import get_db
from app.models import AuditLog, Partner
from app.services.settlements import list_settlements
from app.services.summary import build_summary
from app.web import flash, redirect, render

router = APIRouter(prefix="/socios")


@router.get("")
async def list_partners(
    request: Request,
    partner: Partner = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    partners = list(db.scalars(select(Partner).order_by(Partner.id)))
    total_pct = sum((p.pct_share for p in partners if p.active), Decimal(0))
    recent_audit = list(
        db.scalars(select(AuditLog).order_by(AuditLog.changed_at.desc()).limit(30))
    )
    summary = build_summary(db)
    recent_settlements = list_settlements(db, limit=6)
    return render(
        request,
        "partners/list.html",
        {
            "partner": partner,
            "active_nav": "socios",
            "partners": partners,
            "total_pct": total_pct,
            "recent_audit": recent_audit,
            "summary": summary,
            "recent_settlements": recent_settlements,
        },
        db=db,
    )


@router.post("/porcentajes")
async def update_percentages(
    request: Request,
    partner: Partner = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    form = dict((await request.form()).multi_items())
    partners = list(db.scalars(select(Partner).where(Partner.active.is_(True)).order_by(Partner.id)))
    new_values: dict[int, Decimal] = {}
    try:
        for p in partners:
            raw = str(form.get(f"pct_{p.id}", "")).strip().replace(",", ".")
            new_values[p.id] = Decimal(raw).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        flash(request, "Porcentaje inválido.", "error")
        return redirect("/socios")

    total = sum(new_values.values(), Decimal(0))
    if total != Decimal("100.00"):
        flash(request, f"Los porcentajes tienen que sumar 100 (suman {total}).", "error")
        return redirect("/socios")

    changed = []
    for p in partners:
        if p.pct_share != new_values[p.id]:
            changed.append(f"{p.name}: {p.pct_share} → {new_values[p.id]}")
            p.pct_share = new_values[p.id]
    if changed:
        record(db, obj=partners[0], action="update", changed_by=partner.username,
               summary="Cambio de porcentajes de reparto: " + "; ".join(changed))
        db.commit()
        flash(request, "Porcentajes actualizados. (No afecta pagos ya cargados.)")
    else:
        flash(request, "No hubo cambios.", "info")
    return redirect("/socios")
