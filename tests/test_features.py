"""Categorías editables, reporte por mes, y movimientos entre socios."""

from __future__ import annotations


def _make_payment(client, concept, date, ars, split_mode="auto", **extra):
    data = {
        "concept": concept,
        "date": date,
        "category": extra.get("category", "importacion"),
        "status": "pagado",
        "currency_charged": "ARS",
        "amount_original": str(ars),
        "exchange_rate": "1000",
        "exchange_rate_type": "oficial",
        "split_mode": split_mode,
    }
    data.update({k: v for k, v in extra.items() if k != "category"})
    return client.post("/pagos", data=data, follow_redirects=True)


# --------------------------------------------------------------------- categorías


def test_add_and_use_category(auth_client):
    resp = auth_client.post(
        "/categorias", data={"label": "Costos legales"}, follow_redirects=True
    )
    assert resp.status_code == 200
    assert "Costos legales" in resp.text

    # el nuevo código se puede usar en un pago
    resp = _make_payment(
        auth_client, "Honorarios abogado", "2026-09-03", 50000, category="costos_legales"
    )
    assert resp.status_code == 200
    detail = auth_client.get("/pagos", params={"q": "Honorarios abogado"})
    assert "Costos legales" in detail.text


def test_reject_unknown_category(auth_client):
    resp = _make_payment(
        auth_client, "Pago raro", "2026-09-03", 1000, category="no_existe_esto"
    )
    assert "inv" in resp.text.lower()  # "Categoría inválida"


def test_hide_category(auth_client):
    auth_client.post("/categorias", data={"label": "Temporal X"}, follow_redirects=True)
    page = auth_client.get("/categorias")
    # buscar el id de la categoría temporal
    import re

    m = re.search(r'/categorias/(\d+)"[^>]*>\s*<input name="label" value="Temporal X"', page.text)
    assert m, "no encontró la categoría recién creada"
    cid = m.group(1)
    resp = auth_client.post(
        f"/categorias/{cid}", data={"accion": "toggle"}, follow_redirects=True
    )
    assert "ocultada" in resp.text.lower()


# ------------------------------------------------------------------- reporte / mes


def test_month_filter_on_payments(auth_client):
    _make_payment(auth_client, "Gasto septiembre", "2026-09-10", 111111)
    _make_payment(auth_client, "Gasto octubre", "2026-10-05", 222222)

    sep = auth_client.get("/pagos", params={"mes": "2026-09"})
    assert "Gasto septiembre" in sep.text
    assert "Gasto octubre" not in sep.text


def test_monthly_report(auth_client):
    _make_payment(auth_client, "Reporte test pago", "2026-11-02", 90000)
    resp = auth_client.get("/reporte", params={"mes": "2026-11"})
    assert resp.status_code == 200
    assert "Noviembre 2026" in resp.text
    assert "Reporte test pago" in resp.text
    assert "90.000" in resp.text


# ------------------------------------------------------------- movimientos socios


def test_settlement_is_a_plain_ledger(auth_client):
    """Los movimientos entre socios son solo un registro: no tocan cálculos."""
    resp = auth_client.post(
        "/socios/movimientos",
        data={
            "from_partner_id": "2",
            "to_partner_id": "1",
            "date": "2026-12-05",
            "currency": "ARS",
            "amount_original": "40000",
            "method": "transferencia",
            "concept": "Parte del pago",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "Parte del pago" in resp.text

    # aparece en la lista, pero NO hay panel de "debe a quién"
    lst = auth_client.get("/socios/movimientos").text
    assert "Parte del pago" in lst
    assert "le debe a" not in lst.lower()
    assert "saldo neto" not in lst.lower()


def test_settlement_same_partner_rejected(auth_client):
    resp = auth_client.post(
        "/socios/movimientos",
        data={
            "from_partner_id": "1",
            "to_partner_id": "1",
            "date": "2026-12-05",
            "amount_ars": "1000",
            "method": "transferencia",
        },
        follow_redirects=True,
    )
    assert "mismo socio" in resp.text.lower()


# ---------------------------------------------------------------------- pedidos


def test_order_per_model_costing_and_price(auth_client):
    o = auth_client.post(
        "/pedidos",
        data={"date": "2027-01-05", "title": "Pedido test", "status": "recibido",
              "markup_pct": "150", "notes": ""},
        follow_redirects=True,
    )
    assert o.status_code == 200
    # extraer id del pedido de la URL final
    order_id = str(o.url).rstrip("/").split("/")[-1]

    # compra con 2 modelos: 1000 @ 2 y 1000 @ 4  -> merch = 6000 USD, 2000 unidades
    auth_client.post(
        "/compras",
        data={
            "supplier": "Yiwu", "date": "2027-01-06", "shipment_status": "recibido",
            "order_id": order_id, "payment_id": "",
            "item_name_0": "Modelo A", "item_qty_0": "1000", "item_price_0": "2",
            "item_name_1": "Modelo B", "item_qty_1": "1000", "item_price_1": "4",
        },
        follow_redirects=True,
    )
    # pagos del pedido: proveedor 6000 USD + flete 2000 USD  -> extra 2000 USD / 2000 u = 1 USD/u
    for concept, usd in [("Proveedor", "6000"), ("Flete", "2000")]:
        auth_client.post(
            "/pagos",
            data={"concept": concept, "date": "2027-01-06", "category": "importacion",
                  "status": "pagado", "currency_charged": "USD", "amount_original": usd,
                  "exchange_rate": "1000", "exchange_rate_type": "oficial",
                  "split_mode": "auto", "order_id": order_id},
            follow_redirects=True,
        )

    page = auth_client.get(f"/pedidos/{order_id}").text
    # Modelo A: 2 + 1 = 3 USD ; precio sugerido = 3000 ARS * 2.5 = 7500
    assert "US$ 3,00" in page
    assert "US$ 5,00" in page  # Modelo B: 4 + 1
    assert "7.500" in page     # precio sugerido Modelo A
    assert "12.500" in page    # precio sugerido Modelo B (5000 * 2.5)


def test_operativo_payment_not_in_order(auth_client):
    o = auth_client.post(
        "/pedidos",
        data={"date": "2027-02-01", "status": "abierto", "markup_pct": "100"},
        follow_redirects=True,
    )
    assert o.status_code == 200
    auth_client.post(
        "/pagos",
        data={"concept": "Alquiler febrero", "date": "2027-02-03", "category": "gasto_operativo",
              "status": "pagado", "currency_charged": "ARS", "amount_original": "80000",
              "exchange_rate": "1000", "exchange_rate_type": "oficial", "split_mode": "auto",
              "order_id": ""},
        follow_redirects=True,
    )
    rep = auth_client.get("/reporte", params={"mes": "2027-02"}).text
    assert "Alquiler febrero" in rep
    assert "Costos operativos" in rep


def test_payments_filter_by_order_and_type(auth_client):
    o = auth_client.post(
        "/pedidos", data={"date": "2027-03-01", "status": "abierto", "markup_pct": "150"},
        follow_redirects=True,
    )
    oid = str(o.url).rstrip("/").split("/")[-1]
    _make_payment(auth_client, "Costo del pedido marzo", "2027-03-02", 500000,
                  order_id=oid, currency_charged="ARS")
    _make_payment(auth_client, "Operativo marzo", "2027-03-03", 90000, order_id="")

    con = auth_client.get("/pagos", params={"pedido": "con"}).text
    assert "Costo del pedido marzo" in con
    assert "Operativo marzo" not in con

    sin = auth_client.get("/pagos", params={"pedido": "sin"}).text
    assert "Operativo marzo" in sin
    assert "Costo del pedido marzo" not in sin

    just = auth_client.get("/pagos", params={"pedido": oid}).text
    assert "Costo del pedido marzo" in just
    assert "Operativo marzo" not in just
