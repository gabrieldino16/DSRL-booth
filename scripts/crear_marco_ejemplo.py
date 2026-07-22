"""Genera marcos PNG de ejemplo (con transparencia) para probar DSRL Booth.

Crea un marco vertical (10x15) y uno apaisado (15x20) en la carpeta marcos/.
Se pueden regenerar con:  .venv\\Scripts\\python.exe scripts\\crear_marco_ejemplo.py
"""
import os

from PIL import Image, ImageDraw, ImageFont

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "marcos")
os.makedirs(OUT_DIR, exist_ok=True)

# Paleta
WHITE = (255, 255, 255, 255)
ACCENT = (45, 125, 70, 255)      # verde (mismo tono que el boton CREAR)
BANNER = (20, 20, 20, 210)       # barra inferior semi-opaca


def load_font(size):
    for name in ("arialbd.ttf", "arial.ttf", "segoeuib.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def make_frame(path, size, texto):
    w, h = size
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))  # todo transparente
    d = ImageDraw.Draw(im)

    borde = round(min(w, h) * 0.035)   # borde blanco exterior
    linea = max(3, round(borde * 0.12))  # grosor de la linea de acento

    # Borde blanco exterior (marco)
    d.rectangle([0, 0, w - 1, borde], fill=WHITE)
    d.rectangle([0, h - borde, w - 1, h - 1], fill=WHITE)
    d.rectangle([0, 0, borde, h - 1], fill=WHITE)
    d.rectangle([w - borde, 0, w - 1, h - 1], fill=WHITE)

    # Linea de acento por dentro del borde
    off = round(borde * 1.4)
    d.rectangle([off, off, w - off, h - off], outline=ACCENT, width=linea)

    # Barra inferior con texto
    bar_h = round(h * 0.11)
    d.rectangle([borde, h - borde - bar_h, w - borde, h - borde], fill=BANNER)
    font = load_font(round(bar_h * 0.42))
    bbox = d.textbbox((0, 0), texto, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    tx = (w - tw) / 2 - bbox[0]
    ty = (h - borde - bar_h) + (bar_h - th) / 2 - bbox[1]
    d.text((tx, ty), texto, font=font, fill=WHITE)

    im.save(path)
    print("Creado:", os.path.abspath(path), im.size)


if __name__ == "__main__":
    # 10x15 vertical a 300 DPI = 1181 x 1772
    make_frame(os.path.join(OUT_DIR, "ejemplo_10x15_vertical.png"),
               (1181, 1772), "MU-AVICI.AR")
    # 15x20 apaisado a 300 DPI = 2362 x 1772
    make_frame(os.path.join(OUT_DIR, "ejemplo_15x20_apaisado.png"),
               (2362, 1772), "MU-AVICI.AR")
