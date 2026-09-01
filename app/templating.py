"""Configuración de Jinja2 y filtros compartidos por todos los routers."""

from __future__ import annotations

import datetime as dt
import time
from decimal import Decimal

from fastapi.templating import Jinja2Templates

from app.config import BASE_DIR, get_settings
from app.constants import _ALL, label_for

settings = get_settings()

# Cambia en cada arranque (= cada deploy). Se agrega como ?v= a los CSS/JS para
# que el navegador no sirva una versión vieja cacheada.
ASSET_VERSION = str(int(time.time()))

templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))


def money_ars(value) -> str:
    if value is None or value == "":
        return "—"
    d = Decimal(str(value)).quantize(Decimal("0.01"))
    entero, _, dec = f"{abs(d):.2f}".partition(".")
    miles = f"{int(entero):,}".replace(",", ".")
    signo = "-" if d < 0 else ""
    return f"{signo}$ {miles},{dec}"


def money_usd(value) -> str:
    if value is None or value == "":
        return "—"
    d = Decimal(str(value)).quantize(Decimal("0.01"))
    entero, _, dec = f"{abs(d):.2f}".partition(".")
    miles = f"{int(entero):,}".replace(",", ".")
    signo = "-" if d < 0 else ""
    return f"{signo}US$ {miles},{dec}"


def rate_fmt(value) -> str:
    if value is None:
        return "—"
    d = Decimal(str(value)).normalize()
    return f"{d:f}"


def qty_fmt(value) -> str:
    if value is None:
        return "—"
    d = Decimal(str(value))
    if d == d.to_integral():
        return f"{int(d):,}".replace(",", ".")
    return f"{d:.2f}"


def pct_fmt(value) -> str:
    if value is None:
        return "—"
    d = Decimal(str(value))
    if d == d.to_integral_value():
        return str(int(d))
    return f"{d.normalize():f}"


def date_fmt(value) -> str:
    if not value:
        return "—"
    if isinstance(value, str):
        value = dt.date.fromisoformat(value[:10])
    return value.strftime("%d/%m/%Y")


def datetime_fmt(value) -> str:
    if not value:
        return "—"
    if isinstance(value, str):
        value = dt.datetime.fromisoformat(value)
    return value.strftime("%d/%m/%Y %H:%M")


templates.env.filters["ars"] = money_ars
templates.env.filters["usd"] = money_usd
templates.env.filters["rate"] = rate_fmt
templates.env.filters["qty"] = qty_fmt
templates.env.filters["pct"] = pct_fmt
templates.env.filters["fecha"] = date_fmt
templates.env.filters["fechahora"] = datetime_fmt
templates.env.globals["label_for"] = label_for
templates.env.globals["OPTIONS"] = _ALL
templates.env.globals["APP_NAME"] = settings.app_name
templates.env.globals["ASSET_V"] = ASSET_VERSION
templates.env.globals["today"] = lambda: dt.date.today().isoformat()
