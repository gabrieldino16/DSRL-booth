"""Interfaz grafica de DSRL Booth (PySide6).

Flujo de una sesion:
  1. Seleccionar el marco PNG.
  2. Elegir tamano de impresion y modo de ajuste.
  3. Agregar fotos (boton o arrastrando a la lista).
  4. Elegir carpeta de salida y presionar CREAR.
"""
from __future__ import annotations

import os

from PIL import Image
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QProgressBar,
    QPushButton, QVBoxLayout, QWidget,
)

import config
from processor import Job, process_one, _load_frame

PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}


def _is_photo(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in PHOTO_EXTS


class PhotoList(QListWidget):
    """Lista de fotos que acepta archivos arrastrados desde el explorador."""

    def __init__(self) -> None:
        super().__init__()
        self.setSelectionMode(QListWidget.ExtendedSelection)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        paths: list[str] = []
        for url in event.mimeData().urls():
            p = url.toLocalFile()
            if os.path.isdir(p):
                for name in sorted(os.listdir(p)):
                    full = os.path.join(p, name)
                    if os.path.isfile(full) and _is_photo(full):
                        paths.append(full)
            elif _is_photo(p):
                paths.append(p)
        self.add_paths(paths)

    def add_paths(self, paths: list[str]) -> None:
        existing = {self.item(i).data(Qt.UserRole) for i in range(self.count())}
        for p in paths:
            if p in existing:
                continue
            item = QListWidgetItem(os.path.basename(p))
            item.setData(Qt.UserRole, p)
            item.setToolTip(p)
            self.addItem(item)

    def all_paths(self) -> list[str]:
        return [self.item(i).data(Qt.UserRole) for i in range(self.count())]


class Worker(QThread):
    """Procesa las fotos en un hilo aparte para no congelar la ventana."""
    progress = Signal(int, int, str)   # actual, total, nombre
    failed = Signal(str, str)          # ruta, error
    finished_all = Signal(int, int)    # ok, total

    def __init__(self, photos: list[str], out_dir: str, job: Job) -> None:
        super().__init__()
        self.photos = photos
        self.out_dir = out_dir
        self.job = job

    def run(self) -> None:
        total = len(self.photos)
        ok = 0
        # Carga el marco una sola vez y lo reutiliza para todas las fotos.
        frame = _load_frame(self.job.frame_path)
        for i, photo in enumerate(self.photos, start=1):
            self.progress.emit(i, total, os.path.basename(photo))
            try:
                process_one(photo, self.out_dir, self.job, frame=frame)
                ok += 1
            except Exception as exc:  # noqa: BLE001
                self.failed.emit(photo, str(exc))
        self.finished_all.emit(ok, total)


class MainWindow(QMainWindow):
    """Modo lote (Flujo A): componer una tanda de fotos con un marco."""

    closed = Signal()  # avisa al inicio cuando esta ventana se cierra

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("DSRL Booth — Preparar tanda")
        self.resize(880, 620)

        self.frame_path: str | None = None
        self.out_dir: str = os.path.join(os.getcwd(), "salida")
        self.worker: Worker | None = None

        self._build_ui()

    def closeEvent(self, event) -> None:  # noqa: N802
        self.closed.emit()
        super().closeEvent(event)

    # ---------- construccion de la interfaz ----------
    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)

        # --- barra superior: volver al inicio ---
        top = QHBoxLayout()
        back_btn = QPushButton("← Inicio")
        back_btn.clicked.connect(self.close)
        top.addWidget(back_btn)
        top.addWidget(QLabel("<b>Preparar tanda (lote)</b>"))
        top.addStretch(1)
        outer.addLayout(top)

        columns = QWidget()
        layout = QHBoxLayout(columns)
        layout.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(columns, stretch=1)

        # --- columna izquierda: fotos ---
        left = QVBoxLayout()
        left.addWidget(QLabel("<b>Fotos de la sesion</b>"))
        self.photo_list = PhotoList()
        left.addWidget(self.photo_list, stretch=1)

        btns = QHBoxLayout()
        add_btn = QPushButton("Agregar fotos...")
        add_btn.clicked.connect(self._pick_photos)
        rm_btn = QPushButton("Quitar")
        rm_btn.clicked.connect(self._remove_selected)
        clr_btn = QPushButton("Limpiar")
        clr_btn.clicked.connect(self.photo_list.clear)
        for b in (add_btn, rm_btn, clr_btn):
            btns.addWidget(b)
        left.addLayout(btns)
        left.addWidget(QLabel("Tambien podes arrastrar fotos o carpetas a la lista."))

        # --- columna derecha: opciones ---
        right = QVBoxLayout()
        right.setSpacing(10)

        right.addWidget(QLabel("<b>1. Marco (PNG)</b>"))
        self.frame_preview = QLabel("Sin marco")
        self.frame_preview.setAlignment(Qt.AlignCenter)
        self.frame_preview.setFixedSize(220, 220)
        self.frame_preview.setFrameShape(QFrame.StyledPanel)
        self.frame_preview.setStyleSheet("background:#2a2a2a; color:#aaa;")
        right.addWidget(self.frame_preview, alignment=Qt.AlignCenter)
        frame_btn = QPushButton("Seleccionar marco...")
        frame_btn.clicked.connect(self._pick_frame)
        right.addWidget(frame_btn)

        right.addWidget(QLabel("<b>2. Tamano de impresion</b>"))
        self.size_combo = QComboBox()
        for s in config.PRINT_SIZES:
            self.size_combo.addItem(s.label, s)
        right.addWidget(self.size_combo)

        right.addWidget(QLabel("<b>3. Ajuste de la foto</b>"))
        self.fit_combo = QComboBox()
        for key in (config.FIT_COVER, config.FIT_CONTAIN, config.FIT_STRETCH):
            self.fit_combo.addItem(config.FIT_LABELS[key], key)
        right.addWidget(self.fit_combo)

        right.addWidget(QLabel("<b>4. Formato de salida</b>"))
        self.fmt_combo = QComboBox()
        self.fmt_combo.addItem("JPG (alta calidad)", config.FORMAT_JPG)
        self.fmt_combo.addItem("PNG (sin perdida)", config.FORMAT_PNG)
        right.addWidget(self.fmt_combo)

        right.addWidget(QLabel("<b>5. Carpeta de salida</b>"))
        out_row = QHBoxLayout()
        self.out_label = QLabel(self.out_dir)
        self.out_label.setWordWrap(True)
        out_btn = QPushButton("Cambiar...")
        out_btn.clicked.connect(self._pick_out_dir)
        out_row.addWidget(self.out_label, stretch=1)
        out_row.addWidget(out_btn)
        right.addLayout(out_row)

        right.addStretch(1)

        self.create_btn = QPushButton("CREAR")
        self.create_btn.setMinimumHeight(46)
        self.create_btn.setStyleSheet(
            "font-size:16px; font-weight:bold; background:#2d7d46; color:white;")
        self.create_btn.clicked.connect(self._start)
        right.addWidget(self.create_btn)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        right.addWidget(self.progress)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        right.addWidget(self.status)

        layout.addLayout(left, stretch=1)
        layout.addLayout(right)

    # ---------- acciones ----------
    def _pick_photos(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self, "Elegir fotos", "",
            "Imagenes (*.jpg *.jpeg *.png *.tif *.tiff *.bmp *.webp)")
        if files:
            self.photo_list.add_paths(files)

    def _remove_selected(self) -> None:
        for item in self.photo_list.selectedItems():
            self.photo_list.takeItem(self.photo_list.row(item))

    def _pick_frame(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Elegir marco PNG", "", "PNG (*.png);;Imagenes (*.png *.tif *.tiff)")
        if not path:
            return
        self.frame_path = path
        try:
            with Image.open(path) as im:
                im.thumbnail((220, 220))
                im = im.convert("RGBA")
                data = im.tobytes("raw", "RGBA")
                from PySide6.QtGui import QImage
                qimg = QImage(data, im.width, im.height, QImage.Format_RGBA8888)
                self.frame_preview.setPixmap(QPixmap.fromImage(qimg))
                self.frame_preview.setText("")
        except Exception as exc:  # noqa: BLE001
            self.frame_preview.setText("No se pudo previsualizar")
            self.status.setText(f"Aviso: {exc}")

    def _pick_out_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Carpeta de salida", self.out_dir)
        if path:
            self.out_dir = path
            self.out_label.setText(path)

    def _start(self) -> None:
        photos = self.photo_list.all_paths()
        if not self.frame_path:
            QMessageBox.warning(self, "Falta el marco", "Primero elegi un marco PNG.")
            return
        if not photos:
            QMessageBox.warning(self, "Faltan fotos", "Agrega al menos una foto.")
            return

        job = Job(
            frame_path=self.frame_path,
            size=self.size_combo.currentData(),
            fit=self.fit_combo.currentData(),
            out_format=self.fmt_combo.currentData(),
        )

        self.create_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setMaximum(len(photos))
        self.progress.setValue(0)
        self._errors: list[str] = []

        self.worker = Worker(photos, self.out_dir, job)
        self.worker.progress.connect(self._on_progress)
        self.worker.failed.connect(self._on_failed)
        self.worker.finished_all.connect(self._on_done)
        self.worker.start()

    def _on_progress(self, current: int, total: int, name: str) -> None:
        self.progress.setValue(current)
        self.status.setText(f"Procesando {current}/{total}: {name}")

    def _on_failed(self, path: str, error: str) -> None:
        self._errors.append(f"{os.path.basename(path)}: {error}")

    def _on_done(self, ok: int, total: int) -> None:
        self.create_btn.setEnabled(True)
        self.progress.setVisible(False)
        msg = f"Listo: {ok} de {total} fotos guardadas en\n{self.out_dir}"
        if self._errors:
            msg += "\n\nErrores:\n" + "\n".join(self._errors)
            QMessageBox.warning(self, "Terminado con errores", msg)
        else:
            QMessageBox.information(self, "Terminado", msg)
        self.status.setText(msg.split("\n")[0])


def run() -> None:
    app = QApplication.instance() or QApplication([])
    win = MainWindow()
    win.show()
    app.exec()
