"""Capa de entrega: subir la foto, generar el QR y enviar por email.

Interfaz enchufable (como las cámaras): cada forma de publicar la foto implementa
`Uploader`. Hoy hay dos:

  - LocalUploader:  sirve la foto desde la PC por HTTP en la red local. Sirve para
    probar el flujo sin ninguna cuenta, y para eventos SIN internet (la PC arma su
    propia red/hotspot y el cliente descarga de una IP local).
  - SmugMugUploader: sube a un álbum de SmugMug (OAuth 1.0a) y devuelve la URL
    pública de la foto. Para eventos CON internet: el QR funciona con los datos
    del celular en cualquier lado.

Las credenciales se leen de `secrets.json` en la raíz del proyecto (ver
`secrets.example.json`). Ese archivo está en .gitignore y no se sube al repo.
"""
from __future__ import annotations

import functools
import json
import os
import socket
import threading
from abc import ABC, abstractmethod

from PIL import Image


class DeliveryError(Exception):
    pass


# ---------------------------------------------------------------- credenciales
def _secrets_path() -> str:
    return os.path.join(os.getcwd(), "secrets.json")


def load_secrets() -> dict:
    """Lee secrets.json si existe; si no, devuelve {} (modo local por defecto)."""
    path = _secrets_path()
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:  # noqa: BLE001
            pass
    return {}


# ------------------------------------------------------------------------- QR
def make_qr(url: str, box_size: int = 10, border: int = 2) -> Image.Image:
    """Genera un código QR (imagen PIL RGB) que apunta a `url`."""
    import qrcode

    qr = qrcode.QRCode(box_size=box_size, border=border,
                       error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(url)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white").convert("RGB")


# ------------------------------------------------------------------- uploaders
class Uploader(ABC):
    name: str = "entrega"

    @abstractmethod
    def upload(self, path: str) -> str:
        """Sube el archivo y devuelve una URL para el QR. Lanza DeliveryError."""

    def stop(self) -> None:
        """Libera recursos (servidores, etc.). Opcional."""


def _lan_ip() -> str:
    """IP de esta PC en la red local (para armar la URL del QR)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:  # noqa: BLE001
        return "127.0.0.1"
    finally:
        s.close()


class LocalUploader(Uploader):
    """Sirve la carpeta de salida por HTTP en la LAN. Sin cuentas ni internet."""

    name = "Local (red)"

    def __init__(self, serve_dir: str, port: int = 8000) -> None:
        self.serve_dir = os.path.abspath(serve_dir)
        self.port = port
        self._httpd = None

    def _ensure_server(self) -> None:
        if self._httpd is not None:
            return
        from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

        os.makedirs(self.serve_dir, exist_ok=True)
        handler = functools.partial(SimpleHTTPRequestHandler, directory=self.serve_dir)
        self._httpd = ThreadingHTTPServer(("0.0.0.0", self.port), handler)
        threading.Thread(target=self._httpd.serve_forever, daemon=True).start()

    def upload(self, path: str) -> str:
        self._ensure_server()
        from urllib.parse import quote

        rel = os.path.relpath(os.path.abspath(path), self.serve_dir)
        rel = quote(rel.replace(os.sep, "/"))
        return f"http://{_lan_ip()}:{self.port}/{rel}"

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd = None


class SmugMugUploader(Uploader):
    """Sube a un álbum de SmugMug y devuelve la URL pública de la foto."""

    name = "SmugMug"
    UPLOAD_URL = "https://upload.smugmug.com/"

    def __init__(self, api_key: str, api_secret: str,
                 access_token: str, access_secret: str, album_uri: str) -> None:
        from requests_oauthlib import OAuth1

        if not album_uri:
            raise DeliveryError("Falta 'album_uri' de SmugMug en secrets.json")
        self._auth = OAuth1(api_key, api_secret, access_token, access_secret)
        self.album_uri = album_uri  # p.ej. "/api/v2/album/ABC123"

    def upload(self, path: str) -> str:
        import requests

        with open(path, "rb") as fh:
            data = fh.read()
        headers = {
            "X-Smug-AlbumUri": self.album_uri,
            "X-Smug-ResponseType": "JSON",
            "X-Smug-Version": "v2",
            "X-Smug-FileName": os.path.basename(path),
            "Content-Type": "image/jpeg",
        }
        try:
            r = requests.post(self.UPLOAD_URL, data=data, headers=headers,
                              auth=self._auth, timeout=90)
        except requests.RequestException as exc:
            raise DeliveryError(f"No se pudo conectar a SmugMug: {exc}") from exc
        if r.status_code != 200:
            raise DeliveryError(f"SmugMug respondió {r.status_code}: {r.text[:200]}")
        j = r.json()
        if j.get("stat") != "ok":
            raise DeliveryError(f"SmugMug rechazó la subida: {j}")
        image = j.get("Image", {})
        url = image.get("URL") or image.get("WebUri")
        if not url:
            raise DeliveryError(f"SmugMug no devolvió URL: {j}")
        return url


def load_uploader(serve_dir: str) -> Uploader:
    """Elige el uploader según secrets.json. Si no hay SmugMug, usa el local."""
    sec = load_secrets()
    sm = sec.get("smugmug") or {}
    if sm.get("api_key") and sm.get("access_token") and sm.get("album_uri"):
        return SmugMugUploader(
            sm["api_key"], sm["api_secret"],
            sm["access_token"], sm["access_secret"], sm["album_uri"])
    return LocalUploader(serve_dir)


# ----------------------------------------------------------------------- email
def send_email(to_addr: str, image_path: str,
               subject: str = "Tu foto 📸",
               body: str = "¡Gracias por pasar! Acá va tu foto.",
               link: str | None = None) -> None:
    """Envía la foto por email como adjunto usando SMTP (config en secrets.json)."""
    import smtplib
    from email.message import EmailMessage

    cfg = load_secrets().get("email") or {}
    host = cfg.get("smtp_host")
    user = cfg.get("user")
    password = cfg.get("password")
    if not (host and user and password):
        raise DeliveryError("Falta la config de email en secrets.json")

    msg = EmailMessage()
    from_name = cfg.get("from_name", "Fotocabina")
    msg["From"] = f"{from_name} <{user}>"
    msg["To"] = to_addr
    msg["Subject"] = subject
    text = body + (f"\n\nTambién podés descargarla acá: {link}" if link else "")
    msg.set_content(text)

    with open(image_path, "rb") as fh:
        msg.add_attachment(fh.read(), maintype="image", subtype="jpeg",
                           filename=os.path.basename(image_path))

    port = int(cfg.get("smtp_port", 587))
    try:
        with smtplib.SMTP(host, port, timeout=30) as smtp:
            smtp.starttls()
            smtp.login(user, password)
            smtp.send_message(msg)
    except Exception as exc:  # noqa: BLE001
        raise DeliveryError(f"No se pudo enviar el email: {exc}") from exc
