"""Puentes entre PIL y Qt: conversion de imagenes e impresion.

La impresion usa QtPrintSupport (incluido en PySide6), asi el usuario elige la
impresora (ej. la K60) y el tamano de papel desde el dialogo estandar de Windows.
"""
from __future__ import annotations

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter, QPixmap
from PySide6.QtPrintSupport import QPrinter, QPrintDialog
from PySide6.QtWidgets import QDialog, QWidget


def pil_to_qimage(img: Image.Image) -> QImage:
    """Convierte una imagen PIL (RGB/RGBA) en QImage sin depender de archivos."""
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    if img.mode == "RGB":
        data = img.tobytes("raw", "RGB")
        qimg = QImage(data, img.width, img.height, img.width * 3,
                      QImage.Format_RGB888)
    else:
        data = img.tobytes("raw", "RGBA")
        qimg = QImage(data, img.width, img.height, img.width * 4,
                      QImage.Format_RGBA8888)
    # copy() para que el QImage sea dueno de su buffer (no del de PIL).
    return qimg.copy()


def pil_to_qpixmap(img: Image.Image) -> QPixmap:
    return QPixmap.fromImage(pil_to_qimage(img))


def print_image(img: Image.Image, parent: QWidget | None = None,
                show_dialog: bool = True) -> bool:
    """Envia una imagen PIL a la impresora. Devuelve True si se imprimio.

    show_dialog=True muestra el dialogo para elegir impresora/tamano.
    """
    qimg = pil_to_qimage(img)

    printer = QPrinter(QPrinter.HighResolution)
    printer.setFullPage(True)

    if show_dialog:
        dlg = QPrintDialog(printer, parent)
        dlg.setWindowTitle("Imprimir foto")
        if dlg.exec() != QDialog.Accepted:
            return False

    painter = QPainter()
    if not painter.begin(printer):
        return False
    try:
        page = painter.viewport()
        scaled = qimg.size().scaled(page.size(), Qt.KeepAspectRatio)
        # Centra la imagen en la pagina.
        x = page.x() + (page.width() - scaled.width()) // 2
        y = page.y() + (page.height() - scaled.height()) // 2
        painter.setViewport(x, y, scaled.width(), scaled.height())
        painter.setWindow(qimg.rect())
        painter.drawImage(0, 0, qimg)
    finally:
        painter.end()
    return True
