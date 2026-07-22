"""Modo fotocabina en vivo (Flujo B).

Preview de la cámara -> sesión de N capturas (según la plantilla elegida) ->
composición en la foto de salida (tira de fotocabina) -> pantalla de resultado
con opción de imprimir.

Reusa:
  - camera.open_default_camera()   -> fuente de video (webcam o simulada)
  - template.load_all()            -> plantillas disponibles (huecos + marco)
  - processor.compose_template()   -> capturas + plantilla en memoria
  - imaging_qt.print_image()       -> impresión con el diálogo de Windows
"""
from __future__ import annotations

import os
from datetime import datetime

from PIL import Image
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
    QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

import config
import template as templates_mod
from camera import open_default_camera
from imaging_qt import pil_to_qpixmap, print_image
from processor import Job, compose_template, output_path, save_result, _load_frame


class BoothWindow(QMainWindow):
    """Ventana de fotocabina: preview en vivo -> sesión N tomas -> resultado."""

    closed = Signal()

    PREVIEW_MS = 40          # intervalo del preview (~25 fps)
    COUNTDOWN_FROM = 3       # cuenta regresiva antes de cada toma
    SHOT_PAUSE_MS = 1200     # pausa entre tomas mostrando "¡Foto lista!"

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("DSRL Booth — Fotocabina en vivo")
        self.resize(1000, 760)

        self.out_dir = os.path.join(os.getcwd(), "salida")
        self.templates = templates_mod.load_all()
        self.template = self.templates[0]
        self._frame_img: Image.Image | None = None
        self._last_result: Image.Image | None = None

        # Estado de la sesión de capturas.
        self._session_photos: list[Image.Image] = []
        self._shot_index = 0
        self._countdown = 0
        self._in_session = False

        self.camera = open_default_camera()

        self._build_ui()
        self._on_template_changed(0)

        self.preview_timer = QTimer(self)
        self.preview_timer.timeout.connect(self._update_preview)
        self.preview_timer.start(self.PREVIEW_MS)

        self.countdown_timer = QTimer(self)
        self.countdown_timer.setInterval(1000)
        self.countdown_timer.timeout.connect(self._tick_countdown)

    # ---------- interfaz ----------
    def _build_ui(self) -> None:
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        self.stack.addWidget(self._build_live_page())    # 0
        self.stack.addWidget(self._build_result_page())  # 1

    def _build_live_page(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)

        top = QHBoxLayout()
        back_btn = QPushButton("← Inicio")
        back_btn.clicked.connect(self.close)
        top.addWidget(back_btn)

        top.addWidget(QLabel("<b>Plantilla:</b>"))
        self.template_combo = QComboBox()
        for t in self.templates:
            self.template_combo.addItem(t.name, t)
        self.template_combo.currentIndexChanged.connect(self._on_template_changed)
        top.addWidget(self.template_combo)

        self.info_label = QLabel("")
        self.info_label.setStyleSheet("color:#888;")
        top.addWidget(self.info_label)

        top.addStretch(1)
        top.addWidget(QLabel(f"📷 {self.camera.name}"))
        v.addLayout(top)

        # Estado de la sesión (Toma X de N / mensajes).
        self.session_label = QLabel("")
        self.session_label.setAlignment(Qt.AlignCenter)
        self.session_label.setStyleSheet("font-size:18px; font-weight:bold;")
        self.session_label.setFixedHeight(28)
        v.addWidget(self.session_label)

        self.preview = QLabel("Iniciando cámara...")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(640, 400)
        self.preview.setStyleSheet("background:#000; color:#888;")
        v.addWidget(self.preview, stretch=1)

        self.shutter_btn = QPushButton("📸  EMPEZAR")
        self.shutter_btn.setMinimumHeight(64)
        self.shutter_btn.setStyleSheet(
            "font-size:22px; font-weight:bold; background:#2d7d46; color:white;")
        self.shutter_btn.clicked.connect(self._start_session)
        v.addWidget(self.shutter_btn)
        return page

    def _build_result_page(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)

        self.result_view = QLabel()
        self.result_view.setAlignment(Qt.AlignCenter)
        self.result_view.setMinimumSize(640, 400)
        self.result_view.setStyleSheet("background:#111;")
        v.addWidget(self.result_view, stretch=1)

        self.result_status = QLabel("")
        self.result_status.setAlignment(Qt.AlignCenter)
        v.addWidget(self.result_status)

        row = QHBoxLayout()
        print_btn = QPushButton("🖨  Imprimir")
        print_btn.setMinimumHeight(52)
        print_btn.setStyleSheet("font-size:16px; font-weight:bold;")
        print_btn.clicked.connect(self._print_result)

        again_btn = QPushButton("📷  Nueva sesión")
        again_btn.setMinimumHeight(52)
        again_btn.setStyleSheet("font-size:16px; font-weight:bold;")
        again_btn.clicked.connect(self._new_photo)

        home_btn = QPushButton("← Inicio")
        home_btn.setMinimumHeight(52)
        home_btn.clicked.connect(self.close)

        row.addWidget(print_btn, stretch=2)
        row.addWidget(again_btn, stretch=2)
        row.addWidget(home_btn, stretch=1)
        v.addLayout(row)
        return page

    # ---------- plantilla ----------
    def _on_template_changed(self, index: int) -> None:
        self.template = self.template_combo.itemData(index) or self.templates[0]
        self._frame_img = None  # se recarga en la próxima composición
        n = self.template.shots
        tomas = "1 foto" if n == 1 else f"{n} fotos"
        self.info_label.setText(f"{self.template.size_label} · {tomas}")

    # ---------- preview en vivo ----------
    def _update_preview(self) -> None:
        img = self.camera.read_preview()
        if img is None:
            return
        pix = pil_to_qpixmap(img).scaled(
            self.preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        if self._countdown > 0:
            self._paint_countdown(pix)
        self.preview.setPixmap(pix)

    def _paint_countdown(self, pix) -> None:
        painter = QPainter(pix)
        font = QFont()
        font.setPointSize(max(24, min(pix.width(), pix.height()) // 4))
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(pix.rect(), Qt.AlignCenter, str(self._countdown))
        painter.end()

    # ---------- sesión de capturas ----------
    def _start_session(self) -> None:
        self._session_photos = []
        self._shot_index = 0
        self._in_session = True
        self.shutter_btn.setEnabled(False)
        self.template_combo.setEnabled(False)
        self._next_shot()

    def _next_shot(self) -> None:
        n = self.template.shots
        self.session_label.setText(f"Toma {self._shot_index + 1} de {n}  —  ¡preparate!")
        self._countdown = self.COUNTDOWN_FROM
        self.countdown_timer.start()

    def _tick_countdown(self) -> None:
        self._countdown -= 1
        if self._countdown <= 0:
            self.countdown_timer.stop()
            self._capture_shot()

    def _capture_shot(self) -> None:
        try:
            photo = self.camera.capture()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Error al capturar", str(exc))
            self._abort_session()
            return

        self._session_photos.append(photo)
        self._shot_index += 1
        n = self.template.shots

        if self._shot_index < n:
            self.session_label.setText(f"¡Foto {self._shot_index} de {n} lista!")
            QTimer.singleShot(self.SHOT_PAUSE_MS, self._next_shot)
        else:
            self.session_label.setText("¡Listo! Armando la foto...")
            QTimer.singleShot(300, self._finish_session)

    def _finish_session(self) -> None:
        self.preview_timer.stop()
        try:
            if self._frame_img is None and self.template.frame_path:
                self._frame_img = _load_frame(self.template.frame_path)
            result = compose_template(self._session_photos, self.template,
                                      frame=self._frame_img)
            dest = self._save(result)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Error al componer", str(exc))
            self._abort_session()
            self.preview_timer.start(self.PREVIEW_MS)
            return

        self._last_result = result
        self._show_result(result, dest)
        self._end_session_state()

    def _abort_session(self) -> None:
        self.countdown_timer.stop()
        self._countdown = 0
        self.session_label.setText("")
        self._end_session_state()

    def _end_session_state(self) -> None:
        self._in_session = False
        self.shutter_btn.setEnabled(True)
        self.template_combo.setEnabled(True)

    def _save(self, result: Image.Image) -> str:
        os.makedirs(self.out_dir, exist_ok=True)
        job = Job(frame_path="", size=self.template.size, dpi=self.template.dpi)
        stem = datetime.now().strftime("foto_%Y%m%d_%H%M%S")
        dest = output_path(os.path.join(self.out_dir, stem), self.out_dir, job)
        return save_result(result, dest, job)

    # ---------- resultado ----------
    def _show_result(self, result: Image.Image, dest: str) -> None:
        pix = pil_to_qpixmap(result).scaled(
            self.result_view.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.result_view.setPixmap(pix)
        self.result_status.setText(f"Guardada en: {dest}")
        self.stack.setCurrentIndex(1)

    def _print_result(self) -> None:
        if self._last_result is not None:
            print_image(self._last_result, parent=self)

    def _new_photo(self) -> None:
        self.session_label.setText("")
        self.stack.setCurrentIndex(0)
        self.preview_timer.start(self.PREVIEW_MS)

    # ---------- cierre ----------
    def closeEvent(self, event) -> None:  # noqa: N802
        self.preview_timer.stop()
        self.countdown_timer.stop()
        try:
            self.camera.stop()
        except Exception:  # noqa: BLE001
            pass
        self.closed.emit()
        super().closeEvent(event)
