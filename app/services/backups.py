"""Respaldos automáticos de la base de datos y los comprobantes.

- Cada día: copia consistente de la base (SQLite) -> backups/db-YYYY-MM-DD.db
  (se guardan las últimas DAILY_KEEP).
- Cada semana: copia completa (base + comprobantes) -> backups/full-YYYY-MM-DD.tgz
  (se guardan las últimas WEEKLY_KEEP).

Se corre en segundo plano desde el arranque de la app (ver app/main.py).
"""

from __future__ import annotations

import datetime as dt
import sqlite3
import tarfile
from pathlib import Path

from app.config import get_settings

settings = get_settings()

BACKUP_DIR = settings.storage_path.parent / "backups"
DAILY_KEEP = 14
WEEKLY_KEEP = 8


def _db_file() -> Path | None:
    url = settings.database_url
    if not url.startswith("sqlite:"):
        return None
    # sqlite:///rel/path  o  sqlite:////abs/path
    path = url.split("sqlite:///", 1)[-1]
    p = Path(path)
    if not p.is_absolute():
        from app.config import BASE_DIR

        p = BASE_DIR / p
    return p if p.exists() else None


def _snapshot_db(dest: Path) -> None:
    src = _db_file()
    if not src:
        raise RuntimeError("Solo se puede respaldar automáticamente una base SQLite.")
    dest.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(src))
    try:
        out = sqlite3.connect(str(dest))
        try:
            con.backup(out)  # copia online consistente (respeta el WAL)
        finally:
            out.close()
    finally:
        con.close()


def _prune(prefix: str, keep: int) -> None:
    files = sorted(BACKUP_DIR.glob(f"{prefix}*"), reverse=True)
    for old in files[keep:]:
        try:
            old.unlink()
        except OSError:
            pass


def make_daily(today: dt.date | None = None) -> Path | None:
    today = today or dt.date.today()
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    dest = BACKUP_DIR / f"db-{today.isoformat()}.db"
    if dest.exists():
        return None
    _snapshot_db(dest)
    _prune("db-", DAILY_KEEP)
    return dest


def make_full(today: dt.date | None = None) -> Path | None:
    today = today or dt.date.today()
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    dest = BACKUP_DIR / f"full-{today.isoformat()}.tgz"
    if dest.exists():
        return None
    db_tmp = BACKUP_DIR / ".db-tmp.db"
    _snapshot_db(db_tmp)
    try:
        with tarfile.open(dest, "w:gz") as tar:
            tar.add(db_tmp, arcname="phantomfish.db")
            uploads = settings.storage_path
            if uploads.exists():
                tar.add(uploads, arcname="uploads")
    finally:
        db_tmp.unlink(missing_ok=True)
    _prune("full-", WEEKLY_KEEP)
    return dest


def _needs_weekly(today: dt.date) -> bool:
    recent = sorted(BACKUP_DIR.glob("full-*.tgz"), reverse=True)
    if not recent:
        return True
    try:
        last_date = dt.date.fromisoformat(recent[0].stem.split("full-", 1)[-1])
    except ValueError:
        return True
    return (today - last_date).days >= 7


def run_scheduled(today: dt.date | None = None) -> list[str]:
    """Hace los respaldos que falten. Devuelve qué creó."""
    today = today or dt.date.today()
    made: list[str] = []
    d = make_daily(today)
    if d:
        made.append(d.name)
    if _needs_weekly(today):
        f = make_full(today)
        if f:
            made.append(f.name)
    return made


def list_backups() -> list[dict]:
    if not BACKUP_DIR.exists():
        return []
    out = []
    for f in sorted(BACKUP_DIR.iterdir(), reverse=True):
        if f.name.startswith(".") or not f.is_file():
            continue
        st = f.stat()
        kind = "completo" if f.name.startswith("full-") else "base de datos"
        out.append(
            {
                "name": f.name,
                "kind": kind,
                "size_mb": round(st.st_size / 1_048_576, 2),
                "at": dt.datetime.fromtimestamp(st.st_mtime),
            }
        )
    return out


def backup_path(name: str) -> Path | None:
    if "/" in name or "\\" in name or ".." in name:
        return None
    p = BACKUP_DIR / name
    return p if p.exists() and p.is_file() else None
