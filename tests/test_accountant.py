"""Acceso de la contadora: usuario propio, solo lectura de facturas (pagos y ventas).

No debe ver aportes de socios, pedidos, compras al proveedor ni movimientos entre
socios, y no debe poder gestionar su propio alta (eso lo hace el administrador
desde /socios/contadora).
"""

from __future__ import annotations

import re

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


@pytest.fixture(scope="session")
def accountant_creds():
    """Crea (una vez) el usuario de contadora compartido por los tests de este archivo."""
    admin = TestClient(app)
    r = admin.post(
        "/login", data={"username": "jairo", "password": "test1234"}, follow_redirects=False
    )
    assert r.status_code == 303
    admin.post(
        "/socios/contadora",
        data={"name": "Contadora Test", "username": "contadoratest", "password": "inicial123"},
        follow_redirects=True,
    )
    return {"username": "contadoratest", "password": "inicial123"}


@pytest.fixture
def accountant_client(accountant_creds):
    """Cliente ya logueado como contadora (con la contraseña cambiada, si hacía falta)."""
    c = TestClient(app)
    r = c.post(
        "/contadora/login",
        data={"username": accountant_creds["username"], "password": accountant_creds["password"]},
        follow_redirects=False,
    )
    assert r.status_code == 303
    if r.headers["location"] == "/contadora/password":
        new_pw = "nueva12345"
        c.post(
            "/contadora/password",
            data={"new_password": new_pw, "confirm_password": new_pw},
            follow_redirects=True,
        )
        accountant_creds["password"] = new_pw
    return c


# --------------------------------------------------------- alta/gestión (solo dueño)


def test_owner_can_create_and_manage_accountant(auth_client):
    r = auth_client.post(
        "/socios/contadora",
        data={"name": "Contadora Gestión", "username": "cgestion", "password": "abc12345"},
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert "cgestion" in r.text

    page = auth_client.get("/socios/contadora").text
    acc_id = re.search(r"/socios/contadora/(\d+)/reset", page).group(1)

    r = auth_client.post(
        f"/socios/contadora/{acc_id}/reset", data={"password": "otra12345"}, follow_redirects=True
    )
    assert "reseteada" in r.text.lower()

    r = auth_client.post(f"/socios/contadora/{acc_id}/activar", follow_redirects=True)
    assert "desactivado" in r.text.lower()
    r = auth_client.post(f"/socios/contadora/{acc_id}/activar", follow_redirects=True)
    assert "activado" in r.text.lower()


def test_non_owner_cannot_manage_accountant(sebas_client):
    r = sebas_client.get("/socios/contadora", follow_redirects=False)
    assert r.status_code == 303  # rechazado por require_owner (403 -> redirect)

    r = sebas_client.post(
        "/socios/contadora",
        data={"name": "Colada", "username": "colada1", "password": "abc12345"},
        follow_redirects=True,
    )
    assert "Crear un usuario nuevo" not in r.text
    assert "colada1" not in r.text


# --------------------------------------------------------------------- login propio


def test_accountant_first_login_forces_password_change(auth_client):
    auth_client.post(
        "/socios/contadora",
        data={"name": "Primer Login", "username": "cprimerlogin", "password": "inicial999"},
        follow_redirects=True,
    )
    c = TestClient(app)
    r = c.post(
        "/contadora/login",
        data={"username": "cprimerlogin", "password": "inicial999"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/contadora/password"

    # todavía no puede saltarse el cambio de contraseña e ir directo al tablero
    r = c.get("/contadora/password")
    assert r.status_code == 200

    r = c.post(
        "/contadora/password",
        data={"new_password": "definitiva123", "confirm_password": "definitiva123"},
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert "Facturas" in r.text


def test_accountant_wrong_password_rejected():
    c = TestClient(app)
    r = c.post(
        "/contadora/login",
        data={"username": "contadoratest", "password": "loquesea-incorrecta"},
        follow_redirects=False,
    )
    assert r.status_code == 401
    assert "incorrect" in r.text.lower()


# --------------------------------------------------------------------- tablero


def test_accountant_dashboard_shows_payments_and_sales(auth_client, accountant_client):
    auth_client.post(
        "/pagos",
        data={
            "concept": "Pago con factura para contadora", "date": "2026-09-04",
            "category": "otro", "status": "pagado", "currency_charged": "ARS",
            "amount_original": "50000", "exchange_rate": "1000",
            "exchange_rate_type": "oficial", "split_mode": "auto",
            "invoice_number": "A-0001-00009999", "billable": "1",
        },
        follow_redirects=True,
    )
    auth_client.post(
        "/ventas",
        data={
            "date": "2026-09-04", "customer": "Cliente Factura Contadora",
            "channel": "mayorista", "payment_method": "transferencia", "status": "cobrado",
            "invoice_number": "B-0002-00001234",
            "item_name_0": "Señuelo X", "item_qty_0": "10", "item_price_0": "500",
        },
        follow_redirects=True,
    )

    page = accountant_client.get("/contadora").text
    assert "Pago con factura para contadora" in page
    assert "A-0001-00009999" in page
    assert "Cliente Factura Contadora" in page
    assert "B-0002-00001234" in page

    # nada de aportes de socios ni navegación de socio
    assert "Porcentajes de reparto" not in page
    assert "class=\"tabbar\"" not in page
    assert "Sebasti" not in page
    assert "/socios" not in page
    assert "/pedidos" not in page
    assert "/compras" not in page


def test_accountant_cannot_reach_partner_routes(accountant_client):
    for path in ("/pagos", "/socios", "/pedidos", "/compras", "/socios/movimientos"):
        r = accountant_client.get(path, follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == "/login"


def test_accountant_dashboard_defaults_to_all_dates(accountant_client):
    page = accountant_client.get("/contadora").text
    assert "Todas las fechas" in page


def test_owner_can_hide_payment_from_accountant(auth_client, accountant_client):
    auth_client.post(
        "/pagos",
        data={
            "concept": "Pago proveedor por fuera", "date": "2026-09-20", "category": "importacion",
            "status": "pagado", "currency_charged": "USD", "amount_original": "1000",
            "exchange_rate": "1000", "exchange_rate_type": "oficial", "split_mode": "auto",
            "billable": "1",
        },
        follow_redirects=True,
    )
    pid = re.search(
        r"/pagos/(\d+)", auth_client.get("/pagos", params={"q": "Pago proveedor por fuera"}).text
    ).group(1)
    assert "Pago proveedor por fuera" in accountant_client.get("/contadora").text

    r = auth_client.post(f"/pagos/{pid}/facturable", follow_redirects=True)
    assert "no lo ve" in r.text.lower()
    assert "Pago proveedor por fuera" not in accountant_client.get("/contadora").text

    # y se puede volver a mostrar
    auth_client.post(f"/pagos/{pid}/facturable", follow_redirects=True)
    assert "Pago proveedor por fuera" in accountant_client.get("/contadora").text


# ------------------------------------------------------------- comprobantes (scoping)


def test_accountant_can_view_payment_doc_but_not_purchase_doc(auth_client, accountant_client):
    auth_client.post(
        "/pagos",
        data={
            "concept": "Pago con comprobante", "date": "2026-09-04", "category": "otro",
            "status": "pagado", "currency_charged": "ARS", "amount_original": "1000",
            "exchange_rate": "1000", "exchange_rate_type": "oficial", "split_mode": "auto",
            "billable": "1",
        },
        follow_redirects=True,
    )
    pid = re.search(
        r"/pagos/(\d+)", auth_client.get("/pagos", params={"q": "Pago con comprobante"}).text
    ).group(1)
    # comprobante marcado como factura -> lo ve la contadora
    auth_client.post(
        f"/comprobantes/payment/{pid}",
        data={"kind": "factura"},
        files=[("comprobantes", ("recibo.pdf", b"%PDF-1.4 contenido de prueba", "application/pdf"))],
        follow_redirects=True,
    )
    pay_doc_id = re.search(
        r"/comprobantes/(\d+)/ver", auth_client.get(f"/pagos/{pid}").text
    ).group(1)

    r = accountant_client.get(f"/comprobantes/{pay_doc_id}/ver")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"

    # el mismo comprobante como "otro" (no factura) -> la contadora no lo puede ver
    auth_client.post(f"/comprobantes/{pay_doc_id}/tipo", data={"kind": "otro"}, follow_redirects=True)
    r = accountant_client.get(f"/comprobantes/{pay_doc_id}/ver", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/contadora"
    # se vuelve a marcar como factura para no dejar estado raro
    auth_client.post(f"/comprobantes/{pay_doc_id}/tipo", data={"kind": "factura"}, follow_redirects=True)

    r = auth_client.post(
        "/compras",
        data={"supplier": "Proveedor Confidencial", "date": "2026-09-04",
              "shipment_status": "pendiente_pedido"},
        follow_redirects=True,
    )
    cid = re.search(r"/compras/(\d+)", str(r.url)).group(1)
    auth_client.post(
        f"/comprobantes/purchase/{cid}",
        files=[("comprobantes", ("factura-proveedor.pdf", b"%PDF-1.4 confidencial", "application/pdf"))],
        follow_redirects=True,
    )
    purchase_doc_id = re.search(
        r"/comprobantes/(\d+)/ver", auth_client.get(f"/compras/{cid}").text
    ).group(1)

    r = accountant_client.get(f"/comprobantes/{purchase_doc_id}/ver", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/contadora"
