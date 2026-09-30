"""Desplegable de productos en ventas y agrupación de nombres viejos (a mano)."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import SessionLocal
from app.models import Sale
from app.services.products import canonical_product_name, totals_by_product


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


def _product_totals() -> dict[str, tuple[Decimal, Decimal]]:
    """{nombre: (cantidad, total_ars)} tal como lo arma /ventas hoy."""
    with SessionLocal() as db:
        sales = list(db.scalars(select(Sale).options(selectinload(Sale.items))))
        return {p.name: (p.quantity, p.total_ars) for p in totals_by_product(sales)}


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
    before = _product_totals()

    # variantes viejas, cargadas a mano antes de tener el desplegable
    _sale(auth_client, customer="Venta 1", item_name_0="BANANAS", item_qty_0="2", item_price_0="1000")
    _sale(auth_client, customer="Venta 2", item_name_0="Señuelo Banana", item_qty_0="3", item_price_0="1000")
    _sale(auth_client, customer="Venta 3", item_name_0="CRANK PALA CORTA", item_qty_0="1", item_price_0="500")
    _sale(auth_client, customer="Venta 4", item_name_0="Sub", item_qty_0="4", item_price_0="800")

    after = _product_totals()

    # las variantes no quedan como productos sueltos
    assert "BANANAS" not in after
    assert "CRANK PALA CORTA" not in after
    assert "Sub" not in after

    # se agruparon bajo el nombre real, sumando lo que ya hubiera (2 + 3 = 5, etc.)
    qty0, total0 = before.get("Señuelo Banana", (Decimal("0"), Decimal("0")))
    qty1, total1 = after["Señuelo Banana"]
    assert qty1 - qty0 == Decimal("5")
    assert total1 - total0 == Decimal("5000.00")

    qty0, total0 = before.get("Señuelo Crank", (Decimal("0"), Decimal("0")))
    qty1, total1 = after["Señuelo Crank"]
    assert qty1 - qty0 == Decimal("1")
    assert total1 - total0 == Decimal("500.00")

    qty0, total0 = before.get("Señuelo Sub Superficie", (Decimal("0"), Decimal("0")))
    qty1, total1 = after["Señuelo Sub Superficie"]
    assert qty1 - qty0 == Decimal("4")
    assert total1 - total0 == Decimal("3200.00")


def test_ventas_total_por_producto_usa_el_precio_real_de_cada_venta(auth_client):
    # el mismo producto se vendió a precios distintos en ventas distintas -> el
    # total tiene que sumar cantidad × precio de CADA venta, no la cantidad total
    # por un precio único.
    before_qty, before_total = _product_totals().get("Señuelo Banana", (Decimal("0"), Decimal("0")))

    _sale(auth_client, customer="Precio 1", item_name_0="Señuelo Banana", item_qty_0="2", item_price_0="8900")
    _sale(auth_client, customer="Precio 2", item_name_0="Señuelo Banana", item_qty_0="3", item_price_0="7900")
    _sale(auth_client, customer="Precio 3", item_name_0="Señuelo Banana", item_qty_0="1", item_price_0="11900")

    after_qty, after_total = _product_totals()["Señuelo Banana"]
    assert after_qty - before_qty == Decimal("6")
    # 2×8.900 + 3×7.900 + 1×11.900 = 53.400 -- no 6 × un precio cualquiera
    assert after_total - before_total == Decimal("53400.00")


def test_agrupar_por_palabra_clave_no_pierde_ni_duplica_nada(auth_client):
    """La agrupación solo junta renglones -- no puede cambiar la cantidad ni la
    plata total. Sumar todo agrupado tiene que dar exactamente igual que sumar
    todos los ítems de venta uno por uno, sin agrupar."""
    # variantes de sobra + un producto ajeno, que no debería mezclarse con nada
    _sale(auth_client, customer="Chequeo 1", item_name_0="BANANAS", item_qty_0="5", item_price_0="7900")
    _sale(auth_client, customer="Chequeo 2", item_name_0="SEÑUELO BANANA", item_qty_0="3", item_price_0="9500")
    _sale(auth_client, customer="Chequeo 3", item_name_0="CRANK PALA CORTA", item_qty_0="1", item_price_0="15000")
    _sale(auth_client, customer="Chequeo 4", item_name_0="SUB SUPERFICIE", item_qty_0="2", item_price_0="10800")
    _sale(auth_client, customer="Chequeo 5", item_name_0="Popper importado", item_qty_0="4", item_price_0="4000")

    with SessionLocal() as db:
        sales = list(db.scalars(select(Sale).options(selectinload(Sale.items))))

    raw_qty = sum((it.quantity for s in sales for it in s.items), Decimal("0"))
    raw_total = sum((it.total_ars for s in sales for it in s.items), Decimal("0"))

    grouped = totals_by_product(sales)
    grouped_qty = sum((p.quantity for p in grouped), Decimal("0"))
    grouped_total = sum((p.total_ars for p in grouped), Decimal("0"))

    assert grouped_qty == raw_qty
    assert grouped_total == raw_total
    # el producto ajeno no se mezcló con ningún señuelo
    assert any(p.name == "Popper importado" for p in grouped)
