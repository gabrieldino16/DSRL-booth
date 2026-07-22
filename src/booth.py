"""Modo fotocabina en vivo (Flujo B) — versión mínima.

Muestra el preview de la cámara, dispara con cuenta regresiva, compone la
captura con un marco PNG y muestra el resultado con opción de imprimir.

Reusa las piezas ya existentes:
  - camera.open_default_camera()  -> fuente de video (webcam o simulada)
  - processor.compose_image()     -> foto + marco en memoria
  - imaging_qt.print_image()      -> impresión con el diálogo de Windows
"""
from __future__ import annotations

import os
from datetime import datetime

from PIL import Image
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
    QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

import config
from camera import open_default_camera
from imaging_qt import pil_to_qpixmap, print_image
from processor import Job, compose_image, output_path, save_result, _load_frame


def _default_frame() -> str | None:
    """Primer marco PNG que haya en la carpeta marcos/, si existe."""
    marcos = os.path.join(os.getcwd(), "marcos")
    if os.path.isdir(marcos):
        for name in sorted(os.listdir(marcos)):
            if name.lower().endswith(".png"):
                return os.path.join(marcos, name)
    return None


class BoothWindow(QMainWindow):
    """Ventana de fotocabina: preview en vivo -> disparo -> resultado."""

    closed = Signal()  # avisa al inicio cuando esta ventana se cierra

    PREVIEW_MS = 40         # intervalo del preview (~25 fps)
    COUNTDOWN_FROM = 3      # cuenta regresiva antes de disparar

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("DSRL Booth — Fotocabina en vivo")
        self.resize(1000, 720)

        self.out_dir = os.path.join(os.getcwd(), "salida")
        self.frame_path: str | None = _default_frame()
        self._frame_img: Image.Image | None = None
        self._last_result: Image.Image | None = None
        self._countdown = 0

        self.camera = open_default_camera()

        self._build_ui()
        self._refresh_frame_label()

        # Timer del preview en vivo.
        self.preview_timer = QTimer(self)
        self.preview_timer.timeout.connect(self._update_preview)
        self.preview_timer.start(self.PREVIEW_MS)

        # Timer de la cuenta regresiva (1 segundo por paso).
        self.countdown_timer = QTimer(self)
        self.countdown_timer.setInterval(1000)
        self.countdown_timer.timeout.connect(self._tick_countdown)

    # ---------- construcción de la interfaz ----------
    def _build_ui(self) -> None:
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        self.stack.addWidget(self._build_live_page())    # índice 0
        self.stack.addWidget(self._build_result_page())  # índice 1

    def _build_live_page(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)

        # Barra superior: inicio + marco + tamaño + cámara.
        top = QHBoxLayout()
        back_btn = QPushButton("← Inicio")
        back_btn.clicked.connect(self.close)
        top.addWidget(back_btn)

        self.frame_label = QLabel()
        top.addWidget(self.frame_label)
        frame_btn = QPushButton("Cambiar marco...")
        frame_btn.clicked.connect(self._pick_frame)
        top.addWidget(frame_btn)

        top.addWidget(QLabel("Tamaño:"))
        self.size_combo = QComboBox()
        for s in config.PRINT_SIZES:
            self.size_combo.addItem(s.label, s)
        top.addWidget(self.size_combo)

        top.addStretch(1)
        top.addWidget(QLabel(f"📷 {self.camera.name}"))
        v.addLayout(top)

        # Preview en vivo (ocupa el resto).
        self.preview = QLabel("Iniciando cámara...")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(640, 400)
        self.preview.setStyleSheet("background:#000; color:#888;")
        v.addWidget(self.preview, stretch=1)

        # Botón de disparo.
        self.shutter_btn = QPushButton("📸  DISPARAR")
        self.shutter_btn.setMinimumHeight(64)
        self.shutter_btn.setStyleSheet(
            "font-size:22px; font-weight:bold; background:#2d7d46; color:white;")
        self.shutter_btn.clicked.connect(self._start_countdown)
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

        again_btn = QPushButton("📷  Nueva foto")
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

    # ---------- marco ----------
    def _refresh_frame_label(self) -> None:
        name = os.path.basename(self.frame_path) if self.frame_path else "sin marco"
        self.frame_label.setText(f"<b>Marco:</b> {name}")

    def _pick_frame(self) -> None:
        start = os.path.join(os.getcwd(), "marcos")
        path, _ = QFileDialog.getOpenFileName(
            self, "Elegir marco PNG", start if os.path.isdir(start) else "",
            "PNG (*.png)")
        if path:
            self.frame_path = path
            self._frame_img = None  # se recarga en el próximo disparo
            self._refresh_frame_label()

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

    # ---------- disparo ----------
    def _start_countdown(self) -> None:
        if not self.frame_path:
            QMessageBox.warning(self, "Falta el marco",
                                "Elegí un marco PNG antes de disparar.")
            return
        self.shutter_btn.setEnabled(False)
        self._countdown = self.COUNTDOWN_FROM
        self.countdown_timer.start()

    def _tick_countdown(self) -> None:
        self._countdown -= 1
        if self._countdown <= 0:
            self.countdown_timer.stop()
            self._capture()

    def _capture(self) -> None:
        self.preview_timer.stop()
        try:
            photo = self.camera.capture()
            if self._frame_img is None:
                self._frame_img = _load_frame(self.frame_path)
            job = Job(frame_path=self.frame_path, size=self.size_combo.currentData())
            result = compose_image(photo, job, frame=self._frame_img)
            dest = self._save(result, job)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Error al capturar", str(exc))
            self.shutter_btn.setEnabled(True)
            self.preview_timer.start(self.PREVIEW_MS)
            return

        self._last_result = result
        self._show_result(result, dest)
        self.shutter_btn.setEnabled(True)

    def _save(self, result: Image.Image, job: Job) -> str:
        os.makedirs(self.out_dir, exist_ok=True)
        stem = datetime.now().strftime("foto_%Y%m%d_%H%M%S")
        fake = os.path.join(self.out_dir, stem)  # output_path le agrega sufijo/ext
        dest = output_path(fake, self.out_dir, job)
        return save_result(result, dest, job)

    def _show_result(self, result: Image.Image, dest: str) -> None:
        pix = pil_to_qpixmap(result).scaled(
            self.result_view.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.result_view.setPixmap(pix)
        self.result_status.setText(f"Guardada en: {dest}")
        self.stack.setCurrentIndex(1)

    def _print_result(self) -> None:
        if self._last_result is None:
            return
        print_image(self._last_result, parent=self)

    def _new_photo(self) -> None:
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
