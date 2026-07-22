"""Editor visual de plantillas (como el editor de impresión de dslrBooth).

Un lienzo con la proporción del papel donde se agregan y acomodan los "huecos"
de foto (dónde caen las capturas de la sesión). Se pueden mover y redimensionar
arrastrando, o con valores exactos en el panel de la derecha. Además: tamaño de
papel, orientación, color de fondo y un marco PNG opcional. Se guarda/carga como
los JSON de `plantillas/` (el mismo formato que usa la fotocabina).

Para v1 el editor maneja huecos de foto + marco + fondo, que cubre la tira de
fotocabina. Textos, QR y capas de imagen sueltas quedan para una vuelta futura.
"""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, QRectF, Signal
from PySide6.QtGui import QBrush, QColor, QPen, QPixmap, QFont
from PySide6.QtWidgets import (
    QColorDialog, QComboBox, QDoubleSpinBox, QFileDialog, QGraphicsItem,
    QGraphicsRectItem, QGraphicsScene, QGraphicsView, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

import config
import template as templates_mod
from template import PhotoSlot, Template


class SlotItem(QGraphicsRectItem):
    """Hueco de foto: rectángulo movible y redimensionable (por esquinas)."""

    def __init__(self, slot: PhotoSlot, canvas: tuple[int, int], editor) -> None:
        super().__init__()
        self.slot = slot
        self.canvas = canvas
        self.editor = editor
        self._handle = None
        self.handle_size = max(canvas) * 0.02

        self.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable
                      | QGraphicsItem.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        self.setPen(QPen(QColor("#2d7d46"), max(2, int(canvas[0] * 0.004))))
        self.setBrush(QBrush(QColor(45, 125, 70, 60)))
        self._sync_from_slot()

    # ---- conversión modelo <-> escena ----
    def _sync_from_slot(self) -> None:
        cw, ch = self.canvas
        self.setPos(self.slot.x * cw, self.slot.y * ch)
        self.setRect(0, 0, self.slot.w * cw, self.slot.h * ch)

    def _write_to_slot(self) -> None:
        cw, ch = self.canvas
        self.slot.x = round(self.pos().x() / cw, 4)
        self.slot.y = round(self.pos().y() / ch, 4)
        self.slot.w = round(self.rect().width() / cw, 4)
        self.slot.h = round(self.rect().height() / ch, 4)
        self.editor.on_slot_geometry_changed(self)

    # ---- índice (orden de captura) ----
    def index(self) -> int:
        return self.editor.slots.index(self.slot) + 1

    # ---- handles de redimensionado ----
    def _handles(self) -> dict[str, QRectF]:
        r = self.rect()
        s = self.handle_size
        return {
            "tl": QRectF(r.left(), r.top(), s, s),
            "tr": QRectF(r.right() - s, r.top(), s, s),
            "bl": QRectF(r.left(), r.bottom() - s, s, s),
            "br": QRectF(r.right() - s, r.bottom() - s, s, s),
        }

    def _handle_at(self, pos):
        for name, rect in self._handles().items():
            if rect.contains(pos):
                return name
        return None

    def hoverMoveEvent(self, event):  # noqa: N802
        h = self._handle_at(event.pos())
        if h in ("tl", "br"):
            self.setCursor(Qt.SizeFDiagCursor)
        elif h in ("tr", "bl"):
            self.setCursor(Qt.SizeBDiagCursor)
        else:
            self.setCursor(Qt.SizeAllCursor)
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event):  # noqa: N802
        self._handle = self._handle_at(event.pos())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802
        if self._handle is None:
            super().mouseMoveEvent(event)
            return
        # Redimensionar arrastrando la esquina.
        r = QRectF(self.rect())
        p = event.pos()
        minsz = self.handle_size * 1.5
        if "l" in self._handle:
            r.setLeft(min(p.x(), r.right() - minsz))
        if "r" in self._handle:
            r.setRight(max(p.x(), r.left() + minsz))
        if "t" in self._handle:
            r.setTop(min(p.y(), r.bottom() - minsz))
        if "b" in self._handle:
            r.setBottom(max(p.y(), r.top() + minsz))
        self.setRect(r)

    def mouseReleaseEvent(self, event):  # noqa: N802
        self._handle = None
        # Normaliza: mueve el rect a pos y deja rect en (0,0,w,h).
        r = self.rect()
        self.setPos(self.pos() + r.topLeft())
        self.setRect(0, 0, r.width(), r.height())
        self._clamp()
        self._write_to_slot()
        super().mouseReleaseEvent(event)

    def itemChange(self, change, value):  # noqa: N802
        if change == QGraphicsItem.ItemPositionHasChanged and self.scene():
            self._write_to_slot()
        return super().itemChange(change, value)

    def _clamp(self) -> None:
        cw, ch = self.canvas
        w = min(self.rect().width(), cw)
        h = min(self.rect().height(), ch)
        self.setRect(0, 0, w, h)
        x = min(max(0, self.pos().x()), cw - w)
        y = min(max(0, self.pos().y()), ch - h)
        self.setPos(x, y)

    def paint(self, painter, option, widget=None):  # noqa: N802
        super().paint(painter, option, widget)
        # Número de orden en el centro.
        painter.setPen(QColor("#1b5e2f"))
        f = QFont()
        f.setBold(True)
        f.setPointSize(max(12, int(self.canvas[0] * 0.03)))
        painter.setFont(f)
        painter.drawText(self.rect(), Qt.AlignCenter, str(self.index()))
        # Handles.
        painter.setBrush(QBrush(QColor("#2d7d46")))
        painter.setPen(QPen(QColor("white"), 1))
        for rect in self._handles().values():
            painter.drawRect(rect)


class TemplateEditor(QMainWindow):
    closed = Signal()

    def __init__(self, template: Template | None = None) -> None:
        super().__init__()
        self.setWindowTitle("DSRL Booth — Editor de plantillas")
        self.resize(1100, 780)

        self.tpl = template or templates_mod.strip_template("Nueva plantilla", 3)
        self.slots: list[PhotoSlot] = list(self.tpl.slots)
        self._syncing = False

        self._build_ui()
        self._rebuild_scene()

    # ---------- UI ----------
    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)

        outer.addLayout(self._build_toolbar())

        body = QHBoxLayout()
        outer.addLayout(body, stretch=1)

        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHints(self.view.renderHints())
        self.scene.selectionChanged.connect(self._on_selection_changed)
        body.addWidget(self.view, stretch=1)

        body.addWidget(self._build_side_panel())

    def _build_toolbar(self) -> QHBoxLayout:
        bar = QHBoxLayout()

        back = QPushButton("← Inicio")
        back.clicked.connect(self.close)
        bar.addWidget(back)

        bar.addWidget(QLabel("Nombre:"))
        self.name_edit = QLineEdit(self.tpl.name)
        bar.addWidget(self.name_edit, stretch=1)

        bar.addWidget(QLabel("Papel:"))
        self.size_combo = QComboBox()
        for s in config.PRINT_SIZES:
            self.size_combo.addItem(s.label, s.label)
        self.size_combo.setCurrentText(self.tpl.size_label)
        self.size_combo.currentIndexChanged.connect(self._on_canvas_changed)
        bar.addWidget(self.size_combo)

        self.orient_combo = QComboBox()
        self.orient_combo.addItem("Vertical", False)
        self.orient_combo.addItem("Apaisado", True)
        self.orient_combo.setCurrentIndex(1 if self.tpl.landscape else 0)
        self.orient_combo.currentIndexChanged.connect(self._on_canvas_changed)
        bar.addWidget(self.orient_combo)

        bg_btn = QPushButton("Color de fondo")
        bg_btn.clicked.connect(self._pick_bg_color)
        bar.addWidget(bg_btn)

        frame_btn = QPushButton("Marco PNG...")
        frame_btn.clicked.connect(self._pick_frame)
        bar.addWidget(frame_btn)
        clear_frame = QPushButton("Sin marco")
        clear_frame.clicked.connect(self._clear_frame)
        bar.addWidget(clear_frame)
        return bar

    def _build_side_panel(self) -> QWidget:
        panel = QWidget()
        panel.setFixedWidth(240)
        v = QVBoxLayout(panel)

        v.addWidget(QLabel("<b>Huecos de foto</b>"))
        row = QHBoxLayout()
        add = QPushButton("+ Agregar")
        add.clicked.connect(self._add_slot)
        dup = QPushButton("Duplicar")
        dup.clicked.connect(self._duplicate_slot)
        rm = QPushButton("Eliminar")
        rm.clicked.connect(self._delete_slot)
        for b in (add, dup, rm):
            row.addWidget(b)
        v.addLayout(row)

        order = QHBoxLayout()
        up = QPushButton("↑ Orden")
        up.clicked.connect(lambda: self._reorder(-1))
        down = QPushButton("↓ Orden")
        down.clicked.connect(lambda: self._reorder(1))
        order.addWidget(up)
        order.addWidget(down)
        v.addLayout(order)

        v.addWidget(QLabel("<b>Hueco seleccionado</b> (% del lienzo)"))
        self.spins: dict[str, QDoubleSpinBox] = {}
        for key, label in (("x", "X"), ("y", "Y"), ("w", "Ancho"), ("h", "Alto")):
            hb = QHBoxLayout()
            hb.addWidget(QLabel(label))
            sp = QDoubleSpinBox()
            sp.setRange(0, 100)
            sp.setSuffix(" %")
            sp.setDecimals(1)
            sp.valueChanged.connect(self._on_spin_changed)
            self.spins[key] = sp
            hb.addWidget(sp)
            v.addLayout(hb)

        hb = QHBoxLayout()
        hb.addWidget(QLabel("Ajuste"))
        self.fit_combo = QComboBox()
        for fkey in (config.FIT_COVER, config.FIT_CONTAIN, config.FIT_STRETCH):
            self.fit_combo.addItem(config.FIT_LABELS[fkey], fkey)
        self.fit_combo.currentIndexChanged.connect(self._on_fit_changed)
        hb.addWidget(self.fit_combo)
        v.addLayout(hb)

        v.addStretch(1)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setStyleSheet("color:#888;")
        v.addWidget(self.status)

        save = QPushButton("💾 Guardar")
        save.setMinimumHeight(44)
        save.setStyleSheet("font-weight:bold; background:#2d7d46; color:white;")
        save.clicked.connect(self._save)
        v.addWidget(save)

        load = QPushButton("Abrir plantilla...")
        load.clicked.connect(self._load)
        v.addWidget(load)
        return panel

    # ---------- escena ----------
    def _canvas(self) -> tuple[int, int]:
        size = templates_mod._size_by_label(self.size_combo.currentData())
        return size.pixels(config.DEFAULT_DPI, self.orient_combo.currentData())

    def _rebuild_scene(self) -> None:
        cw, ch = self._canvas()
        self.scene.clear()
        self.scene.setSceneRect(0, 0, cw, ch)
        # Fondo (color).
        self.scene.setBackgroundBrush(QColor(200, 200, 200))
        bg = self.scene.addRect(0, 0, cw, ch, QPen(Qt.NoPen),
                                QBrush(QColor(*self.tpl.background_color)))
        bg.setZValue(-10)
        # Marco de referencia (semitransparente) si hay.
        if self.tpl.frame_path and os.path.isfile(self.tpl.frame_path):
            pm = QPixmap(self.tpl.frame_path).scaled(
                cw, ch, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            item = self.scene.addPixmap(pm)
            item.setOpacity(0.5)
            item.setZValue(-5)
        # Huecos.
        for slot in self.slots:
            self.scene.addItem(SlotItem(slot, (cw, ch), self))
        self.view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        if self.scene.sceneRect().width():
            self.view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)

    def _selected_item(self) -> SlotItem | None:
        for it in self.scene.selectedItems():
            if isinstance(it, SlotItem):
                return it
        return None

    # ---------- callbacks de geometría ----------
    def on_slot_geometry_changed(self, item: SlotItem) -> None:
        if self._selected_item() is item:
            self._load_spins(item.slot)

    def _on_selection_changed(self) -> None:
        item = self._selected_item()
        if item:
            self._load_spins(item.slot)
            self.fit_combo.blockSignals(True)
            idx = self.fit_combo.findData(item.slot.fit)
            self.fit_combo.setCurrentIndex(max(0, idx))
            self.fit_combo.blockSignals(False)

    def _load_spins(self, slot: PhotoSlot) -> None:
        self._syncing = True
        self.spins["x"].setValue(slot.x * 100)
        self.spins["y"].setValue(slot.y * 100)
        self.spins["w"].setValue(slot.w * 100)
        self.spins["h"].setValue(slot.h * 100)
        self._syncing = False

    def _on_spin_changed(self) -> None:
        if self._syncing:
            return
        item = self._selected_item()
        if not item:
            return
        item.slot.x = self.spins["x"].value() / 100
        item.slot.y = self.spins["y"].value() / 100
        item.slot.w = self.spins["w"].value() / 100
        item.slot.h = self.spins["h"].value() / 100
        item._sync_from_slot()

    def _on_fit_changed(self) -> None:
        item = self._selected_item()
        if item:
            item.slot.fit = self.fit_combo.currentData()

    # ---------- acciones de huecos ----------
    def _add_slot(self) -> None:
        self.slots.append(PhotoSlot(x=0.1, y=0.1, w=0.4, h=0.3))
        self._rebuild_scene()

    def _duplicate_slot(self) -> None:
        item = self._selected_item()
        if not item:
            return
        s = item.slot
        self.slots.append(PhotoSlot(x=min(s.x + 0.03, 0.9), y=min(s.y + 0.03, 0.9),
                                    w=s.w, h=s.h, rotation=s.rotation, fit=s.fit))
        self._rebuild_scene()

    def _delete_slot(self) -> None:
        item = self._selected_item()
        if item and item.slot in self.slots:
            self.slots.remove(item.slot)
            self._rebuild_scene()

    def _reorder(self, direction: int) -> None:
        item = self._selected_item()
        if not item:
            return
        i = self.slots.index(item.slot)
        j = i + direction
        if 0 <= j < len(self.slots):
            self.slots[i], self.slots[j] = self.slots[j], self.slots[i]
            self._rebuild_scene()

    # ---------- lienzo / apariencia ----------
    def _on_canvas_changed(self) -> None:
        self._rebuild_scene()

    def _pick_bg_color(self) -> None:
        col = QColorDialog.getColor(QColor(*self.tpl.background_color), self,
                                    "Color de fondo")
        if col.isValid():
            self.tpl.background_color = (col.red(), col.green(), col.blue())
            self._rebuild_scene()

    def _pick_frame(self) -> None:
        start = os.path.join(os.getcwd(), "marcos")
        path, _ = QFileDialog.getOpenFileName(
            self, "Elegir marco PNG", start if os.path.isdir(start) else "",
            "PNG (*.png)")
        if path:
            self.tpl.frame_path = path
            self._rebuild_scene()

    def _clear_frame(self) -> None:
        self.tpl.frame_path = None
        self._rebuild_scene()

    # ---------- guardar / cargar ----------
    def _build_template(self) -> Template:
        return Template(
            name=self.name_edit.text().strip() or "Sin nombre",
            size_label=self.size_combo.currentData(),
            landscape=self.orient_combo.currentData(),
            slots=list(self.slots),
            frame_path=self.tpl.frame_path,
            background_path=self.tpl.background_path,
            background_color=self.tpl.background_color,
        )

    def _save(self) -> None:
        if not self.slots:
            QMessageBox.warning(self, "Sin huecos", "Agregá al menos un hueco de foto.")
            return
        folder = os.path.join(os.getcwd(), "plantillas")
        os.makedirs(folder, exist_ok=True)
        default = os.path.join(folder, self.name_edit.text().strip() or "plantilla")
        path, _ = QFileDialog.getSaveFileName(
            self, "Guardar plantilla", default + ".json", "JSON (*.json)")
        if not path:
            return
        tpl = self._build_template()
        tpl.save(path)
        self.status.setText(f"Guardada: {os.path.basename(path)}")

    def _load(self) -> None:
        folder = os.path.join(os.getcwd(), "plantillas")
        path, _ = QFileDialog.getOpenFileName(
            self, "Abrir plantilla", folder if os.path.isdir(folder) else "",
            "JSON (*.json)")
        if not path:
            return
        try:
            tpl = templates_mod.load_json(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "No se pudo abrir", str(exc))
            return
        self.tpl = tpl
        self.slots = list(tpl.slots)
        self.name_edit.setText(tpl.name)
        self.size_combo.setCurrentText(tpl.size_label)
        self.orient_combo.setCurrentIndex(1 if tpl.landscape else 0)
        self._rebuild_scene()
        self.status.setText(f"Abierta: {os.path.basename(path)}")

    def closeEvent(self, event):  # noqa: N802
        self.closed.emit()
        super().closeEvent(event)
