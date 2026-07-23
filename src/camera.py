"""Capa de camara de DSRL Booth.

Define una interfaz comun (CameraBackend) para que la fotocabina no dependa de
un hardware puntual. Hoy hay dos backends:

  - WebcamBackend: cualquier camara USB/UVC via OpenCV (incluye la GoPro en
    "modo webcam"). Sirve para tener el ciclo completo andando ya.
  - DummyBackend: imagen sintetica animada para cuando no hay camara conectada
    (permite probar toda la app sin hardware).

La Canon (EDSDK) entrara mas adelante como un CanonBackend que implemente esta
misma interfaz, sin tocar el resto del programa.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod

from PIL import Image, ImageDraw


class CameraError(Exception):
    pass


class CameraBackend(ABC):
    """Interfaz que debe cumplir cualquier fuente de captura."""

    name: str = "camara"

    # Fotos que llegan solas (obturador fisico). True solo en camaras tethered
    # (Canon EDSDK). En webcams el disparo siempre lo inicia la PC.
    supports_physical_trigger: bool = False

    # Callback opcional para el modo "foto asistida": se invoca con cada foto
    # entrante, sin importar si el disparo vino de la PC o del obturador fisico.
    on_photo = None

    @abstractmethod
    def start(self) -> None:
        """Abre la camara. Lanza CameraError si no se puede."""

    @abstractmethod
    def read_preview(self) -> Image.Image | None:
        """Devuelve un cuadro para la vista en vivo (o None si no hay)."""

    @abstractmethod
    def capture(self) -> Image.Image:
        """Toma la foto de alta calidad y la devuelve como imagen PIL."""

    def trigger(self) -> None:
        """Pide una captura desde la PC. Entrega el resultado por on_photo.

        Por defecto (webcam/simulada) captura al instante. La Canon manda el
        comando a la camara y la foto llega despues via poll().
        """
        img = self.capture()
        if self.on_photo is not None:
            self.on_photo(img)

    def poll(self) -> None:
        """Procesa fotos entrantes (obturador fisico). Solo camaras tethered."""

    def stop(self) -> None:
        """Libera la camara."""

    # Permite usar el backend con 'with'.
    def __enter__(self) -> "CameraBackend":
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()


class WebcamBackend(CameraBackend):
    """Webcam / GoPro / cualquier camara UVC mediante OpenCV."""

    def __init__(self, index: int = 0, width: int = 1920, height: int = 1080) -> None:
        self.index = index
        self.width = width
        self.height = height
        self.name = f"Webcam #{index}"
        self._cap = None

    def start(self) -> None:
        import cv2  # import perezoso: solo si realmente se usa webcam

        # CAP_DSHOW = backend DirectShow de Windows, mas rapido para abrir.
        cap = cv2.VideoCapture(self.index, cv2.CAP_DSHOW)
        if not cap or not cap.isOpened():
            raise CameraError(f"No se pudo abrir la webcam #{self.index}")
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self._cap = cap

    def _grab(self) -> Image.Image | None:
        import cv2

        if self._cap is None:
            return None
        ok, frame = self._cap.read()
        if not ok or frame is None:
            return None
        # OpenCV entrega BGR; PIL espera RGB.
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        return Image.fromarray(rgb)

    def read_preview(self) -> Image.Image | None:
        return self._grab()

    def capture(self) -> Image.Image:
        # Descarta unos cuadros para que el sensor ajuste exposicion/enfoque.
        for _ in range(4):
            self._grab()
            time.sleep(0.02)
        img = self._grab()
        if img is None:
            raise CameraError("La webcam no devolvio imagen al capturar")
        return img

    def stop(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None


class DummyBackend(CameraBackend):
    """Camara simulada: degradado animado. Util sin hardware conectado."""

    def __init__(self, width: int = 1920, height: int = 1080) -> None:
        self.width = width
        self.height = height
        self.name = "Camara simulada"
        self._t0 = 0.0

    def start(self) -> None:
        self._t0 = time.time()

    def _render(self) -> Image.Image:
        import math

        t = time.time() - self._t0
        img = Image.new("RGB", (self.width, self.height))
        px = img.load()
        # Degradado que cambia suavemente para que se note que esta "vivo".
        base = int(60 + 40 * math.sin(t))
        for y in range(self.height):
            r = base
            g = int(80 + 120 * y / self.height)
            b = int(160 + 60 * math.sin(t + y / 300))
            for x in range(0, self.width, 2):
                px[x, y] = (r, g, min(255, b))
                if x + 1 < self.width:
                    px[x + 1, y] = (r, g, min(255, b))
        d = ImageDraw.Draw(img)
        d.text((40, 40), "CAMARA SIMULADA (sin hardware)", fill=(255, 255, 255))
        return img

    def read_preview(self) -> Image.Image | None:
        # Preview mas chico para que la animacion sea fluida.
        small = self._render_small()
        return small

    def _render_small(self) -> Image.Image:
        import math

        t = time.time() - self._t0
        w, h = 640, 360
        img = Image.new("RGB", (w, h))
        d = ImageDraw.Draw(img)
        for y in range(h):
            c = (int(60 + 40 * math.sin(t)), int(80 + 120 * y / h),
                 min(255, int(160 + 60 * math.sin(t + y / 100))))
            d.line([(0, y), (w, y)], fill=c)
        cx = int(w / 2 + 200 * math.sin(t * 2))
        d.ellipse([cx - 30, h // 2 - 30, cx + 30, h // 2 + 30], fill=(255, 255, 255))
        d.text((20, 20), "CAMARA SIMULADA", fill=(255, 255, 255))
        return img

    def capture(self) -> Image.Image:
        return self._render()


def open_default_camera() -> CameraBackend:
    """Intenta abrir la webcam; si no hay, cae en la camara simulada."""
    cam = WebcamBackend()
    try:
        cam.start()
        return cam
    except (CameraError, Exception):
        dummy = DummyBackend()
        dummy.start()
        return dummy


from dataclasses import dataclass
from typing import Callable


@dataclass
class CameraOption:
    """Una cámara ofrecida en el selector. `factory` la crea (aún sin abrir)."""
    label: str
    factory: Callable[[], CameraBackend]


def list_webcam_indices(max_index: int = 5) -> list[int]:
    """Índices de webcams disponibles. Sin OpenCV, ofrece al menos el #0."""
    try:
        import cv2
    except ImportError:
        return [0]
    found: list[int] = []
    for i in range(max_index):
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
        if cap is not None and cap.isOpened():
            found.append(i)
        if cap is not None:
            cap.release()
    return found or [0]


def available_cameras() -> list[CameraOption]:
    """Cámaras para el selector: Canon (si está el SDK), webcams y la simulada."""
    options: list[CameraOption] = []

    try:
        import canon
        if canon.edsdk_available():
            options.append(CameraOption("Canon (EDSDK) — máxima calidad",
                                        lambda: canon.CanonBackend()))
    except Exception:  # noqa: BLE001
        pass

    for i in list_webcam_indices():
        options.append(CameraOption(
            f"Cámara USB #{i} (webcam / EOS Webcam Utility)",
            lambda i=i: WebcamBackend(i)))

    options.append(CameraOption("Cámara simulada (sin hardware)",
                                lambda: DummyBackend()))
    return options
