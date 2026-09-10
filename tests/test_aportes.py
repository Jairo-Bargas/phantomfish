"""Reparto de pagos compartidos: "quién lo pagó" y el saldo entre socios."""

from __future__ import annotations

import re
from decimal import Decimal

from app.database import SessionLocal
from app.services.payments import active_partners
from app.services.summary import aportes_debt


def _debt() -> Decimal:
    """Deuda por aportes en ARS: + => Sebastián le debe a Jairo."""
    with SessionLocal() as db:
        return aportes_debt(db, active_partners(db))


def _pay(client, **over):
    data = {
        "concept": "Pago compartido", "date": "2026-10-01", "category": "gasto_operativo",
        "status": "pagado", "currency_charged": "ARS", "amount_original": "100000",
        "exchange_rate": "1000", "exchange_rate_type": "oficial",
    }
    data.update(over)
    r = client.post("/pagos", data=data, follow_redirects=True)
    assert r.status_code == 200
    return r


def test_paid_by_one_partner_creates_debt(auth_client):
    d0 = _debt()
    # lo pagó Jairo (id 1) -> Sebastián (65%) le debe 65.000
    _pay(auth_client, concept="Alquiler oct", paid_mode="by_1")
    assert _debt() - d0 == Decimal("65000.00")


def test_split_between_both_no_debt(auth_client):
    d0 = _debt()
    _pay(auth_client, concept="Compartido 35/65", paid_mode="split", split_mode="auto")
    assert _debt() - d0 == Decimal("0")


def test_unallocated_payment_does_not_create_phantom_debt(auth_client):
    """Un pago sin repartir (aportes no suman el total) NO mueve el saldo."""
    d0 = _debt()
    _pay(
        auth_client, concept="Sin repartir", paid_mode="split", split_mode="custom",
        contribution_1="0", contribution_2="0",
    )
    assert _debt() == d0  # sin cambio


def test_detail_shows_who_paid(auth_client):
    _pay(auth_client, concept="Honorarios abogada X", paid_mode="by_1")
    pid = re.search(
        r"/pagos/(\d+)", auth_client.get("/pagos", params={"q": "Honorarios abogada X"}).text
    ).group(1)
    page = auth_client.get(f"/pagos/{pid}").text
    assert "Lo pagó Jairo" in page
    assert "le queda debiendo" in page


def test_change_who_paid_from_detail(auth_client):
    _pay(auth_client, concept="Insumos Y", paid_mode="split", split_mode="auto")
    pid = re.search(
        r"/pagos/(\d+)", auth_client.get("/pagos", params={"q": "Insumos Y"}).text
    ).group(1)
    d0 = _debt()
    auth_client.post(f"/pagos/{pid}/aportes", data={"paid_mode": "by_2"}, follow_redirects=True)
    # ahora lo pagó Sebastián -> Jairo (35%) le debe 35.000 -> el saldo baja 35.000
    assert _debt() - d0 == Decimal("-35000.00")
