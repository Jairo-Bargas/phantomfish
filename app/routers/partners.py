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
from app.constants import PASE_COLON_ARS
from app.database import get_db
from app.models import Accountant, AuditLog, Partner, Payment
from app.money import ZERO, dsum, money
from app.services.payments import active_partners, apply_contributions, compute_amounts
from app.services.settlements import list_settlements
from app.services.summary import build_summary
from app.web import flash, redirect, render

_PASE_CATEGORY = "pase_colon"


def _ars(value: Decimal) -> str:
    d = money(value)
    entero, _, dec = f"{abs(d):.2f}".partition(".")
    return ("-" if d < 0 else "") + "$ " + f"{int(entero):,}".replace(",", ".") + f",{dec}"

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

    # saldo de aportes (neto de los pagos compartidos) — quién le debe a quién
    summary = build_summary(db)
    ranked = sorted(summary.partners, key=lambda x: x.balance)
    aportes = {"partners": summary.partners, "deudor": None, "acreedor": None, "monto": ZERO}
    if ranked and ranked[0].balance < -Decimal("0.5") and ranked[-1].balance > Decimal("0.5"):
        aportes["deudor"] = ranked[0].name
        aportes["acreedor"] = ranked[-1].name
        aportes["monto"] = ranked[-1].balance

    # recap de pases a Colón
    pases = list(
        db.scalars(select(Payment).where(Payment.category == _PASE_CATEGORY)
                   .order_by(Payment.date.desc(), Payment.id.desc()))
    )
    month0 = dt.date.today().replace(day=1)
    pases_mes = [p for p in pases if p.date >= month0]
    pase = {
        "monto": money(PASE_COLON_ARS),
        "count_total": len(pases),
        "count_mes": len(pases_mes),
        "total_mes": dsum(p.amount_ars for p in pases_mes),
        "ultima": pases[0].date if pases else None,
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
            "aportes": aportes,
            "pase": pase,
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
    """Registra una pasada al puente de Colón: la paga el socio que toca el
    botón (su parte queda saldada) y la parte del otro socio queda pendiente."""
    partners = active_partners(db)
    if len(partners) < 2:
        flash(request, "Necesitás los dos socios activos para registrar una pasada.", "error")
        return redirect("/socios")

    total = money(PASE_COLON_ARS)
    amounts = compute_amounts(currency_charged="ARS", amount_original=total, exchange_rate=ZERO)
    pay = Payment(
        date=dt.date.today(),
        concept=f"Pase Colón — pagó {partner.name}",
        category=_PASE_CATEGORY,
        currency_charged="ARS",
        amount_original=total,
        exchange_rate=amounts.exchange_rate,
        exchange_rate_type="oficial",
        amount_ars=amounts.amount_ars,
        amount_usd=amounts.amount_usd,
        status="pagado",
        billable=False,
        expense_type="negocio",
        created_by=partner.username,
    )
    # el que toca el botón puso el 100%; el reparto "que correspondía" es 35/65
    apply_contributions(db, pay, {p.id: (total if p.id == partner.id else ZERO) for p in partners})
    db.add(pay)
    db.flush()
    record(db, obj=pay, action="insert", changed_by=partner.username,
           summary=f"Pase Colón registrado (pagó {partner.name})")
    db.commit()

    other = next(p for p in partners if p.id != partner.id)
    otra_parte = money(total * Decimal(str(other.pct_share)) / Decimal(100))
    flash(request,
          f"Pase Colón registrado ({_ars(total)}). Lo pagaste vos; "
          f"la parte de {other.name} ({other.pct_share:.0f}%) = {_ars(otra_parte)} queda pendiente.")
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
