"""Pases a Colón: registro multimoneda y saldo entre socios."""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import PaseColon
from app.services.pases import pase_saldo
from app.services.payments import active_partners

_SEBAS_PW = "sebas12345"


@pytest.fixture
def sebas_client():
    c = TestClient(app)
    for pw in (_SEBAS_PW, "test1234"):
        r = c.post("/login", data={"username": "sebastian", "password": pw}, follow_redirects=False)
        if r.status_code == 303:
            break
    else:
        raise AssertionError("no se pudo iniciar sesión como sebastian")
    c.post(
        "/cuenta/password",
        data={"current_password": "test1234", "new_password": _SEBAS_PW,
              "confirm_password": _SEBAS_PW},
        follow_redirects=True,
    )
    return c


def _saldo() -> tuple[Decimal, Decimal]:
    """(net_ars, net_uyu) — positivo = socio B (65%) le debe al socio A (35%)."""
    with SessionLocal() as db:
        s = pase_saldo(db, active_partners(db))
        return s.net_ars, s.net_uyu


def test_button_and_form_visible(auth_client):
    page = auth_client.get("/socios").text
    assert "Registrar pase" in page
    assert 'name="ars"' in page and 'name="uyu"' in page
    assert "Saldo entre socios" in page


def test_pase_uyu_split(auth_client):
    ars0, uyu0 = _saldo()
    r = auth_client.post("/socios/pase-colon", data={"ars": "0", "uyu": "600"}, follow_redirects=True)
    assert "Pase Colón registrado" in r.text
    ars1, uyu1 = _saldo()
    # Jairo (35%) pagó 600 UYU -> Sebastián (65%) le debe 390 UYU ; ARS sin cambio
    assert uyu1 - uyu0 == Decimal("390.00")
    assert ars1 - ars0 == Decimal("0")


def test_pase_ars_split(auth_client):
    ars0, uyu0 = _saldo()
    auth_client.post("/socios/pase-colon", data={"ars": "4000", "uyu": "0"}, follow_redirects=True)
    ars1, uyu1 = _saldo()
    assert ars1 - ars0 == Decimal("2600.00")   # 65% de 4000
    assert uyu1 - uyu0 == Decimal("0")


def test_pase_nets_between_partners(auth_client, sebas_client):
    ars0, uyu0 = _saldo()
    auth_client.post("/socios/pase-colon", data={"ars": "0", "uyu": "600"}, follow_redirects=True)   # Jairo
    sebas_client.post("/socios/pase-colon", data={"ars": "0", "uyu": "600"}, follow_redirects=True)  # Sebastián
    ars1, uyu1 = _saldo()
    # Jairo: Seba debe 390 ; Sebastián: Jairo debe 210 -> neto Seba debe 180
    assert uyu1 - uyu0 == Decimal("180.00")
    assert ars1 - ars0 == Decimal("0")


def test_pase_requires_amount(auth_client):
    r = auth_client.post("/socios/pase-colon", data={"ars": "0", "uyu": "0"}, follow_redirects=True)
    assert "monto del pase" in r.text.lower()


def test_pase_owner_can_delete(auth_client):
    from sqlalchemy import select

    auth_client.post("/socios/pase-colon", data={"ars": "0", "uyu": "600"}, follow_redirects=True)
    with SessionLocal() as db:
        pid = db.scalar(select(PaseColon.id).order_by(PaseColon.id.desc()).limit(1))
    r = auth_client.post(f"/socios/pase-colon/{pid}/eliminar", follow_redirects=True)
    assert "eliminado" in r.text.lower()


def test_saldo_combines_aportes_and_pases(auth_client):
    """El saldo entre socios de /socios netea aportes de pagos + pasadas."""
    auth_client.post("/socios/pase-colon", data={"ars": "4000", "uyu": "0"}, follow_redirects=True)
    page = auth_client.get("/socios").text
    assert "Saldo entre socios" in page
    assert "le debe" in page  # hay una deuda (al menos por la pasada recién cargada)
