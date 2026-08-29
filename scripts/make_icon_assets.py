"""
Genera el asset de relleno del ícono del vehículo.

A partir de icono_carro.png (arte de líneas negras sobre fondo transparente)
produce icono_carro_fill.png: silueta opaca (interior + bordes) con exterior
transparente. Esta silueta se usa como máscara para colorear el fondo del
auto, mientras la imagen original se dibuja encima para conservar los
bordes negros.

Uso:
    python scripts/make_icon_assets.py
"""

import os

from PIL import Image, ImageDraw

SRC = os.path.join("static", "icono_carro.png")
DST = os.path.join("static", "icono_carro_fill.png")

THRESH = 32  # tolerancia para absorber el anti-aliasing del exterior


def main() -> None:
    im = Image.open(SRC).convert("RGBA")
    alpha = im.getchannel("A")
    w, h = alpha.size

    seeds = [
        (0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1),
        (w // 2, 0), (w // 2, h - 1), (0, h // 2), (w - 1, h // 2),
    ]
    for xy in seeds:
        if alpha.getpixel(xy) <= THRESH:
            ImageDraw.floodfill(alpha, xy, 128, thresh=THRESH)

    fill = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    px_a = alpha.load()
    px_f = fill.load()
    opaque = 0
    interior = 0
    for y in range(h):
        for x in range(w):
            v = px_a[x, y]
            if v != 128:  # todo lo que no es exterior
                px_f[x, y] = (255, 255, 255, 255)
                opaque += 1
                if v == 0:
                    interior += 1

    fill.save(DST)
    total = w * h
    print(f"size={w}x{h}")
    print(f"opacos={opaque} ({opaque / total * 100:.1f}%)")
    print(f"interior rellenado={interior} px")

    if interior == 0:
        print("ADVERTENCIA: no se rellenó interior; el contorno puede estar abierto.")


if __name__ == "__main__":
    main()
