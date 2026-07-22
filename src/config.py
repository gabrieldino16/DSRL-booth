"""Configuracion central de DSRL Booth: tamanos de impresion, DPI y ajustes."""
from __future__ import annotations

from dataclasses import dataclass

# Resolucion de impresion. La K60 (y la fotografia en general) trabaja a 300 DPI.
DEFAULT_DPI = 300

# Calidad JPG de salida (0-100). 95 es visualmente indistinguible del original.
JPG_QUALITY = 95


@dataclass(frozen=True)
class PrintSize:
    """Un tamano de papel definido por su lado corto y largo en centimetros."""
    label: str
    short_cm: float
    long_cm: float

    def pixels(self, dpi: int, landscape: bool) -> tuple[int, int]:
        """Devuelve (ancho, alto) en pixeles al DPI dado.

        landscape=True -> el lado largo es horizontal.
        """
        long_px = self._cm_to_px(self.long_cm, dpi)
        short_px = self._cm_to_px(self.short_cm, dpi)
        if landscape:
            return long_px, short_px
        return short_px, long_px

    @staticmethod
    def _cm_to_px(cm: float, dpi: int) -> int:
        return round(cm / 2.54 * dpi)


# Tamanos disponibles en la app. Agregar mas es tan simple como sumar a la lista.
PRINT_SIZES: list[PrintSize] = [
    PrintSize("10x15 cm", 10.0, 15.0),
    PrintSize("15x20 cm", 15.0, 20.0),
    PrintSize("13x18 cm", 13.0, 18.0),
    PrintSize("9x13 cm", 9.0, 13.0),
]


# Modos de ajuste cuando la foto no tiene la misma proporcion que el papel.
FIT_COVER = "cover"      # recortar para llenar (predeterminado elegido por el usuario)
FIT_CONTAIN = "contain"  # foto entera con borde de relleno
FIT_STRETCH = "stretch"  # estirar hasta llenar (deforma)

FIT_LABELS = {
    FIT_COVER: "Recortar para llenar",
    FIT_CONTAIN: "Ajustar entera (con borde)",
    FIT_STRETCH: "Estirar para llenar",
}

DEFAULT_FIT = FIT_COVER

# Formatos de salida soportados.
FORMAT_JPG = "jpg"
FORMAT_PNG = "png"
DEFAULT_FORMAT = FORMAT_JPG

# Sufijo agregado al nombre del archivo de salida.
OUTPUT_SUFFIX = "_marco"
