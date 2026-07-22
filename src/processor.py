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


def fit_photo(photo: Image.Image, target: tuple[int, int],
              fit: str = config.DEFAULT_FIT,
              border_color: tuple[int, int, int] = (255, 255, 255)) -> Image.Image:
    """Ajusta una foto al tamano objetivo segun el modo. Devuelve RGB.

    Es la primitiva reutilizada tanto por la composicion de una foto suelta
    como por la de plantillas con varios huecos.
    """
    tw, th = target
    photo = photo.convert("RGB")

    if fit == config.FIT_STRETCH:
        return photo.resize((tw, th), Image.LANCZOS)

    if fit == config.FIT_CONTAIN:
        fitted = ImageOps.contain(photo, (tw, th), Image.LANCZOS)
        canvas = Image.new("RGB", (tw, th), border_color)
        canvas.paste(fitted, ((tw - fitted.width) // 2, (th - fitted.height) // 2))
        return canvas

    # FIT_COVER (predeterminado): llena y recorta el excedente, centrado.
    return ImageOps.fit(photo, (tw, th), Image.LANCZOS, centering=(0.5, 0.5))


def _fit_photo(photo: Image.Image, target: tuple[int, int], job: Job) -> Image.Image:
    """Compatibilidad: ajusta usando los parametros del Job."""
    return fit_photo(photo, target, job.fit, job.border_color)


def compose_image(photo: Image.Image, job: Job,
                  frame: Image.Image | None = None) -> Image.Image:
    """Compone una foto ya cargada en memoria con el marco. Devuelve RGB.

    Sirve tanto para archivos (modo lote) como para capturas en vivo (fotocabina).
    """
    if frame is None:
        frame = _load_frame(job.frame_path)

    target = _canvas_size(frame, job)

    # Corrige rotacion segun metadatos EXIF de la camara (si los hay).
    photo = ImageOps.exif_transpose(photo)
    base = _fit_photo(photo, target, job)

    # Escala el marco exactamente al lienzo y lo pega respetando su transparencia.
    frame_scaled = frame if frame.size == target else frame.resize(target, Image.LANCZOS)
    base_rgba = base.convert("RGBA")
    base_rgba.alpha_composite(frame_scaled)
    return base_rgba.convert("RGB")


def compose(photo_path: str, job: Job, frame: Image.Image | None = None) -> Image.Image:
    """Genera la imagen final desde un archivo (foto ajustada + marco). No la guarda."""
    with Image.open(photo_path) as raw:
        return compose_image(raw, job, frame)


def output_path(photo_path: str, out_dir: str, job: Job) -> str:
    stem = os.path.splitext(os.path.basename(photo_path))[0]
    ext = "jpg" if job.out_format == config.FORMAT_JPG else "png"
    return os.path.join(out_dir, f"{stem}{config.OUTPUT_SUFFIX}.{ext}")


def save_result(image: Image.Image, dest: str, job: Job) -> str:
    """Guarda una imagen ya compuesta en disco segun el formato del job."""
    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    if job.out_format == config.FORMAT_JPG:
        image.save(dest, "JPEG", quality=job.quality,
                   dpi=(job.dpi, job.dpi), subsampling=0, optimize=True)
    else:
        image.save(dest, "PNG", dpi=(job.dpi, job.dpi))
    return dest


def process_one(photo_path: str, out_dir: str, job: Job,
                frame: Image.Image | None = None) -> str:
    """Procesa una foto y la guarda. Devuelve la ruta del archivo generado."""
    result = compose(photo_path, job, frame=frame)
    dest = output_path(photo_path, out_dir, job)
    return save_result(result, dest, job)


def compose_template(photos: list[Image.Image | None], template,
                     frame: Image.Image | None = None,
                     background: Image.Image | None = None) -> Image.Image:
    """Compone varias capturas dentro de una plantilla (tira de fotocabina).

    `template` es un template.Template: define el lienzo, los huecos de foto
    (posicion/tamano en fracciones 0..1), un marco PNG opcional encima y un
    fondo opcional debajo.

    `photos` se empareja con los huecos en orden. Se admiten None o una lista
    mas corta que la cantidad de huecos: esos huecos quedan sin foto (util para
    ir mostrando la tira mientras se llena durante la sesion).

    Devuelve RGB.
    """
    canvas_w, canvas_h = template.canvas_size()

    base = Image.new("RGBA", (canvas_w, canvas_h),
                     tuple(template.background_color) + (255,))

    # Fondo opcional debajo de todo.
    if background is None and template.background_path:
        background = Image.open(template.background_path)
    if background is not None:
        bg = fit_photo(background, (canvas_w, canvas_h), config.FIT_COVER)
        base.alpha_composite(bg.convert("RGBA"))

    # Cada captura en su hueco.
    for slot, photo in zip(template.slots, photos):
        if photo is None:
            continue
        sx = round(slot.x * canvas_w)
        sy = round(slot.y * canvas_h)
        sw = max(1, round(slot.w * canvas_w))
        sh = max(1, round(slot.h * canvas_h))

        photo = ImageOps.exif_transpose(photo)
        fitted = fit_photo(photo, (sw, sh), slot.fit).convert("RGBA")

        if slot.rotation:
            # PIL rota en sentido antihorario; negamos para que sea horario.
            fitted = fitted.rotate(-slot.rotation, expand=True,
                                   resample=Image.BICUBIC)
            px = sx + (sw - fitted.width) // 2
            py = sy + (sh - fitted.height) // 2
            base.alpha_composite(fitted, (px, py))
        else:
            base.alpha_composite(fitted, (sx, sy))

    # Marco PNG encima (respeta su transparencia).
    if frame is None and template.frame_path:
        frame = _load_frame(template.frame_path)
    if frame is not None:
        if frame.size != (canvas_w, canvas_h):
            frame = frame.resize((canvas_w, canvas_h), Image.LANCZOS)
        base.alpha_composite(frame)

    return base.convert("RGB")
