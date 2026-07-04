"""Genera el set de iconos (.png multi-tamaño + .ico) a partir del SVG fuente.

Uso:
    python generate_icons.py

Requiere: cairosvg, Pillow.

Produce:
    icons/icon-<size>.png   para size en (16, 20, 24, 32, 40, 48, 64, 128, 256)
    icon-calculator.ico     (multi-resolución, raíz del proyecto, usado por Nuitka)
"""

from __future__ import annotations

import io
from pathlib import Path

import cairosvg
from PIL import Image


SVG_PATH = Path(__file__).parent / "icons" / "icon-calculator.svg"
ICONS_DIR = Path(__file__).parent / "icons"
ICO_PATH = Path(__file__).parent / "icon-calculator.ico"

# Tamaños recomendados para Windows (incluye los usados por la shell y HiDPI).
SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def render_png(size: int) -> Image.Image:
    """Rasteriza el SVG a un PNG cuadrado del tamaño pedido, con alpha."""
    png_bytes = cairosvg.svg2png(
        url=str(SVG_PATH),
        output_width=size,
        output_height=size,
    )
    img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    return img


def main() -> None:
    if not SVG_PATH.exists():
        raise SystemExit(f"No se encontró el SVG: {SVG_PATH}")

    ICONS_DIR.mkdir(exist_ok=True)

    images: list[Image.Image] = []
    for size in SIZES:
        img = render_png(size)
        out_png = ICONS_DIR / f"icon-{size}.png"
        img.save(out_png, format="PNG", optimize=True)
        print(f"  + {out_png.relative_to(Path(__file__).parent)}  ({size}x{size})")
        images.append(img)

    # Pillow genera ICO multi-resolución a partir de la imagen más grande
    # usando el parámetro `sizes`. Cada entrada conserva el canal alpha.
    largest = images[-1]
    largest.save(
        ICO_PATH,
        format="ICO",
        sizes=[(s, s) for s in SIZES],
    )
    print(f"  + {ICO_PATH.name}  (multi-res: {', '.join(str(s) for s in SIZES)})")


if __name__ == "__main__":
    main()
