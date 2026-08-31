"""Arma phantomfish-proyecto.zip (proyecto limpio, sin entorno ni datos)."""

from __future__ import annotations

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = Path.home() / "Downloads" / "phantomfish-proyecto.zip"

EXCLUDE_DIRS = {".venv", ".git", "__pycache__", "storage", ".pytest_cache", ".idea", ".vscode"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".db", ".db-wal", ".db-shm", ".db-journal"}
EXCLUDE_NAMES = {".env", "pf.tgz", "phantomfish-proyecto.zip", ".DS_Store"}


def included(path: Path) -> bool:
    parts = set(path.relative_to(ROOT).parts)
    if parts & EXCLUDE_DIRS:
        return False
    if path.name in EXCLUDE_NAMES:
        return False
    if path.suffix in EXCLUDE_SUFFIXES:
        return False
    return True


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(ROOT.rglob("*")):
            if not path.is_file() or not included(path):
                continue
            zf.write(path, path.relative_to(ROOT).as_posix())
            count += 1
    size_kb = OUT.stat().st_size / 1024
    print(f"{OUT}  ({count} archivos, {size_kb:.0f} KB)")


if __name__ == "__main__":
    main()
