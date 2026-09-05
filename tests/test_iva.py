"""IVA discriminado en pagos/ventas, panel de IVA, y gastos personales."""

from __future__ import annotations

import re
from decimal import Decimal

from app.services.vat import vat_from_total


def _pay(client, **over):
    data = {
        "concept": "Pago IVA", "date": "2026-09-10", "category": "otro", "status": "pagado",
        "currency_charged": "ARS", "amount_original": "12100", "exchange_rate": "1000",
        "exchange_rate_type": "oficial", "split_mode": "auto", "billable": "1",
    }
    data.update(over)
    data = {k: v for k, v in data.items() if v is not None}
    r = client.post("/pagos", data=data, follow_redirects=True)
    assert r.status_code == 200
    return r


def _pay_id(client, concept):
    return re.search(r"/pagos/(\d+)", client.get("/pagos", params={"q": concept}).text).group(1)


# --------------------------------------------------------------- cálculo del IVA


def test_vat_from_total_math():
    # total con IVA incluido -> IVA contenido
    assert vat_from_total(Decimal("12100"), Decimal("21")) == Decimal("2100.00")
    assert vat_from_total(Decimal("11050"), Decimal("10.5")) == Decimal("1050.00")
    assert vat_from_total(Decimal("0"), Decimal("21")) == Decimal("0")


def test_payment_discrimina_iva(auth_client):
    _pay(auth_client, concept="Combustible con factura A", vat_discrimina="1", vat_rate="21")
    pid = _pay_id(auth_client, "Combustible con factura A")
    page = auth_client.get(f"/pagos/{pid}").text
    assert "2.100,00" in page  # IVA
    assert "10.000,00" in page  # neto


def test_payment_manual_iva_override(auth_client):
    _pay(
        auth_client, concept="Factura con percepcion", vat_discrimina="1", vat_rate="21",
        vat_amount_manual="3000",
    )
    pid = _pay_id(auth_client, "Factura con percepcion")
    page = auth_client.get(f"/pagos/{pid}").text
    assert "3.000,00" in page  # IVA manual, no el calculado (2100)


def test_iva_panel_position(auth_client):
    # crédito: pago con IVA 2100
    _pay(auth_client, concept="Credito IVA test", vat_discrimina="1", vat_rate="21")
    # débito: venta con IVA
    auth_client.post(
        "/ventas",
        data={
            "date": "2026-09-11", "customer": "Cliente IVA", "channel": "mayorista",
            "payment_method": "transferencia", "status": "cobrado",
            "vat_discrimina": "1", "vat_rate": "21",
            "item_name_0": "Señuelo", "item_qty_0": "1", "item_price_0": "6050",
        },
        follow_redirects=True,
    )
    page = auth_client.get("/reporte", params={"mes": "2026-09"}).text
    assert "IVA" in page
    # venta 6050 -> IVA débito 1050 ; crédito 2100 (al menos) -> posición a favor
    assert "IVA a favor" in page


# ------------------------------------------------------------- gastos personales


def test_personal_expense_hidden_from_default_list(auth_client):
    _pay(
        auth_client, concept="Nafta auto Jairo", expense_type="personal",
        paid_by_partner_id="1", billable="1",
    )
    # por defecto no aparece
    assert "Nafta auto Jairo" not in auth_client.get("/pagos").text
    # con el filtro sí
    assert "Nafta auto Jairo" in auth_client.get("/pagos", params={"personales": "ver"}).text
    assert "Nafta auto Jairo" in auth_client.get("/pagos", params={"personales": "solo"}).text


def test_personal_expense_not_in_report_totals(auth_client):
    # dos pagos del negocio + uno personal, todos en el mismo mes
    _pay(auth_client, concept="Op1 negocio", amount_original="10000", date="2026-10-02")
    _pay(auth_client, concept="Op2 negocio", amount_original="10000", date="2026-10-03")
    r = auth_client.get("/reporte", params={"mes": "2026-10"})
    base = r.text
    # total de pagos del mes (2 x 10000 = 20.000)
    assert "20.000,00" in base

    _pay(
        auth_client, concept="Gasto personal oct", amount_original="99999",
        expense_type="personal", paid_by_partner_id="2", date="2026-10-04",
    )
    r2 = auth_client.get("/reporte", params={"mes": "2026-10"}).text
    assert "99.999" not in r2  # el personal no suma a los costos del negocio
    assert "Gasto personal oct" not in r2


def test_personal_expense_requires_payer(auth_client):
    r = auth_client.post(
        "/pagos",
        data={
            "concept": "Personal sin pagador", "date": "2026-09-10", "category": "otro",
            "status": "pagado", "currency_charged": "ARS", "amount_original": "1000",
            "exchange_rate": "1000", "exchange_rate_type": "oficial", "split_mode": "auto",
            "expense_type": "personal",
        },
        follow_redirects=True,
    )
    assert "socio" in r.text.lower()  # mensaje de error pidiendo el pagador


# ------------------------------------------------------------ pago no facturable


def test_non_billable_payment_hidden_from_accountant(auth_client):
    from fastapi.testclient import TestClient
    from app.main import app

    _pay(auth_client, concept="Pago reservado no facturable", date="2026-09-15", billable=None)
    # crear/loguear contadora
    auth_client.post(
        "/socios/contadora",
        data={"name": "Conta IVA", "username": "contaiva", "password": "inicial123"},
        follow_redirects=True,
    )
    c = TestClient(app)
    r = c.post(
        "/contadora/login", data={"username": "contaiva", "password": "inicial123"},
        follow_redirects=False,
    )
    if r.headers["location"] == "/contadora/password":
        c.post(
            "/contadora/password",
            data={"new_password": "nueva12345", "confirm_password": "nueva12345"},
            follow_redirects=True,
        )
    page = c.get("/contadora").text
    assert "Pago reservado no facturable" not in page
