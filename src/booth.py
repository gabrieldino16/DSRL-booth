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
from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QComboBox, QDialog, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

import config
import delivery
import template as templates_mod
from camera import available_cameras, DummyBackend
from imaging_qt import pil_to_qpixmap, print_image
from processor import Job, compose_template, output_path, save_result, _load_frame


class _DeliveryWorker(QThread):
    """Corre una tarea de entrega (subir/enviar) sin congelar la ventana."""
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, fn) -> None:
        super().__init__()
        self._fn = fn

    def run(self) -> None:
        try:
            self.done.emit(self._fn())
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


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
        self._last_dest: str | None = None   # archivo guardado de la última foto
        self._last_url: str | None = None     # URL publicada (si se generó el QR)
        self._delivery_worker: _DeliveryWorker | None = None

        self.uploader = delivery.load_uploader(self.out_dir)

        # Estado de la sesión de capturas.
        self._session_photos: list[Image.Image] = []
        self._shot_index = 0
        self._countdown = 0
        self._in_session = False

        # Cámaras disponibles (Canon si está el SDK, webcams, simulada).
        self.cam_options = available_cameras()
        self._cam_index, self.camera = self._open_default_camera()

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
        top.addWidget(QLabel("📷"))
        self.camera_combo = QComboBox()
        for opt in self.cam_options:
            self.camera_combo.addItem(opt.label)
        self.camera_combo.setCurrentIndex(self._cam_index)
        self.camera_combo.currentIndexChanged.connect(self._select_camera)
        top.addWidget(self.camera_combo)
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

        # Fila 1: entrega de la foto.
        row1 = QHBoxLayout()
        print_btn = QPushButton("🖨  Imprimir")
        print_btn.clicked.connect(self._print_result)
        self.qr_btn = QPushButton("🔳  QR para descargar")
        self.qr_btn.clicked.connect(self._share_qr)
        self.email_btn = QPushButton("✉  Email")
        self.email_btn.clicked.connect(self._share_email)
        for b in (print_btn, self.qr_btn, self.email_btn):
            b.setMinimumHeight(52)
            b.setStyleSheet("font-size:16px; font-weight:bold;")
            row1.addWidget(b)
        v.addLayout(row1)

        # Fila 2: navegación.
        row2 = QHBoxLayout()
        again_btn = QPushButton("📷  Nueva sesión")
        again_btn.setMinimumHeight(46)
        again_btn.clicked.connect(self._new_photo)
        home_btn = QPushButton("← Inicio")
        home_btn.setMinimumHeight(46)
        home_btn.clicked.connect(self.close)
        row2.addWidget(again_btn, stretch=2)
        row2.addWidget(home_btn, stretch=1)
        v.addLayout(row2)
        return page

    # ---------- plantilla ----------
    def _on_template_changed(self, index: int) -> None:
        self.template = self.template_combo.itemData(index) or self.templates[0]
        self._frame_img = None  # se recarga en la próxima composición
        n = self.template.shots
        tomas = "1 foto" if n == 1 else f"{n} fotos"
        self.info_label.setText(f"{self.template.size_label} · {tomas}")

    # ---------- cámara ----------
    def _open_default_camera(self):
        """Abre la primera cámara que arranque, sin auto-iniciar la Canon."""
        for i, opt in enumerate(self.cam_options):
            if opt.label.startswith("Canon"):
                continue  # la Canon (EDSDK) se elige a mano
            try:
                cam = opt.factory()
                cam.start()
                return i, cam
            except Exception:  # noqa: BLE001
                continue
        cam = DummyBackend()
        cam.start()
        return len(self.cam_options) - 1, cam

    def _select_camera(self, index: int) -> None:
        if self._in_session or index == self._cam_index:
            return
        self.preview_timer.stop()
        try:
            self.camera.stop()
        except Exception:  # noqa: BLE001
            pass
        try:
            cam = self.cam_options[index].factory()
            cam.start()
            self.camera = cam
            self._cam_index = index
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "No se pudo abrir la cámara", str(exc))
            self.camera_combo.blockSignals(True)
            self.camera_combo.setCurrentIndex(self._cam_index)
            self.camera_combo.blockSignals(False)
            try:
                self.camera = self.cam_options[self._cam_index].factory()
                self.camera.start()
            except Exception:  # noqa: BLE001
                self.camera = DummyBackend()
                self.camera.start()
        self.preview_timer.start(self.PREVIEW_MS)

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
        self.camera_combo.setEnabled(False)
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
        self.camera_combo.setEnabled(True)

    def _save(self, result: Image.Image) -> str:
        os.makedirs(self.out_dir, exist_ok=True)
        job = Job(frame_path="", size=self.template.size, dpi=self.template.dpi)
        stem = datetime.now().strftime("foto_%Y%m%d_%H%M%S")
        dest = output_path(os.path.join(self.out_dir, stem), self.out_dir, job)
        return save_result(result, dest, job)

    # ---------- resultado ----------
    def _show_result(self, result: Image.Image, dest: str) -> None:
        self._last_dest = dest
        self._last_url = None
        pix = pil_to_qpixmap(result).scaled(
            self.result_view.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.result_view.setPixmap(pix)
        self.result_status.setText(f"Guardada en: {dest}")
        self.stack.setCurrentIndex(1)

    def _print_result(self) -> None:
        if self._last_result is not None:
            print_image(self._last_result, parent=self)

    # ---------- entrega: QR y email ----------
    def _share_qr(self) -> None:
        if not self._last_dest:
            return
        if self._last_url:  # ya se subió antes: mostrar el QR directo
            self._show_qr_dialog(self._last_url)
            return
        self.qr_btn.setEnabled(False)
        self.result_status.setText(f"Subiendo a {self.uploader.name}...")
        self._run_delivery(lambda: self.uploader.upload(self._last_dest),
                           self._on_qr_ready, self._on_delivery_error)

    def _on_qr_ready(self, url: str) -> None:
        self.qr_btn.setEnabled(True)
        self._last_url = url
        self.result_status.setText(f"Guardada en: {self._last_dest}")
        self._show_qr_dialog(url)

    def _show_qr_dialog(self, url: str) -> None:
        qr_img = delivery.make_qr(url)
        dlg = QDialog(self)
        dlg.setWindowTitle("QR para descargar")
        lay = QVBoxLayout(dlg)
        title = QLabel("Escaneá para descargar tu foto")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size:16px; font-weight:bold;")
        lay.addWidget(title)
        qr_label = QLabel()
        qr_label.setAlignment(Qt.AlignCenter)
        qr_label.setPixmap(pil_to_qpixmap(qr_img).scaled(
            360, 360, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        lay.addWidget(qr_label)
        link = QLabel(f'<a href="{url}">{url}</a>')
        link.setAlignment(Qt.AlignCenter)
        link.setOpenExternalLinks(True)
        link.setWordWrap(True)
        lay.addWidget(link)
        close_btn = QPushButton("Cerrar")
        close_btn.clicked.connect(dlg.accept)
        lay.addWidget(close_btn)
        dlg.exec()

    def _share_email(self) -> None:
        if not self._last_dest:
            return
        addr, ok = QInputDialog.getText(
            self, "Enviar por email", "Email del cliente:", QLineEdit.Normal)
        addr = addr.strip()
        if not ok or not addr:
            return
        self.email_btn.setEnabled(False)
        self.result_status.setText(f"Enviando a {addr}...")
        dest, link = self._last_dest, self._last_url
        self._run_delivery(
            lambda: delivery.send_email(addr, dest, link=link),
            lambda _: self._on_email_sent(addr), self._on_delivery_error)

    def _on_email_sent(self, addr: str) -> None:
        self.email_btn.setEnabled(True)
        self.result_status.setText(f"✓ Enviado a {addr}")

    def _on_delivery_error(self, msg: str) -> None:
        self.qr_btn.setEnabled(True)
        self.email_btn.setEnabled(True)
        self.result_status.setText(f"Guardada en: {self._last_dest}")
        QMessageBox.warning(self, "No se pudo completar", msg)

    def _run_delivery(self, fn, on_done, on_error) -> None:
        worker = _DeliveryWorker(fn)
        worker.done.connect(on_done)
        worker.failed.connect(on_error)
        worker.finished.connect(lambda: setattr(self, "_delivery_worker", None))
        self._delivery_worker = worker  # referencia viva mientras corre
        worker.start()

    def _new_photo(self) -> None:
        self.session_label.setText("")
        self.stack.setCurrentIndex(0)
        self.preview_timer.start(self.PREVIEW_MS)

    # ---------- cierre ----------
    def closeEvent(self, event) -> None:  # noqa: N802
        self.preview_timer.stop()
        self.countdown_timer.stop()
        for closer in (self.camera.stop, self.uploader.stop):
            try:
                closer()
            except Exception:  # noqa: BLE001
                pass
        self.closed.emit()
        super().closeEvent(event)
