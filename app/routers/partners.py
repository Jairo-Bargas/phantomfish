"""Socios: ver y ajustar porcentajes de reparto."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

import re
import unicodedata

from app.audit import record
from app.auth import get_current_partner, hash_password, require_owner
from app.database import get_db
from app.models import Accountant, AuditLog, Partner
from app.services.settlements import list_settlements
from app.web import flash, redirect, render

router = APIRouter(prefix="/socios")


def _slug_username(label: str) -> str:
    text = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "", text).lower()
    return (text[:40] or "contadora")


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


# ------------------------------------------------------------- acceso de la contadora


@router.get("/contadora")
async def accountant_admin(
    request: Request,
    partner: Partner = Depends(require_owner),
    db: Session = Depends(get_db),
):
    accountants = list(db.scalars(select(Accountant).order_by(Accountant.id)))
    return render(
        request,
        "partners/accountant.html",
        {"partner": partner, "active_nav": "socios", "accountants": accountants},
        db=db,
    )


@router.post("/contadora")
async def accountant_create(
    request: Request,
    partner: Partner = Depends(require_owner),
    db: Session = Depends(get_db),
):
    form = dict((await request.form()).multi_items())
    name = (form.get("name") or "").strip()
    if not name:
        flash(request, "Poné el nombre de la contadora.", "error")
        return redirect("/socios/contadora")
    username = (form.get("username") or "").strip().lower() or _slug_username(name)
    password = (form.get("password") or "").strip()
    if len(password) < 6:
        flash(request, "La contraseña inicial tiene que tener al menos 6 caracteres.", "error")
        return redirect("/socios/contadora")
    if db.scalar(select(Accountant).where(Accountant.username == username)):
        flash(request, f"Ya existe un usuario '{username}'.", "error")
        return redirect("/socios/contadora")

    acc = Accountant(
        name=name, username=username, password_hash=hash_password(password),
        must_change_password=True, active=True,
    )
    db.add(acc)
    db.flush()
    record(db, obj=acc, action="insert", changed_by=partner.username,
           summary=f"Alta de usuario contadora: {acc.name} ({acc.username})")
    db.commit()
    return redirect("/socios/contadora", request,
                    f"Usuario creado: {username}. Pasale el usuario y esta contraseña inicial.")


@router.post("/contadora/{accountant_id}/reset")
async def accountant_reset(
    accountant_id: int,
    request: Request,
    partner: Partner = Depends(require_owner),
    db: Session = Depends(get_db),
):
    acc = db.get(Accountant, accountant_id)
    if not acc:
        return redirect("/socios/contadora")
    form = dict((await request.form()).multi_items())
    password = (form.get("password") or "").strip()
    if len(password) < 6:
        flash(request, "La contraseña tiene que tener al menos 6 caracteres.", "error")
        return redirect("/socios/contadora")
    acc.password_hash = hash_password(password)
    acc.must_change_password = True
    record(db, obj=acc, action="update", changed_by=partner.username,
           summary=f"Reseteo de contraseña de contadora: {acc.username}")
    db.commit()
    return redirect("/socios/contadora", request, f"Contraseña reseteada para {acc.username}.")


@router.post("/contadora/{accountant_id}/activar")
async def accountant_toggle(
    accountant_id: int,
    request: Request,
    partner: Partner = Depends(require_owner),
    db: Session = Depends(get_db),
):
    acc = db.get(Accountant, accountant_id)
    if not acc:
        return redirect("/socios/contadora")
    acc.active = not acc.active
    estado = "activado" if acc.active else "desactivado"
    record(db, obj=acc, action="update", changed_by=partner.username,
           summary=f"Usuario contadora {estado}: {acc.username}")
    db.commit()
    return redirect("/socios/contadora", request, f"Usuario {estado}.")
