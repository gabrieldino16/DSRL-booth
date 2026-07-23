"""Fuente de fotos por "carpeta observada" (hot folder), como dslrBooth.

Este es el patrón que usás con dslrBooth + EOS Utility, y evita tener la cámara
en Live View / modo webcam todo el día:

  1. EOS Utility queda corriendo y hace la **descarga automática**: cuando el
     fotógrafo dispara (obturador físico), baja el JPG a una carpeta.
  2. Esta clase **vigila esa carpeta**: apenas aparece una foto nueva, la carga y
     la entrega por `on_photo`, igual que si fuera una captura.

Ventajas para el flujo asistido (foto con fotógrafo, tipo Papá Noel):
  - La cámara solo trabaja cuando el fotógrafo dispara (no queda "abierta").
  - Funciona con cualquier Canon que EOS Utility soporte (T5, 80D, 6D Mark II...).
  - No depende de Live View ni del EDSDK.

No tiene vista en vivo (no es una cámara): `read_preview()` devuelve None.
"""
from __future__ import annotations

import os

from PIL import Image, ImageOps

IMG_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"}


class WatchFolderSource:
    """Vigila una carpeta y entrega por on_photo cada imagen nueva y completa."""

    name = "Carpeta observada (EOS Utility)"
    supports_physical_trigger = True  # el disparo lo hace el fotógrafo
    on_photo = None

    def __init__(self, folder: str) -> None:
        self.folder = folder
        self._seen: set[str] = set()
        self._sizes: dict[str, int] = {}  # para detectar archivos aún escribiéndose

    def start(self) -> None:
        if not os.path.isdir(self.folder):
            raise FileNotFoundError(f"No existe la carpeta: {self.folder}")
        # Los archivos que ya estaban se marcan como vistos (no reprocesar historial).
        self._seen = set(self._list())

    def _list(self) -> list[str]:
        try:
            return [os.path.join(self.folder, f) for f in os.listdir(self.folder)
                    if os.path.splitext(f)[1].lower() in IMG_EXTS]
        except OSError:
            return []

    def poll(self) -> None:
        for path in self._list():
            if path in self._seen:
                continue
            try:
                size = os.path.getsize(path)
            except OSError:
                continue
            # Esperar a que el archivo deje de crecer (EOS Utility todavía escribe).
            if self._sizes.get(path) != size:
                self._sizes[path] = size
                continue
            img = self._safe_open(path)
            if img is None:
                continue  # todavía no se puede leer; se reintenta en el próximo poll
            self._seen.add(path)
            self._sizes.pop(path, None)
            if self.on_photo is not None:
                self.on_photo(img)

    @staticmethod
    def _safe_open(path: str) -> Image.Image | None:
        try:
            with Image.open(path) as im:
                return ImageOps.exif_transpose(im).convert("RGB").copy()
        except Exception:  # noqa: BLE001
            return None

    def read_preview(self) -> Image.Image | None:
        return None

    def trigger(self) -> None:
        # No aplica: el disparo es físico (o desde EOS Utility).
        pass

    def stop(self) -> None:
        pass
