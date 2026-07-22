"""Prueba de humo del motor: genera una foto y un marco de mentira, compone y verifica.

No es un test unitario formal; se ejecuta directo con python para validar la logica.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from PIL import Image  # noqa: E402

import config  # noqa: E402
from processor import Job, process_one, compose  # noqa: E402

TMP = os.path.join(os.path.dirname(__file__), "_tmp")
os.makedirs(TMP, exist_ok=True)


def make_photo(path, size, color):
    Image.new("RGB", size, color).save(path)


def make_frame(path, size):
    # Marco transparente con un borde opaco de 40 px alrededor.
    im = Image.new("RGBA", size, (0, 0, 0, 0))
    px = im.load()
    b = 40
    for y in range(size[1]):
        for x in range(size[0]):
            if x < b or x >= size[0] - b or y < b or y >= size[1] - b:
                px[x, y] = (255, 0, 0, 255)
    im.save(path)


def check(name, cond):
    print(("OK  " if cond else "FALLO ") + name)
    if not cond:
        raise SystemExit(1)


def main():
    size_10x15 = config.PRINT_SIZES[0]
    size_15x20 = config.PRINT_SIZES[1]

    # 1) Verificar pixeles a 300 DPI (10x15 vertical -> 1181x1772).
    w, h = size_10x15.pixels(300, landscape=False)
    check(f"10x15 vertical = {w}x{h} (esperado 1181x1772)", (w, h) == (1181, 1772))
    w, h = size_15x20.pixels(300, landscape=True)
    check(f"15x20 apaisado = {w}x{h} (esperado 2362x1772)", (w, h) == (2362, 1772))

    # 2) Foto DSLR simulada (6000x4000, apaisada) + marco apaisado -> salida apaisada.
    photo = os.path.join(TMP, "foto.jpg")
    frame = os.path.join(TMP, "marco.png")
    make_photo(photo, (6000, 4000), (50, 120, 200))
    make_frame(frame, (1772, 1181))  # marco apaisado a 300 DPI para 10x15

    job = Job(frame_path=frame, size=size_10x15, fit=config.FIT_COVER)
    out = process_one(photo, TMP, job)
    check("archivo de salida existe", os.path.exists(out))

    with Image.open(out) as res:
        check(f"salida apaisada {res.size} (marco apaisado)", res.size == (1772, 1181))
        check("salida a 300 DPI", res.info.get("dpi", (0, 0))[0] in (300, 300.0))
        # La esquina debe ser roja (borde opaco del marco), no el azul de la foto.
        r, g, b = res.getpixel((5, 5))[:3]
        check(f"esquina roja del marco = ({r},{g},{b})", r > 200 and g < 60 and b < 60)
        # El centro debe mostrar la foto (azulado).
        cx, cy = res.width // 2, res.height // 2
        r, g, b = res.getpixel((cx, cy))[:3]
        check(f"centro muestra la foto = ({r},{g},{b})", b > 150 and r < 120)

    # 3) Foto vertical con marco vertical (marco manda la orientacion).
    make_frame(frame, (1181, 1772))  # marco vertical
    job = Job(frame_path=frame, size=size_10x15, fit=config.FIT_COVER)
    out2 = process_one(photo, TMP, job)
    with Image.open(out2) as res:
        check(f"salida vertical {res.size} (marco vertical)", res.size == (1181, 1772))

    print("\nTodo OK.")


if __name__ == "__main__":
    main()
