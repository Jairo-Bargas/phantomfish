"""Endpoint de cotización del dólar (consulta dolarapi.com y la registra)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.auth import get_current_partner
from app.constants import valid_codes
from app.database import get_db
from app.models import Partner
from app.services.exchange_rate import (
    ExchangeRateError,
    fetch_and_log,
    last_known,
    suggested_rate,
)

router = APIRouter(prefix="/api")


@router.get("/exchange-rate")
async def exchange_rate(
    tipo: str = "oficial",
    partner: Partner = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    if tipo not in valid_codes("rate_type"):
        tipo = "oficial"
    try:
        data = fetch_and_log(db, tipo)
        return {
            "tipo": tipo,
            "compra": str(data["buy"]) if data["buy"] is not None else None,
            "venta": str(data["sell"]) if data["sell"] is not None else None,
            "sugerido": str(suggested_rate(data)) if suggested_rate(data) else None,
            "actualizado": data.get("updated_at"),
            "fuente": "dolarapi.com",
        }
    except ExchangeRateError as exc:
        known = last_known(db, tipo)
        if known:
            val = known.sell or known.buy
            return JSONResponse(
                {
                    "tipo": tipo,
                    "compra": str(known.buy) if known.buy is not None else None,
                    "venta": str(known.sell) if known.sell is not None else None,
                    "sugerido": str(val) if val is not None else None,
                    "actualizado": known.fetched_at.isoformat(),
                    "fuente": "último registro guardado",
                    "aviso": "No se pudo consultar dolarapi.com; se muestra el último valor.",
                },
                status_code=200,
            )
        return JSONResponse({"error": str(exc)}, status_code=502)
