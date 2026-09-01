"""Pesos uruguayos, autorización de borrado y respaldos."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


_SEBAS_PW = "sebas12345"


@pytest.fixture
def sebas_client():
    """Sesión de Sebastián (no administrador)."""
    c = TestClient(app)
    for pw in (_SEBAS_PW, "test1234"):
        r = c.post(
            "/login", data={"username": "sebastian", "password": pw}, follow_redirects=False
        )
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


# ------------------------------------------------------------------ pesos uruguayos


def test_payment_in_uyu(auth_client):
    r = auth_client.post(
        "/pagos",
        data={
            "concept": "Hospedaje Punta del Este",
            "date": "2026-09-10",
            "category": "gasto_operativo",
            "status": "pagado",
            "currency_charged": "UYU",
            "amount_original": "4000",
            "exchange_rate": "26.5",  # ARS por peso uruguayo
            "split_mode": "auto",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    body = r.text
    # 4000 * 26.5 = 106.000 ARS
    assert "106.000" in body
    assert "Hospedaje Punta del Este" in body


def test_settlement_in_usd(auth_client):
    r = auth_client.post(
        "/socios/movimientos",
        data={
            "from_partner_id": "2",
            "to_partner_id": "1",
            "date": "2026-09-12",
            "currency": "USD",
            "amount_original": "100",
            "exchange_rate": "1450",
            "method": "transferencia",
            "concept": "Su parte en dólares",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    # 100 * 1450 = 145.000 ARS
    assert "145.000" in r.text


# --------------------------------------------------------- autorización de borrado


def test_owner_can_delete_payment(auth_client):
    _ = auth_client.post(
        "/pagos",
        data={
            "concept": "Para borrar", "date": "2026-09-01", "category": "otro",
            "status": "pagado", "currency_charged": "ARS", "amount_original": "1000",
            "exchange_rate": "1000", "exchange_rate_type": "oficial", "split_mode": "auto",
        },
        follow_redirects=True,
    )
    # buscar el id
    import re

    lst = auth_client.get("/pagos", params={"q": "Para borrar"}).text
    pid = re.search(r"/pagos/(\d+)", lst).group(1)
    r = auth_client.post(f"/pagos/{pid}/eliminar", follow_redirects=True)
    assert r.status_code == 200
    assert "eliminado" in r.text.lower()


def test_non_owner_cannot_delete(auth_client, sebas_client):
    # Jairo crea un pago
    auth_client.post(
        "/pagos",
        data={
            "concept": "Protegido", "date": "2026-09-01", "category": "otro",
            "status": "pagado", "currency_charged": "ARS", "amount_original": "1000",
            "exchange_rate": "1000", "exchange_rate_type": "oficial", "split_mode": "auto",
        },
        follow_redirects=True,
    )
    import re

    lst = auth_client.get("/pagos", params={"q": "Protegido"}).text
    pid = re.search(r"/pagos/(\d+)", lst).group(1)

    # Sebastián intenta borrarlo -> rechazado, el pago sigue
    r = sebas_client.post(f"/pagos/{pid}/eliminar", follow_redirects=False)
    assert r.status_code in (303, 403)
    still = auth_client.get(f"/pagos/{pid}")
    assert still.status_code == 200
    assert "Protegido" in still.text


def test_non_owner_no_delete_button(sebas_client, auth_client):
    auth_client.post(
        "/pagos",
        data={
            "concept": "Sin boton", "date": "2026-09-01", "category": "otro",
            "status": "pagado", "currency_charged": "ARS", "amount_original": "1000",
            "exchange_rate": "1000", "exchange_rate_type": "oficial", "split_mode": "auto",
        },
        follow_redirects=True,
    )
    import re

    lst = auth_client.get("/pagos", params={"q": "Sin boton"}).text
    pid = re.search(r"/pagos/(\d+)", lst).group(1)
    page = sebas_client.get(f"/pagos/{pid}").text
    assert "Sin boton" in page  # la página cargó
    assert f"/pagos/{pid}/eliminar" not in page  # pero sin botón de borrar
    # y en /socios ve la aclaración
    assert "administrador" in sebas_client.get("/socios").text.lower()


# ----------------------------------------------------------------------- respaldos


def test_backups_page_and_create(auth_client):
    r = auth_client.get("/respaldos")
    assert r.status_code == 200
    r = auth_client.post("/respaldos/crear", follow_redirects=True)
    assert r.status_code == 200
    page = auth_client.get("/respaldos").text
    assert "db-" in page  # apareció al menos un respaldo diario
