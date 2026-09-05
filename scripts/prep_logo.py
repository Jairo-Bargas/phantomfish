"""Prepara los assets del logo Phantom Fish a partir del original.

Entrada:  app/static/logo-source.png  (el logo cuadrado, fondo blanco)
Salidas:  app/static/logo.png           - logo completo, recortado y liviano (login)
          app/static/icon-192.png / icon-512.png - íconos PWA

La barra superior usa texto ("PHANTOM" + "FISH" en pill roja), no una imagen.
Volvé a correrlo (`py scripts/prep_logo.py`) si cambiás el logo original.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops

STATIC = Path(__file__).resolve().parent.parent / "app" / "static"
SRC = STATIC / "logo-source.png"


def trim_white(im: Image.Image, tol: int = 14) -> Image.Image:
    bg = Image.new("RGB", im.size, (255, 255, 255))
    diff = ImageChops.difference(im.convert("RGB"), bg)
    diff = ImageChops.add(diff, diff, 2.0, -tol * 3)
    box = diff.getbbox()
    return im.crop(box) if box else im


def pad(im: Image.Image, frac: float = 0.06) -> Image.Image:
    w, h = im.size
    m = int(max(w, h) * frac)
    side = max(w, h) + 2 * m
    canvas = Image.new("RGB", (side, side), (255, 255, 255))
    canvas.paste(im, ((side - w) // 2, (side - h) // 2))
    return canvas


def main() -> None:
    src = Image.open(SRC).convert("RGB")

    # --- logo completo, recortado y a ~640px ---
    full = trim_white(src)
    full.thumbnail((640, 640), Image.LANCZOS)
    full.save(STATIC / "logo.png", optimize=True)
    print("logo.png", full.size)

    # --- íconos PWA (logo sobre blanco, con aire) ---
    icon = pad(trim_white(src), 0.07)
    for px in (192, 512):
        icon.resize((px, px), Image.LANCZOS).save(STATIC / f"icon-{px}.png", optimize=True)
        print(f"icon-{px}.png")


if __name__ == "__main__":
    main()
