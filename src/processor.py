"""Motor de composicion: toma una foto + un marco PNG y produce el archivo final.

Reglas clave:
- La orientacion del resultado la define el MARCO (si el PNG es apaisado, la salida
  es apaisada; si es vertical, vertical).
- La foto se reduce desde su resolucion original al tamano de impresion. Nunca se
  agranda mas alla de lo necesario, asi que no se pierde calidad.
- Se respeta la orientacion EXIF de la camara (fotos verticales salen derechas).
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from PIL import Image, ImageOps

import config


@dataclass
class Job:
    """Parametros de una sesion de procesamiento."""
    frame_path: str
    size: "config.PrintSize"
    fit: str = config.DEFAULT_FIT
    dpi: int = config.DEFAULT_DPI
    out_format: str = config.DEFAULT_FORMAT
    border_color: tuple[int, int, int] = (255, 255, 255)
    quality: int = config.JPG_QUALITY


def _load_frame(frame_path: str) -> Image.Image:
    """Carga el marco en RGBA (necesita canal alfa para transparencia)."""
    frame = Image.open(frame_path)
    if frame.mode != "RGBA":
        frame = frame.convert("RGBA")
    return frame


def _canvas_size(frame: Image.Image, job: Job) -> tuple[int, int]:
    """Tamano del lienzo final en px, con la orientacion del marco."""
    landscape = frame.width >= frame.height
    return job.size.pixels(job.dpi, landscape)


def _fit_photo(photo: Image.Image, target: tuple[int, int], job: Job) -> Image.Image:
    """Ajusta la foto al tamano objetivo segun el modo elegido. Devuelve RGB."""
    tw, th = target
    photo = photo.convert("RGB")

    if job.fit == config.FIT_STRETCH:
        return photo.resize((tw, th), Image.LANCZOS)

    if job.fit == config.FIT_CONTAIN:
        fitted = ImageOps.contain(photo, (tw, th), Image.LANCZOS)
        canvas = Image.new("RGB", (tw, th), job.border_color)
        canvas.paste(fitted, ((tw - fitted.width) // 2, (th - fitted.height) // 2))
        return canvas

    # FIT_COVER (predeterminado): llena y recorta el excedente, centrado.
    return ImageOps.fit(photo, (tw, th), Image.LANCZOS, centering=(0.5, 0.5))


def compose(photo_path: str, job: Job, frame: Image.Image | None = None) -> Image.Image:
    """Genera la imagen final (foto ajustada + marco encima). No la guarda."""
    if frame is None:
        frame = _load_frame(job.frame_path)

    target = _canvas_size(frame, job)

    with Image.open(photo_path) as raw:
        # Corrige rotacion segun metadatos EXIF de la camara.
        raw = ImageOps.exif_transpose(raw)
        base = _fit_photo(raw, target, job)

    # Escala el marco exactamente al lienzo y lo pega respetando su transparencia.
    frame_scaled = frame if frame.size == target else frame.resize(target, Image.LANCZOS)
    base_rgba = base.convert("RGBA")
    base_rgba.alpha_composite(frame_scaled)
    return base_rgba.convert("RGB")


def output_path(photo_path: str, out_dir: str, job: Job) -> str:
    stem = os.path.splitext(os.path.basename(photo_path))[0]
    ext = "jpg" if job.out_format == config.FORMAT_JPG else "png"
    return os.path.join(out_dir, f"{stem}{config.OUTPUT_SUFFIX}.{ext}")


def process_one(photo_path: str, out_dir: str, job: Job,
                frame: Image.Image | None = None) -> str:
    """Procesa una foto y la guarda. Devuelve la ruta del archivo generado."""
    os.makedirs(out_dir, exist_ok=True)
    result = compose(photo_path, job, frame=frame)
    dest = output_path(photo_path, out_dir, job)

    if job.out_format == config.FORMAT_JPG:
        result.save(dest, "JPEG", quality=job.quality,
                    dpi=(job.dpi, job.dpi), subsampling=0, optimize=True)
    else:
        result.save(dest, "PNG", dpi=(job.dpi, job.dpi))
    return dest
