"""Helpers compartidos por los routers web (mensajes flash, contexto base)."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.templating import templates

_FLASH_KEY = "_flash"


def flash(request: Request, message: str, category: str = "success") -> None:
    request.session.setdefault(_FLASH_KEY, []).append({"message": message, "category": category})


def pop_flashes(request: Request) -> list[dict]:
    return request.session.pop(_FLASH_KEY, [])


def render(
    request: Request,
    template: str,
    context: dict[str, Any] | None = None,
    *,
    status_code: int = 200,
    db: Any = None,
) -> HTMLResponse:
    ctx: dict[str, Any] = {
        "request": request,
        "flashes": pop_flashes(request),
        "partner": None,
        "active_nav": None,
        "categorias": [],
        "cat_label": lambda code: code or "",
    }
    if db is not None:
        from app.services.categories import all_categories

        cats = all_categories(db)
        lm = {c.code: c.label for c in cats}
        ctx["categorias"] = [c for c in cats if c.active]
        ctx["cat_label"] = lambda code, _lm=lm: _lm.get(code, code or "")
    if context:
        ctx.update(context)
    return templates.TemplateResponse(request, template, ctx, status_code=status_code)


def redirect(
    url: str, request: Request | None = None, message: str | None = None, category: str = "success"
) -> RedirectResponse:
    if request is not None and message:
        flash(request, message, category)
    return RedirectResponse(url=url, status_code=303)
