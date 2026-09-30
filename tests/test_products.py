"""Desplegable de productos en ventas y agrupación de nombres viejos (a mano)."""

from __future__ import annotations

import re

from app.services.products import canonical_product_name


def _sale(client, **over):
    data = {
        "date": "2026-09-11", "customer": "Cliente venta", "channel": "mayorista",
        "payment_method": "transferencia", "status": "cobrado",
        "item_name_0": "Señuelo Banana", "item_qty_0": "1", "item_price_0": "1000",
    }
    data.update(over)
    r = client.post("/ventas", data=data, follow_redirects=True)
    assert r.status_code == 200
    return r


# ------------------------------------------------------- canonical_product_name


def test_canonical_product_name_variants():
    assert canonical_product_name("Señuelo Banana") == "Señuelo Banana"
    assert canonical_product_name("SEÑUELO BANANA") == "Señuelo Banana"
    assert canonical_product_name("Bananas") == "Señuelo Banana"
    assert canonical_product_name("BANANAS") == "Señuelo Banana"
    assert canonical_product_name("Crank") == "Señuelo Crank"
    assert canonical_product_name("CRANK PALA CORTA") == "Señuelo Crank"
    assert canonical_product_name("Sub") == "Señuelo Sub Superficie"
    assert canonical_product_name("SUB SUPERFICIE") == "Señuelo Sub Superficie"


def test_canonical_product_name_unknown_falls_back_unchanged():
    assert canonical_product_name("Popper importado") == "Popper importado"
    assert canonical_product_name("  ") == ""


# --------------------------------------------------------------- vendidos por producto


def test_ventas_agrupa_nombres_viejos_bajo_el_producto_real(auth_client):
    # variantes viejas, cargadas a mano antes de tener el desplegable
    _sale(auth_client, customer="Venta 1", item_name_0="BANANAS", item_qty_0="2", item_price_0="1000")
    _sale(auth_client, customer="Venta 2", item_name_0="Señuelo Banana", item_qty_0="3", item_price_0="1000")
    _sale(auth_client, customer="Venta 3", item_name_0="CRANK PALA CORTA", item_qty_0="1", item_price_0="500")
    _sale(auth_client, customer="Venta 4", item_name_0="Sub", item_qty_0="4", item_price_0="800")

    page = auth_client.get("/ventas").text
    # las variantes no aparecen sueltas como si fueran otro producto
    assert "<td>BANANAS</td>" not in page
    assert "<td>CRANK PALA CORTA</td>" not in page
    assert "<td>Sub</td>" not in page
    # se agruparon bajo el nombre real, con la cantidad sumada (2 + 3 = 5)
    assert re.search(r'<td>Señuelo Banana</td>\s*<td class="num">5</td>', page)
