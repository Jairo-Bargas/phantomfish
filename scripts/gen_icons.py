"""Genera los íconos PWA (icon-192.png / icon-512.png) con la marca Phantom Fish.

Ícono simple: fondo negro, pez blanco estilizado, aleta dorsal roja.
Si querés el logo real, reemplazá app/static/icon-192.png y icon-512.png por
tus PNG cuadrados (o poné app/static/logo-source.png y este script lo usa).
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "app" / "static"
SOURCE = OUT / "logo-source.png"

BLACK = (23, 21, 26)
WHITE = (255, 255, 255)
RED = (224, 31, 38)


def draw_icon(size: int) -> Image.Image:
    img = Image.new("RGB", (size, size), BLACK)
    d = ImageDraw.Draw(img)
    s = size / 512

    # cuerpo del pez
    d.ellipse([120 * s, 190 * s, 400 * s, 330 * s], fill=WHITE)
    # cola
    d.polygon(
        [(150 * s, 260 * s), (60 * s, 180 * s), (60 * s, 340 * s)],
        fill=WHITE,
    )
    # aleta dorsal (roja)
    d.polygon(
        [(210 * s, 195 * s), (300 * s, 120 * s), (330 * s, 200 * s)],
        fill=RED,
    )
    # ojo
    d.ellipse([330 * s, 240 * s, 360 * s, 270 * s], fill=BLACK)
    return img


def main() -> None:
    src = Image.open(SOURCE).convert("RGB") if SOURCE.exists() else None
    for px in (192, 512):
        if src is not None:
            icon = src.resize((px, px), Image.LANCZOS)
        else:
            icon = draw_icon(512).resize((px, px), Image.LANCZOS)
        icon.save(OUT / f"icon-{px}.png")
        print("escrito", OUT / f"icon-{px}.png")


if __name__ == "__main__":
    main()
