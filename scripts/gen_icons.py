"""Genera los íconos PWA (icon-192.png / icon-512.png)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "app" / "static"
TEAL = (15, 118, 110)
TEAL_DARK = (17, 94, 89)
CREAM = (240, 253, 250)


def draw_fish(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), TEAL)
    d = ImageDraw.Draw(img)
    s = size / 512

    # cuerpo del pez (elipse) + cola (triángulo)
    body = [90 * s, 170 * s, 380 * s, 342 * s]
    d.ellipse(body, fill=CREAM)
    d.polygon(
        [(360 * s, 256 * s), (460 * s, 175 * s), (460 * s, 337 * s)],
        fill=CREAM,
    )
    # ojo
    d.ellipse([150 * s, 228 * s, 178 * s, 256 * s], fill=TEAL_DARK)
    # "phantom": franja diagonal semitransparente
    overlay = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.line([(120 * s, 60 * s), (420 * s, 452 * s)], fill=(15, 118, 110, 90), width=int(70 * s))
    img.alpha_composite(overlay)
    return img


def main() -> None:
    for px in (192, 512):
        icon = draw_fish(512).resize((px, px), Image.LANCZOS)
        icon.convert("RGB").save(OUT / f"icon-{px}.png")
        print("escrito", OUT / f"icon-{px}.png")


if __name__ == "__main__":
    main()
