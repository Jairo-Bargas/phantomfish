"""Prepara los assets del logo Phantom Fish a partir del original.

Entrada:  app/static/logo-source.png  (el logo, con fondo transparente)
Salidas:  app/static/logo.png       - logo completo sobre blanco (pantallas de login)
          app/static/logo-mark.png  - solo "PHANTOM FISH" transparente (barra sup.)
          app/static/icon-192.png / icon-512.png - íconos PWA

Volvé a correrlo (`py scripts/prep_logo.py`) si cambiás el logo original.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

STATIC = Path(__file__).resolve().parent.parent / "app" / "static"
SRC = STATIC / "logo-source.png"


def trim_alpha(im: Image.Image) -> Image.Image:
    """Recorta los bordes transparentes."""
    im = im.convert("RGBA")
    box = im.split()[-1].getbbox()
    return im.crop(box) if box else im


def flatten(im: Image.Image, bg=(255, 255, 255)) -> Image.Image:
    canvas = Image.new("RGB", im.size, bg)
    canvas.paste(im, mask=im.split()[-1])
    return canvas


def pad_square(im: Image.Image, frac: float = 0.06) -> Image.Image:
    w, h = im.size
    m = int(max(w, h) * frac)
    side = max(w, h) + 2 * m
    canvas = Image.new("RGBA", (side, side), (255, 255, 255, 0))
    canvas.paste(im, ((side - w) // 2, (side - h) // 2))
    return canvas


def main() -> None:
    src = trim_alpha(Image.open(SRC))
    w, h = src.size

    # --- logo completo (con subtítulo), sobre blanco, para el login ---
    full = flatten(src)
    full.thumbnail((760, 760), Image.LANCZOS)
    full.save(STATIC / "logo.png", optimize=True)
    print("logo.png", full.size)

    # --- solo el wordmark "PHANTOM FISH" (transparente, el subtítulo va abajo) ---
    mark = trim_alpha(src.crop((0, 0, w, int(h * 0.70))))
    mark.thumbnail((900, 300), Image.LANCZOS)
    mark.save(STATIC / "logo-mark.png", optimize=True)
    print("logo-mark.png", mark.size)

    # --- íconos PWA (el wordmark sobre blanco, cuadrado, con aire) ---
    icon = flatten(pad_square(mark, 0.06))
    for px in (192, 512):
        icon.resize((px, px), Image.LANCZOS).save(STATIC / f"icon-{px}.png", optimize=True)
        print(f"icon-{px}.png")


if __name__ == "__main__":
    main()
