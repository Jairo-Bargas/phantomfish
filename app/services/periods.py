"""Helpers para filtrar por mes / período."""

from __future__ import annotations

import calendar
import datetime as dt

_MESES = [
    "", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]


def month_bounds(mes: str | None) -> tuple[dt.date | None, dt.date | None]:
    """'2026-09' -> (date(2026,9,1), date(2026,9,30)). Vacío -> (None, None)."""
    if not mes:
        return None, None
    try:
        year, month = (int(x) for x in mes.split("-")[:2])
        first = dt.date(year, month, 1)
        last = dt.date(year, month, calendar.monthrange(year, month)[1])
        return first, last
    except (ValueError, TypeError):
        return None, None


def month_label(mes: str | None) -> str:
    first, _ = month_bounds(mes)
    if not first:
        return ""
    return f"{_MESES[first.month]} {first.year}"


def this_month(today: dt.date | None = None) -> str:
    today = today or dt.date.today()
    return f"{today.year:04d}-{today.month:02d}"


def last_month(today: dt.date | None = None) -> str:
    today = today or dt.date.today()
    first = today.replace(day=1)
    prev = first - dt.timedelta(days=1)
    return f"{prev.year:04d}-{prev.month:02d}"


def recent_months(
    n: int = 14, today: dt.date | None = None, ahead: int = 2
) -> list[tuple[str, str]]:
    """[(code, label), ...] arrancando ``ahead`` meses adelante y yendo hacia atrás."""
    today = today or dt.date.today()
    y, m = today.year, today.month + ahead
    while m > 12:
        m -= 12
        y += 1
    out: list[tuple[str, str]] = []
    for _ in range(n):
        out.append((f"{y:04d}-{m:02d}", f"{_MESES[m]} {y}"))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return out


def month_options(selected: str | None = None, n: int = 14) -> list[tuple[str, str]]:
    """Como recent_months, pero garantiza que el mes seleccionado esté en la lista."""
    months = recent_months(n)
    if selected and selected not in {c for c, _ in months}:
        lbl = month_label(selected)
        if lbl:
            months = [(selected, lbl)] + months
    return months
