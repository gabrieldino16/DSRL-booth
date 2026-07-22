"""Plantillas de la foto de salida (tira de fotocabina).

Una plantilla define cómo se arma la imagen final:
  - tamaño de papel + orientación del lienzo,
  - uno o más "huecos" de foto (dónde van las capturas de la cámara),
  - un marco PNG opcional por encima y un fondo opcional por debajo.

Las coordenadas de los huecos van en **fracciones 0..1** del lienzo, así la
plantilla es independiente del DPI: el mismo diseño sirve a 300 dpi o al que sea.

Las plantillas se pueden guardar/cargar como JSON (carpeta `plantillas/`). Además
hay unas cuantas prearmadas por código para que la app funcione sin configurar
nada. El editor visual vendrá más adelante y escribirá estos mismos JSON.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict

import config


def _size_by_label(label: str) -> "config.PrintSize":
    for s in config.PRINT_SIZES:
        if s.label == label:
            return s
    return config.PRINT_SIZES[0]


def _default_frame() -> str | None:
    """Primer marco PNG que haya en la carpeta marcos/, si existe."""
    marcos = os.path.join(os.getcwd(), "marcos")
    if os.path.isdir(marcos):
        for name in sorted(os.listdir(marcos)):
            if name.lower().endswith(".png"):
                return os.path.join(marcos, name)
    return None


@dataclass
class PhotoSlot:
    """Un hueco de foto dentro del lienzo, en fracciones 0..1."""
    x: float
    y: float
    w: float
    h: float
    rotation: float = 0.0
    fit: str = config.FIT_COVER


@dataclass
class Template:
    name: str
    size_label: str = "10x15 cm"
    landscape: bool = False
    slots: list[PhotoSlot] = field(default_factory=list)
    frame_path: str | None = None
    background_path: str | None = None
    background_color: tuple[int, int, int] = (255, 255, 255)
    dpi: int = config.DEFAULT_DPI

    @property
    def size(self) -> "config.PrintSize":
        return _size_by_label(self.size_label)

    @property
    def shots(self) -> int:
        """Cantidad de capturas que pide esta plantilla."""
        return len(self.slots)

    def canvas_size(self) -> tuple[int, int]:
        """Tamaño del lienzo en píxeles (ancho, alto)."""
        return self.size.pixels(self.dpi, self.landscape)

    # ---------- serialización ----------
    def to_dict(self) -> dict:
        d = asdict(self)
        d["background_color"] = list(self.background_color)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Template":
        slots = [PhotoSlot(**s) for s in d.get("slots", [])]
        return cls(
            name=d["name"],
            size_label=d.get("size_label", d.get("size", "10x15 cm")),
            landscape=bool(d.get("landscape", False)),
            slots=slots,
            frame_path=d.get("frame_path") or d.get("frame"),
            background_path=d.get("background_path") or d.get("background"),
            background_color=tuple(d.get("background_color", (255, 255, 255))),
            dpi=int(d.get("dpi", config.DEFAULT_DPI)),
        )

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, ensure_ascii=False, indent=2)


def load_json(path: str) -> Template:
    with open(path, encoding="utf-8") as fh:
        return Template.from_dict(json.load(fh))


def strip_template(name: str, n: int, size_label: str = "10x15 cm",
                   landscape: bool = False, frame_path: str | None = None,
                   side: float = 0.06, top: float = 0.04,
                   bottom: float = 0.10, gap: float = 0.025) -> Template:
    """Genera una tira vertical de `n` huecos iguales con márgenes parejos."""
    usable = 1.0 - top - bottom - gap * (n - 1)
    slot_h = usable / n
    slot_w = 1.0 - 2 * side
    slots = []
    y = top
    for _ in range(n):
        slots.append(PhotoSlot(x=side, y=round(y, 4), w=round(slot_w, 4),
                               h=round(slot_h, 4)))
        y += slot_h + gap
    return Template(name=name, size_label=size_label, landscape=landscape,
                    slots=slots, frame_path=frame_path)


def builtin_templates() -> list[Template]:
    """Plantillas prearmadas por código (siempre disponibles)."""
    frame = _default_frame()
    return [
        Template(
            name="Clásico (1 foto)",
            size_label="10x15 cm",
            landscape=False,
            slots=[PhotoSlot(x=0.0, y=0.0, w=1.0, h=1.0)],
            frame_path=frame,
        ),
        strip_template("Tira 3 fotos (vertical)", 3),
        strip_template("Tira 4 fotos (vertical)", 4),
    ]


def load_all(folder: str = "plantillas") -> list[Template]:
    """Plantillas prearmadas + las que haya en JSON dentro de `folder`."""
    templates = builtin_templates()
    path = os.path.join(os.getcwd(), folder)
    if os.path.isdir(path):
        for name in sorted(os.listdir(path)):
            if name.lower().endswith(".json"):
                try:
                    templates.append(load_json(os.path.join(path, name)))
                except Exception:  # noqa: BLE001
                    pass  # ignorar JSON inválidos, no romper la app
    return templates
