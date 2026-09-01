"""Opciones fijas (las mismas que los desplegables de la planilla modelo).

Nota: las categorías de pago (PAYMENT_CATEGORIES) ahora se pueden editar desde la
app — esta lista es solo la carga inicial (ver app/seed.py).
"""

# Carga inicial de la tabla `categories`. Después se editan desde /categorias.
PAYMENT_CATEGORIES = [
    ("importacion", "Importación"),
    ("gasto_operativo", "Gasto operativo"),
    ("costos_administrativos", "Costos administrativos"),
    ("impuesto", "Impuesto"),
    ("logistica", "Logística"),
    ("comision", "Comisión"),
    ("otro", "Otro"),
]

PAYMENT_STATUS = [
    ("pagado", "Pagado"),
    ("pendiente", "Pendiente"),
    ("parcial", "Parcial"),
]

CURRENCIES = [
    ("ARS", "Pesos argentinos ($)"),
    ("USD", "Dólares (US$)"),
    ("UYU", "Pesos uruguayos ($U)"),
]

# Cómo pedirle la cotización a dolarapi según la moneda del pago.
CURRENCY_RATE_KIND = {"USD": None, "UYU": "uyu"}  # USD usa el tipo elegido; UYU es fijo

RATE_TYPES = [
    ("oficial", "Oficial"),
    ("blue", "Blue"),
    ("mep", "MEP"),
    ("ccl", "CCL"),
    ("tarjeta", "Tarjeta"),
    ("mayorista", "Mayorista"),
]

SHIPMENT_STATUS = [
    ("pendiente_pedido", "Pendiente de pedido"),
    ("en_fabrica", "En fábrica"),
    ("en_transito", "En tránsito"),
    ("en_aduana", "En aduana"),
    ("recibido", "Recibido"),
]

ORDER_STATUS = [
    ("abierto", "Abierto"),
    ("recibido", "Recibido"),
    ("cerrado", "Cerrado (costo final)"),
]

SALE_CHANNELS = [
    ("mayorista", "Mayorista"),
    ("online", "Online"),
    ("local", "Local"),
    ("otro", "Otro"),
]

PAYMENT_METHODS = [
    ("efectivo", "Efectivo"),
    ("transferencia", "Transferencia"),
    ("mercado_pago", "Mercado Pago"),
    ("tarjeta", "Tarjeta"),
    ("otro", "Otro"),
]

SALE_STATUS = [
    ("cobrado", "Cobrado"),
    ("pendiente", "Pendiente"),
    ("parcial", "Parcial"),
]

SETTLEMENT_METHODS = [
    ("transferencia", "Transferencia"),
    ("efectivo", "Efectivo"),
    ("mercado_pago", "Mercado Pago"),
    ("otro", "Otro"),
]

SETTLEMENT_CURRENCIES = [
    ("ARS", "Pesos argentinos ($)"),
    ("USD", "Dólares (US$)"),
    ("UYU", "Pesos uruguayos ($U)"),
]

ENTITY_TYPES = ["payment", "purchase", "sale", "settlement"]

_ALL = {
    "payment_category": PAYMENT_CATEGORIES,
    "payment_status": PAYMENT_STATUS,
    "currency": CURRENCIES,
    "rate_type": RATE_TYPES,
    "shipment_status": SHIPMENT_STATUS,
    "sale_channel": SALE_CHANNELS,
    "payment_method": PAYMENT_METHODS,
    "sale_status": SALE_STATUS,
    "settlement_method": SETTLEMENT_METHODS,
    "settlement_currency": SETTLEMENT_CURRENCIES,
    "order_status": ORDER_STATUS,
}


def label_for(group: str, value: str) -> str:
    for code, label in _ALL.get(group, []):
        if code == value:
            return label
    return value or ""


def valid_codes(group: str) -> set[str]:
    return {code for code, _ in _ALL.get(group, [])}
