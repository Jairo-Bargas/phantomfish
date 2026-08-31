"""Registro de auditoría: quién cambió qué y cuándo."""

from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.models import AuditLog

_SKIP = {"created_at", "updated_at", "password_hash"}


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    return value


def snapshot(obj) -> dict[str, Any]:
    data = {}
    for col in inspect(obj).mapper.column_attrs:
        key = col.key
        if key in _SKIP:
            continue
        data[key] = _jsonable(getattr(obj, key))
    return data


def record(
    db: Session,
    *,
    obj,
    action: str,
    changed_by: str | None,
    summary: str | None = None,
    old: dict | None = None,
    new: dict | None = None,
) -> None:
    table = obj.__tablename__
    rec_id = getattr(obj, "id", 0) or 0
    if new is None and action != "delete":
        new = snapshot(obj)
    entry = AuditLog(
        table_name=table,
        record_id=rec_id,
        action=action,
        changed_by=changed_by,
        summary=summary,
        old_values=json.dumps(old, ensure_ascii=False) if old else None,
        new_values=json.dumps(new, ensure_ascii=False) if new else None,
    )
    db.add(entry)
