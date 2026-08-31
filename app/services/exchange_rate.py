"""Cliente de dolarapi.com (pública, sin API key).

Cada consulta se guarda en exchange_rate_log como auditoría de la fuente
externa. El valor que se usa en cada pago lo confirma el usuario en el
formulario; nunca se aplica en silencio.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import httpx
from sqlalchemy.orm import Session

from app.models import ExchangeRateLog
from app.money import rate

BASE_URL = "https://dolarapi.com/v1/dolares"
TIMEOUT = 8.0

# casa de dolarapi por cada tipo que mostramos
_CASA = {
    "oficial": "oficial",
    "blue": "blue",
    "mep": "bolsa",
    "ccl": "contadoconliqui",
    "tarjeta": "tarjeta",
    "mayorista": "mayorista",
}


class ExchangeRateError(RuntimeError):
    pass


def _parse(payload: dict) -> dict:
    compra = payload.get("compra")
    venta = payload.get("venta")
    return {
        "buy": rate(compra) if compra is not None else None,
        "sell": rate(venta) if venta is not None else None,
        "updated_at": payload.get("fechaActualizacion"),
        "name": payload.get("nombre"),
    }


def fetch_rate(rate_type: str) -> dict:
    casa = _CASA.get(rate_type, "oficial")
    try:
        resp = httpx.get(f"{BASE_URL}/{casa}", timeout=TIMEOUT)
        resp.raise_for_status()
        data = _parse(resp.json())
    except (httpx.HTTPError, ValueError) as exc:
        raise ExchangeRateError(
            f"No se pudo obtener la cotización ({rate_type}): {exc}"
        ) from exc
    data["rate_type"] = rate_type
    return data


def fetch_and_log(db: Session, rate_type: str) -> dict:
    data = fetch_rate(rate_type)
    db.add(
        ExchangeRateLog(
            rate_type=rate_type,
            buy=data["buy"],
            sell=data["sell"],
            source="dolarapi.com",
        )
    )
    db.commit()
    return data


def suggested_rate(data: dict) -> Decimal | None:
    """Para pagar (comprar dólares) usamos el valor de venta."""
    return data.get("sell") or data.get("buy")


def last_known(db: Session, rate_type: str) -> ExchangeRateLog | None:
    from sqlalchemy import select

    return db.scalar(
        select(ExchangeRateLog)
        .where(ExchangeRateLog.rate_type == rate_type)
        .order_by(ExchangeRateLog.fetched_at.desc())
        .limit(1)
    )


def today_str() -> str:
    return dt.date.today().isoformat()
