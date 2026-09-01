"""Respaldos: ver la lista, crear uno ahora, descargar."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse

from app.auth import get_current_partner
from app.models import Partner
from app.services import backups
from app.web import redirect, render

router = APIRouter(prefix="/respaldos")


@router.get("")
async def list_view(
    request: Request,
    partner: Partner = Depends(get_current_partner),
):
    return render(
        request,
        "backups/list.html",
        {
            "partner": partner,
            "active_nav": "socios",
            "backups": backups.list_backups(),
            "dir": str(backups.BACKUP_DIR),
        },
    )


@router.post("/crear")
async def create_now(
    request: Request,
    partner: Partner = Depends(get_current_partner),
):
    import asyncio

    try:
        d = await asyncio.to_thread(backups.make_daily)
        f = await asyncio.to_thread(backups.make_full)
        hechos = [x.name for x in (d, f) if x]
        msg = "Respaldo creado: " + ", ".join(hechos) if hechos else "Ya había un respaldo de hoy."
        return redirect("/respaldos", request, msg)
    except Exception as exc:  # noqa: BLE001
        return redirect("/respaldos", request, f"No se pudo crear el respaldo: {exc}", "error")


@router.get("/{name}/descargar")
async def download(
    name: str,
    partner: Partner = Depends(get_current_partner),
):
    p = backups.backup_path(name)
    if not p:
        return redirect("/respaldos")
    return FileResponse(p, filename=name, media_type="application/octet-stream")
