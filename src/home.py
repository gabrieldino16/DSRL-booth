"""Pantalla de inicio de DSRL Booth: selector de modo de trabajo.

Desde acá se elige entre:
  - Preparar tanda (lote): componer un lote de fotos ya sacadas + marco.  (gui.MainWindow)
  - Fotocabina en vivo:    capturar con la cámara, componer y mostrar.    (booth.BoothWindow)

Cada modo es una ventana propia; al cerrarla se vuelve a este inicio.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel, QMainWindow, QPushButton, QVBoxLayout, QWidget,
)


class HomeWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("DSRL Booth")
        self.resize(560, 460)
        self._child = None  # ventana del modo activo (mantiene la referencia viva)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        v = QVBoxLayout(root)
        v.setContentsMargins(40, 40, 40, 40)
        v.setSpacing(18)

        title = QLabel("📸 DSRL Booth")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size:30px; font-weight:bold;")
        v.addWidget(title)

        subtitle = QLabel("Elegí cómo querés trabajar")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("color:#888; font-size:14px;")
        v.addWidget(subtitle)

        v.addStretch(1)

        batch_btn = self._mode_button(
            "🖼  Preparar tanda (lote)",
            "Cargá fotos ya sacadas, elegí marco y tamaño, imprimí.",
            "#2d6cff")
        batch_btn.clicked.connect(self._open_batch)
        v.addWidget(batch_btn)

        booth_btn = self._mode_button(
            "🎥  Fotocabina en vivo",
            "Capturá con la cámara, componé con el marco y mostrá al instante.",
            "#2d7d46")
        booth_btn.clicked.connect(self._open_booth)
        v.addWidget(booth_btn)

        v.addStretch(2)

    def _mode_button(self, title: str, desc: str, color: str) -> QPushButton:
        btn = QPushButton(f"{title}\n{desc}")
        btn.setMinimumHeight(96)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(
            f"QPushButton {{ font-size:17px; font-weight:bold; text-align:left;"
            f" padding:14px 22px; border:none; border-radius:10px;"
            f" background:{color}; color:white; }}"
            f"QPushButton:hover {{ background:{color}; opacity:0.9; }}")
        return btn

    # ---------- apertura de modos ----------
    def _open_batch(self) -> None:
        from gui import MainWindow
        self._open(MainWindow())

    def _open_booth(self) -> None:
        from booth import BoothWindow
        self._open(BoothWindow())

    def _open(self, window) -> None:
        self._child = window
        window.closed.connect(self._on_child_closed)
        window.show()
        self.hide()

    def _on_child_closed(self) -> None:
        self._child = None
        self.show()


def run() -> None:
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    win = HomeWindow()
    win.show()
    app.exec()
