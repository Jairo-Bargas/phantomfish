"""Guardado de comprobantes (PDF / imágenes) en disco.

Abstracción fina para poder cambiar a S3 / almacenamiento en la nube más
adelante sin tocar los routers.
"""

from __future__ import annotations

import datetime as dt
import re
import unicodedata
import uuid
from pathlib import Path

from fastapi import UploadFile

from app.config import get_settings

settings = get_settings()

ALLOWED_CONTENT_TYPES = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/heic": ".heic",
    "image/heif": ".heif",
}
ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
MAX_BYTES = 20 * 1024 * 1024  # 20 MB


class UploadError(ValueError):
    pass


def _slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text[:50] or "archivo"


def _extension(filename: str, content_type: str | None) -> str:
    ext = Path(filename or "").suffix.lower()
    if ext in ALLOWED_EXTENSIONS:
        return ".jpg" if ext == ".jpeg" else ext
    if content_type in ALLOWED_CONTENT_TYPES:
        return ALLOWED_CONTENT_TYPES[content_type]
    raise UploadError(
        "Formato no permitido. Subí PDF o imagen (jpg, png, webp, heic)."
    )


async def save_upload(
    file: UploadFile,
    *,
    entity_type: str,
    entity_id: int,
    label: str = "",
    on_date: dt.date | None = None,
) -> dict:
    """Guarda el archivo y devuelve metadatos para la tabla ``documents``."""
    raw = await file.read()
    if not raw:
        raise UploadError("El archivo está vacío.")
    if len(raw) > MAX_BYTES:
        raise UploadError("El archivo supera los 20 MB.")

    ext = _extension(file.filename or "", file.content_type)
    on_date = on_date or dt.date.today()
    prefix = f"{entity_type[:3].upper()}{entity_id:04d}"
    slug = _slugify(label or Path(file.filename or "").stem or entity_type)
    name = f"{on_date.isoformat()}_{prefix}_{slug}_{uuid.uuid4().hex[:8]}{ext}"

    subdir = settings.storage_path / f"{on_date.year:04d}" / f"{on_date.month:02d}"
    subdir.mkdir(parents=True, exist_ok=True)
    dest = subdir / name
    dest.write_bytes(raw)

    rel = dest.relative_to(settings.storage_path).as_posix()
    return {
        "file_reference": rel,
        "original_filename": file.filename or name,
        "content_type": file.content_type,
        "size_bytes": len(raw),
    }


def absolute_path(file_reference: str) -> Path:
    p = (settings.storage_path / file_reference).resolve()
    if settings.storage_path.resolve() not in p.parents:
        raise UploadError("Ruta de archivo inválida.")
    return p


def delete_file(file_reference: str) -> None:
    try:
        absolute_path(file_reference).unlink(missing_ok=True)
    except (UploadError, OSError):
        pass
