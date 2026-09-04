"""Punto de entrada de la app FastAPI."""

from __future__ import annotations

import asyncio
import contextlib
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app import __version__
from app.config import BASE_DIR, get_settings
from app.seed import init_db
from app.templating import templates

settings = get_settings()


async def _backup_loop() -> None:
    from app.services import backups

    while True:
        try:
            made = await asyncio.to_thread(backups.run_scheduled)
            if made:
                print("Respaldo automático:", ", ".join(made))
        except Exception as exc:  # noqa: BLE001
            print("Error en respaldo automático:", exc)
        await asyncio.sleep(6 * 3600)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    task = asyncio.create_task(_backup_loop())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


app = FastAPI(title=settings.app_name, version=__version__, lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    same_site="lax",
    https_only=settings.cookie_secure,
    max_age=60 * 60 * 24 * 14,
)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app" / "static")), name="static")


from app.routers import (  # noqa: E402
    accountant,
    auth_routes,
    backups as backups_router,
    categories,
    dashboard,
    data_browser,
    documents,
    exchange,
    export,
    orders,
    partners,
    payments,
    purchases,
    reports,
    sales,
    settlements,
)

app.include_router(auth_routes.router)
app.include_router(accountant.router)
app.include_router(dashboard.router)
app.include_router(payments.router)
app.include_router(orders.router)
app.include_router(purchases.router)
app.include_router(sales.router)
app.include_router(reports.router)
app.include_router(settlements.router)
app.include_router(partners.router)
app.include_router(categories.router)
app.include_router(backups_router.router)
app.include_router(documents.router)
app.include_router(exchange.router)
app.include_router(export.router)
app.include_router(data_browser.router)


@app.exception_handler(401)
async def unauthorized_handler(request: Request, _exc):
    if request.url.path.startswith("/api/"):
        from fastapi.responses import JSONResponse

        return JSONResponse({"detail": "No autenticado"}, status_code=401)
    return RedirectResponse(url="/login", status_code=303)


@app.exception_handler(403)
async def forbidden_handler(request: Request, exc):
    from app.web import flash

    detail = getattr(exc, "detail", "No tenés permiso para hacer esto.")
    with contextlib.suppress(Exception):
        flash(request, detail, "error")
    back = request.headers.get("referer") or "/"
    return RedirectResponse(url=back, status_code=303)


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "version": __version__}


@app.get("/manifest.webmanifest")
async def manifest(request: Request):
    return templates.TemplateResponse(
        request, "manifest.webmanifest", media_type="application/manifest+json"
    )
