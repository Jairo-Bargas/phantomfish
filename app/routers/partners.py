"""Socios: ver y ajustar porcentajes de reparto."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

import re
import unicodedata

from app.audit import record
from app.auth import get_current_partner, hash_password, require_owner
from app.constants import PASE_COLON_ARS, PASE_COLON_UYU
from app.database import get_db
from app.models import Accountant, AuditLog, PaseColon, Partner
from app.money import ZERO, money
from app.services.pases import pase_saldo
from app.services.payments import active_partners
from app.services.settlements import list_settlements
from app.services.summary import aportes_breakdown, socios_saldo
from app.web import flash, redirect, render


def _cur(value: Decimal, prefix: str) -> str:
    d = money(value)
    entero, _, dec = f"{abs(d):.2f}".partition(".")
    return ("-" if d < 0 else "") + f"{prefix} " + f"{int(entero):,}".replace(",", ".") + f",{dec}"


def _parse_money(value: str | None) -> Decimal:
    v = str(value or "").strip().replace(" ", "")
    if not v:
        return ZERO
    if "," in v and v.rfind(",") > v.rfind("."):
        v = v.replace(".", "").replace(",", ".")
    else:
        v = v.replace(",", "")
    try:
        return money(v)
    except (ValueError, ArithmeticError):
        return ZERO


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
    active = active_partners(db)

    saldo = socios_saldo(db)
    ps = pase_saldo(db, active)
    pases = list(
        db.scalars(select(PaseColon).order_by(PaseColon.date.desc(), PaseColon.id.desc()).limit(8))
    )
    pase_recap = {
        "prefill_ars": f"{PASE_COLON_ARS:.0f}",
        "prefill_uyu": f"{PASE_COLON_UYU:.0f}",
        "count": ps.count,
        "count_mes": ps.count_mes,
        "total_ars": ps.total_ars,
        "total_uyu": ps.total_uyu,
        "ultima": ps.ultima,
        "recientes": pases,
    }

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
            "saldo": saldo,
            "pase": pase_recap,
        },
        db=db,
    )


@router.get("/saldo")
async def saldo_detalle(
    request: Request,
    partner: Partner = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    """De dónde sale el saldo entre socios: pago por pago + pasada por pasada."""
    active = active_partners(db)
    saldo = socios_saldo(db)
    aportes = aportes_breakdown(db, active)
    pases = list(
        db.scalars(select(PaseColon).order_by(PaseColon.date.desc(), PaseColon.id.desc()))
    )
    b_pct = (
        Decimal(str(active[1].pct_share)) / Decimal(100) if len(active) > 1 else Decimal("0.65")
    )
    a_pct = (
        Decimal(str(active[0].pct_share)) / Decimal(100) if active else Decimal("0.35")
    )
    return render(
        request,
        "partners/saldo.html",
        {
            "partner": partner,
            "active_nav": "socios",
            "saldo": saldo,
            "aportes": aportes,
            "pases": pases,
            "a_pct": a_pct,
            "b_pct": b_pct,
            "socio_a_id": active[0].id if active else 0,
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


@router.post("/pase-colon")
async def register_pase_colon(
    request: Request,
    partner: Partner = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    """Registra una pasada al puente de Colón. La paga el socio que la registra:
    su parte queda saldada y la del otro socio queda pendiente. Se guarda en las
    dos monedas por separado (pesos y/o pesos uruguayos), sin conversión."""
    partners = active_partners(db)
    if len(partners) < 2:
        flash(request, "Necesitás los dos socios activos para registrar una pasada.", "error")
        return redirect("/socios")

    form = dict((await request.form()).multi_items())
    ars = _parse_money(form.get("ars"))
    uyu = _parse_money(form.get("uyu"))
    if ars <= ZERO and uyu <= ZERO:
        flash(request, "Poné el monto del pase (en pesos y/o en pesos uruguayos).", "error")
        return redirect("/socios")

    row = PaseColon(
        date=dt.date.today(),
        paid_by_partner_id=partner.id,
        amount_ars=ars,
        amount_uyu=uyu,
        created_by=partner.username,
    )
    db.add(row)
    db.flush()
    montos = " + ".join(
        x for x in [_cur(ars, "$") if ars > ZERO else "", _cur(uyu, "$U") if uyu > ZERO else ""] if x
    )
    record(db, obj=row, action="insert", changed_by=partner.username,
           summary=f"Pase Colón (pagó {partner.name}): {montos}")
    db.commit()

    other = next(p for p in partners if p.id != partner.id)
    pct = Decimal(str(other.pct_share)) / Decimal(100)
    partes = " + ".join(
        x for x in [
            _cur(money(ars * pct), "$") if ars > ZERO else "",
            _cur(money(uyu * pct), "$U") if uyu > ZERO else "",
        ] if x
    )
    flash(request,
          f"Pase Colón registrado ({montos}). Lo pagaste vos; "
          f"la parte de {other.name} ({other.pct_share:.0f}%) = {partes} queda pendiente.")
    return redirect("/socios")


@router.post("/pase-colon/{pase_id}/eliminar")
async def delete_pase_colon(
    pase_id: int,
    request: Request,
    partner: Partner = Depends(require_owner),
    db: Session = Depends(get_db),
):
    row = db.get(PaseColon, pase_id)
    if row:
        record(db, obj=row, action="delete", changed_by=partner.username,
               summary=f"Pase Colón #{row.id} eliminado")
        db.delete(row)
        db.commit()
        flash(request, "Pase eliminado.")
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
