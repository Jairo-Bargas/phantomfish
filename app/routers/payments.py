"""Pagos y aportes de socios."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.audit import record, snapshot
from app.auth import get_current_partner, require_owner
from app.constants import valid_codes
from app.database import get_db
from app.money import ZERO, dsum, money, rate
from app.models import Partner, Payment
from app.services.categories import valid_category_codes
from app.services.documents import attach_files, list_documents
from app.services.exchange_rate import last_known
from app.services.orders import order_choices
from app.services.payments import (
    active_partners,
    apply_contributions,
    compute_amounts,
    default_split,
    last_rate_for_currency,
    parse_date,
)
from app.services.periods import month_bounds, month_label, month_options
from app.services.vat import DEFAULT_VAT_RATE, parse_rate, vat_from_total
from app.config import get_settings
from app.web import flash, redirect, render

router = APIRouter(prefix="/pagos")
settings = get_settings()


def _load_payment(db: Session, payment_id: int) -> Payment | None:
    from app.models import PaymentContribution

    return db.scalar(
        select(Payment)
        .options(
            selectinload(Payment.contributions).selectinload(PaymentContribution.partner),
            selectinload(Payment.purchases),
            selectinload(Payment.order),
            selectinload(Payment.paid_by),
        )
        .where(Payment.id == payment_id)
    )


def _parse_amount(value: str, field: str) -> Decimal:
    v = str(value or "").strip().replace(" ", "")
    if not v:
        raise ValueError(f"{field}: falta el número.")
    # "1.234,56" (formato es) -> "1234.56"
    if "," in v and v.rfind(",") > v.rfind("."):
        v = v.replace(".", "").replace(",", ".")
    else:
        v = v.replace(",", "")
    try:
        return money(v)
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field}: número inválido ({value!r}).") from None


def _parse_amount_opt(value: str | None, field: str) -> Decimal | None:
    """Como _parse_amount pero devuelve None si viene vacío."""
    if value is None or str(value).strip() == "":
        return None
    return _parse_amount(value, field)


def _vat_from_form(form: dict, total_ars: Decimal) -> tuple[Decimal | None, Decimal | None]:
    """(vat_amount, vat_rate) a partir del form. (None, None) si no discrimina IVA."""
    if not form.get("vat_discrimina"):
        return None, None
    rate_pct = parse_rate(form.get("vat_rate")) or DEFAULT_VAT_RATE
    manual = _parse_amount_opt(form.get("vat_amount_manual"), "IVA")
    vat_amount = manual if manual is not None else vat_from_total(total_ars, rate_pct)
    if vat_amount < ZERO:
        raise ValueError("El IVA no puede ser negativo.")
    if vat_amount > money(total_ars):
        raise ValueError("El IVA no puede ser mayor que el total.")
    return vat_amount, rate_pct


def _contribution_inputs(form: dict, partners: list[Partner]) -> dict[int, Decimal] | None:
    """Lee contribution_<id> del form. Devuelve None si no vino ninguno."""
    result: dict[int, Decimal] = {}
    found = False
    for p in partners:
        raw = form.get(f"contribution_{p.id}")
        if raw is None or raw == "":
            continue
        found = True
        result[p.id] = _parse_amount(str(raw), f"Aporte {p.name}")
    if not found:
        return None
    for p in partners:
        result.setdefault(p.id, ZERO)
    return result


# --------------------------------------------------------------------------- list


@router.get("")
async def list_payments(
    request: Request,
    q: str | None = None,
    categoria: str | None = None,
    estado: str | None = None,
    desde: str | None = None,
    hasta: str | None = None,
    mes: str | None = None,
    pedido: str | None = None,
    personales: str | None = None,
    partner: Partner = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    from app.models import Order, PaymentContribution

    if mes:
        m_from, m_to = month_bounds(mes)
        if m_from:
            desde = m_from.isoformat()
            hasta = m_to.isoformat()

    stmt = select(Payment).options(
        selectinload(Payment.contributions).selectinload(PaymentContribution.partner),
        selectinload(Payment.order),
    )
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(Payment.concept.ilike(like))
    if categoria:
        stmt = stmt.where(Payment.category == categoria)
    if estado:
        stmt = stmt.where(Payment.status == estado)
    if desde:
        stmt = stmt.where(Payment.date >= dt.date.fromisoformat(desde))
    if hasta:
        stmt = stmt.where(Payment.date <= dt.date.fromisoformat(hasta))

    pedido = (pedido or "").strip()
    pedido_label = ""
    if pedido == "sin":
        stmt = stmt.where(Payment.order_id.is_(None))
        pedido_label = "Solo operativos (sin pedido)"
    elif pedido == "con":
        stmt = stmt.where(Payment.order_id.is_not(None))
        pedido_label = "Todos los de pedidos"
    elif pedido.isdigit():
        o = db.get(Order, int(pedido))
        if o:
            stmt = stmt.where(Payment.order_id == o.id)
            pedido_label = o.display_name
        else:
            pedido = ""

    # Por defecto la lista muestra solo gastos del negocio; los personales de
    # cada socio (ej. su combustible) aparecen solo si se piden.
    personales = (personales or "").strip()
    if personales == "solo":
        stmt = stmt.where(Payment.expense_type == "personal")
    elif personales != "ver":
        stmt = stmt.where(Payment.expense_type != "personal")

    stmt = stmt.order_by(Payment.date.desc(), Payment.id.desc())
    payments = list(db.scalars(stmt))

    total_ars = dsum(p.amount_ars for p in payments)
    total_usd = dsum(p.amount_usd for p in payments)
    total_aportes = dsum(p.contributed_total for p in payments)

    return render(
        request,
        "payments/list.html",
        {
            "partner": partner,
            "active_nav": "pagos",
            "payments": payments,
            "total_ars": total_ars,
            "total_usd": total_usd,
            "total_aportes": total_aportes,
            "control_ok": abs(total_ars - total_aportes) <= Decimal("0.01"),
            "mes": mes or "",
            "mes_label": month_label(mes) if mes else "",
            "months": month_options(mes),
            "pedido": pedido,
            "pedido_label": pedido_label,
            "personales": personales,
            "orders": order_choices(db),
            "filters": {
                "q": q or "",
                "categoria": categoria or "",
                "estado": estado or "",
                "desde": desde or "",
                "hasta": hasta or "",
            },
        },
        db=db,
    )


# ---------------------------------------------------------------------------- new


def _rate_context(db: Session, rate_type: str) -> dict:
    """Sugerencia rápida desde el último registro guardado (sin llamar a la red).

    La consulta en vivo a dolarapi la hace el botón 'Traer de dolarapi' del formulario.
    """
    known = last_known(db, rate_type)
    if known:
        return {
            "suggested_rate": known.sell or known.buy,
            "rate_source": f"último registro {known.fetched_at:%d/%m %H:%M}",
        }
    return {"suggested_rate": None, "rate_source": None}


@router.get("/nuevo")
async def new_payment(
    request: Request,
    partner: Partner = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    partners = active_partners(db)
    preselect_order = request.query_params.get("pedido", "")
    ctx = {
        "partner": partner,
        "active_nav": "pagos",
        "partners": partners,
        "payment": None,
        "orders": order_choices(db),
        "form": {
            "date": dt.date.today().isoformat(),
            "currency_charged": "USD",
            "exchange_rate_type": settings.default_rate_type,
            "status": "pagado",
            "category": "importacion",
            "order_id": preselect_order,
            "billable": "1",
            "expense_type": "negocio",
        },
        "contributions": {p.id: ZERO for p in partners},
        "pct_by_partner": {str(p.id): str(p.pct_share) for p in partners},
        "last_uyu_rate": last_rate_for_currency(db, "UYU"),
    }
    ctx.update(_rate_context(db, settings.default_rate_type))
    return render(request, "payments/form.html", ctx, db=db)


@router.post("")
async def create_payment(
    request: Request,
    partner: Partner = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    form_data = await request.form()
    form = dict(form_data.multi_items())
    files_factura: list[UploadFile] = form_data.getlist("comprobantes_factura")  # type: ignore
    files_otros: list[UploadFile] = form_data.getlist("comprobantes")  # type: ignore
    partners = active_partners(db)

    try:
        payment = _build_payment_from_form(db, form, partner)
        amounts_by_partner = _resolve_contributions(db, form, partners, payment)
    except ValueError as exc:
        flash(request, str(exc), "error")
        return _rerender_form(request, db, partner, form, partners, status_code=400)

    apply_contributions(db, payment, amounts_by_partner)
    payment.created_by = partner.username
    db.add(payment)
    db.flush()

    saved = 0
    for group, kind in ((files_factura, "factura"), (files_otros, "otro")):
        n, errors = await attach_files(
            db,
            files=group,
            entity_type="payment",
            entity_id=payment.id,
            label=payment.concept,
            on_date=payment.date,
            uploaded_by=partner.username,
            kind=kind,
        )
        saved += n
        for e in errors:
            flash(request, e, "error")

    record(db, obj=payment, action="insert", changed_by=partner.username,
           summary=f"Alta de pago: {payment.concept}")
    db.commit()

    msg = f"Pago cargado ({saved} comprobante/s)." if saved else "Pago cargado."
    if not payment.control_ok:
        flash(request, "Ojo: la suma de aportes no coincide con el total del pago.", "warning")
    return redirect(f"/pagos/{payment.id}", request, msg)


def _resolve_order_id(db: Session, raw) -> int | None:
    from app.models import Order

    if not raw:
        return None
    try:
        oid = int(raw)
    except (ValueError, TypeError):
        return None
    return oid if db.get(Order, oid) else None


def _build_payment_from_form(db: Session, form: dict, partner: Partner) -> Payment:
    concept = (form.get("concept") or "").strip()
    if not concept:
        raise ValueError("Poné un concepto para el pago.")
    category = form.get("category") or "otro"
    if category not in valid_category_codes(db):
        raise ValueError("Categoría inválida.")
    status = form.get("status") or "pagado"
    if status not in valid_codes("payment_status"):
        raise ValueError("Estado inválido.")
    currency = (form.get("currency_charged") or "").upper()
    if currency not in {"ARS", "USD", "UYU"}:
        raise ValueError("Elegí la moneda (pesos, dólares o pesos uruguayos).")
    rate_type = form.get("exchange_rate_type") or "oficial"
    if currency == "UYU":
        rate_type = "uyu"

    amount_original = _parse_amount(str(form.get("amount_original") or ""), "Monto")
    exchange_rate = rate(str(form.get("exchange_rate") or "0").replace(",", "."))

    amounts = compute_amounts(
        currency_charged=currency,
        amount_original=amount_original,
        exchange_rate=exchange_rate,
    )

    expense_type = form.get("expense_type") or "negocio"
    if expense_type not in {"negocio", "personal"}:
        raise ValueError("Tipo de gasto inválido.")
    paid_by_id = None
    if expense_type == "personal":
        paid_by_id = _resolve_partner_id(db, form.get("paid_by_partner_id"))
        if paid_by_id is None:
            raise ValueError("Elegí qué socio pagó este gasto personal.")

    vat_amount, vat_rate = _vat_from_form(form, amounts.amount_ars)

    return Payment(
        date=parse_date(form.get("date")),
        concept=concept,
        category=category,
        currency_charged=currency,
        amount_original=amount_original,
        exchange_rate=amounts.exchange_rate,
        exchange_rate_type=rate_type,
        amount_ars=amounts.amount_ars,
        amount_usd=amounts.amount_usd,
        status=status,
        order_id=_resolve_order_id(db, form.get("order_id")),
        invoice_number=(form.get("invoice_number") or "").strip() or None,
        billable=bool(form.get("billable")),
        expense_type=expense_type,
        paid_by_partner_id=paid_by_id,
        vat_amount=vat_amount,
        vat_rate=vat_rate,
        notes=(form.get("notes") or "").strip() or None,
    )


def _resolve_partner_id(db: Session, raw) -> int | None:
    try:
        pid = int(raw)
    except (ValueError, TypeError):
        return None
    p = db.get(Partner, pid)
    return pid if p is not None else None


def _resolve_contributions(
    db: Session, form: dict, partners: list[Partner], payment: Payment
) -> dict[int, Decimal]:
    total_ars = payment.amount_ars
    if payment.expense_type == "personal":
        # 100% al socio que lo pagó; no participa del reparto 35/65.
        return {payment.paid_by_partner_id: money(total_ars)}
    mode = form.get("split_mode", "auto")
    if mode == "auto":
        return default_split(db, total_ars)
    custom = _contribution_inputs(form, partners)
    if custom is None:
        return default_split(db, total_ars)
    return custom


def _rerender_form(request, db, partner, form, partners, *, status_code=200, payment=None):
    ctx = {
        "partner": partner,
        "active_nav": "pagos",
        "partners": partners,
        "payment": payment,
        "orders": order_choices(db),
        "form": form,
        "contributions": {
            p.id: form.get(f"contribution_{p.id}", "") for p in partners
        },
        "pct_by_partner": {str(p.id): str(p.pct_share) for p in partners},
    }
    ctx.update(_rate_context(db, form.get("exchange_rate_type") or settings.default_rate_type))
    return render(request, "payments/form.html", ctx, status_code=status_code, db=db)


# -------------------------------------------------------------------------- detail


@router.get("/{payment_id}")
async def payment_detail(
    payment_id: int,
    request: Request,
    partner: Partner = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    payment = _load_payment(db, payment_id)
    if not payment:
        flash(request, "No se encontró el pago.", "error")
        return redirect("/pagos")
    docs = list_documents(db, "payment", payment.id)
    return render(
        request,
        "payments/detail.html",
        {
            "partner": partner,
            "active_nav": "pagos",
            "payment": payment,
            "documents": docs,
        },
        db=db,
    )


# ---------------------------------------------------------------------------- edit


@router.get("/{payment_id}/editar")
async def edit_payment(
    payment_id: int,
    request: Request,
    partner: Partner = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    payment = _load_payment(db, payment_id)
    if not payment:
        flash(request, "No se encontró el pago.", "error")
        return redirect("/pagos")
    partners = active_partners(db)
    contrib = {c.partner_id: c.amount_ars for c in payment.contributions}
    ctx = {
        "partner": partner,
        "active_nav": "pagos",
        "partners": partners,
        "payment": payment,
        "orders": order_choices(db),
        "form": {
            "date": payment.date.isoformat(),
            "concept": payment.concept,
            "category": payment.category,
            "status": payment.status,
            "currency_charged": payment.currency_charged,
            "amount_original": f"{payment.amount_original:.2f}",
            "exchange_rate": f"{payment.exchange_rate.normalize():f}",
            "exchange_rate_type": payment.exchange_rate_type,
            "order_id": str(payment.order_id or ""),
            "invoice_number": payment.invoice_number or "",
            "billable": "1" if payment.billable else "",
            "expense_type": payment.expense_type,
            "paid_by_partner_id": str(payment.paid_by_partner_id or ""),
            "vat_discrimina": "1" if payment.vat_amount is not None else "",
            "vat_rate": (f"{payment.vat_rate.normalize():f}" if payment.vat_rate is not None else "21"),
            "vat_amount_manual": (f"{payment.vat_amount:.2f}" if payment.vat_amount is not None else ""),
            "notes": payment.notes or "",
        },
        "contributions": {p.id: contrib.get(p.id, ZERO) for p in partners},
        "pct_by_partner": {str(p.id): str(p.pct_share) for p in partners},
        "suggested_rate": None,
        "rate_source": None,
    }
    return render(request, "payments/form.html", ctx, db=db)


@router.post("/{payment_id}")
async def update_payment(
    payment_id: int,
    request: Request,
    partner: Partner = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    payment = _load_payment(db, payment_id)
    if not payment:
        flash(request, "No se encontró el pago.", "error")
        return redirect("/pagos")

    form = dict((await request.form()).multi_items())
    partners = active_partners(db)
    before = snapshot(payment)
    try:
        new_data = _build_payment_from_form(db, form, partner)
        amounts_by_partner = _resolve_contributions(db, form, partners, new_data)
    except ValueError as exc:
        flash(request, str(exc), "error")
        return _rerender_form(request, db, partner, form, partners, status_code=400, payment=payment)

    for field in (
        "date", "concept", "category", "currency_charged", "amount_original",
        "exchange_rate", "exchange_rate_type", "amount_ars", "amount_usd", "status",
        "order_id", "invoice_number", "billable", "expense_type", "paid_by_partner_id",
        "vat_amount", "vat_rate", "notes",
    ):
        setattr(payment, field, getattr(new_data, field))
    apply_contributions(db, payment, amounts_by_partner)

    record(db, obj=payment, action="update", changed_by=partner.username,
           summary=f"Edición de pago #{payment.id}", old=before)
    db.commit()
    if not payment.control_ok:
        flash(request, "Ojo: la suma de aportes no coincide con el total del pago.", "warning")
    return redirect(f"/pagos/{payment.id}", request, "Pago actualizado.")


# --------------------------------------------------------------- editar solo aportes


@router.post("/{payment_id}/aportes")
async def update_contributions(
    payment_id: int,
    request: Request,
    partner: Partner = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    payment = _load_payment(db, payment_id)
    if not payment:
        flash(request, "No se encontró el pago.", "error")
        return redirect("/pagos")

    form = dict((await request.form()).multi_items())
    partners = active_partners(db)
    before = snapshot(payment)
    try:
        if form.get("split_mode") == "auto":
            amounts = default_split(db, payment.amount_ars)
        else:
            custom = _contribution_inputs(form, partners)
            amounts = custom if custom is not None else default_split(db, payment.amount_ars)
    except ValueError as exc:
        flash(request, str(exc), "error")
        return redirect(f"/pagos/{payment.id}")

    apply_contributions(db, payment, amounts)
    record(db, obj=payment, action="update", changed_by=partner.username,
           summary=f"Ajuste de aportes del pago #{payment.id}", old=before)
    db.commit()
    if not payment.control_ok:
        flash(request, "La suma de aportes no coincide con el total del pago.", "warning")
    else:
        flash(request, "Aportes actualizados.")
    return redirect(f"/pagos/{payment.id}")


# --------------------------------------------------------------------------- delete


@router.post("/{payment_id}/eliminar")
async def delete_payment(
    payment_id: int,
    request: Request,
    partner: Partner = Depends(require_owner),
    db: Session = Depends(get_db),
):
    payment = _load_payment(db, payment_id)
    if not payment:
        flash(request, "No se encontró el pago.", "error")
        return redirect("/pagos")
    from app.models import Document
    from app.storage import delete_file

    for doc in db.scalars(
        select(Document).where(Document.entity_type == "payment", Document.entity_id == payment.id)
    ):
        delete_file(doc.file_reference)
        db.delete(doc)

    # movimientos entre socios que lo referenciaban: se desvinculan (no se borran)
    from app.models import Purchase, Settlement

    for s in db.scalars(select(Settlement).where(Settlement.payment_id == payment.id)):
        s.payment_id = None
    for pu in db.scalars(select(Purchase).where(Purchase.payment_id == payment.id)):
        pu.payment_id = None

    record(db, obj=payment, action="delete", changed_by=partner.username,
           summary=f"Baja de pago #{payment.id}: {payment.concept}", old=snapshot(payment))
    db.delete(payment)
    db.commit()
    return redirect("/pagos", request, "Pago eliminado.")
