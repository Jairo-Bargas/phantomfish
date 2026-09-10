"""Botón 'Registrar pase Colón' en el panel de socios."""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.services.summary import build_summary

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


def _balances() -> dict[str, Decimal]:
    with SessionLocal() as db:
        s = build_summary(db)
        return {p.name: p.balance for p in s.partners}


def _names() -> tuple[str, str]:
    b = _balances()
    jairo = next(n for n in b if n.lower().startswith("jairo"))
    sebas = next(n for n in b if "seba" in n.lower())
    return jairo, sebas


def test_pase_colon_button_visible(auth_client):
    page = auth_client.get("/socios").text
    assert "Registrar pase Colón" in page
    assert "/socios/pase-colon" in page
    assert "Saldo de aportes" in page


def test_pase_colon_split_35_65(auth_client):
    jairo, sebas = _names()
    before = _balances()
    r = auth_client.post("/socios/pase-colon", follow_redirects=True)
    assert "Pase Colón registrado" in r.text
    after = _balances()
    # Jairo pagó 4000, le correspondía 1400 (35%) -> +2600 ; Sebastián -2600 (65%)
    assert after[jairo] - before[jairo] == Decimal("2600.00")
    assert after[sebas] - before[sebas] == Decimal("-2600.00")

    # aparece en pagos, no en el panel de la contadora (no facturable)
    assert "Pase Colón" in auth_client.get("/pagos", params={"q": "Pase Colón"}).text


def test_pase_colon_nets_between_partners(auth_client, sebas_client):
    jairo, sebas = _names()
    before = _balances()
    auth_client.post("/socios/pase-colon", follow_redirects=True)   # paga Jairo
    sebas_client.post("/socios/pase-colon", follow_redirects=True)  # paga Sebastián
    after = _balances()
    # neto: Jairo +2600 -1400 = +1200 ; Sebastián -1200
    assert after[jairo] - before[jairo] == Decimal("1200.00")
    assert after[sebas] - before[sebas] == Decimal("-1200.00")
    assert auth_client.get("/socios").status_code == 200


def test_pase_colon_not_visible_to_accountant(auth_client):
    auth_client.post("/socios/pase-colon", follow_redirects=True)
    auth_client.post(
        "/socios/contadora",
        data={"name": "Conta Pase", "username": "contapase", "password": "inicial123"},
        follow_redirects=True,
    )
    c = TestClient(app)
    rr = c.post("/contadora/login", data={"username": "contapase", "password": "inicial123"},
               follow_redirects=False)
    if rr.headers["location"] == "/contadora/password":
        c.post("/contadora/password",
               data={"new_password": "nueva12345", "confirm_password": "nueva12345"},
               follow_redirects=True)
    assert "Pase Colón" not in c.get("/contadora").text
