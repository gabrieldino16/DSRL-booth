"""Backend de cámara Canon vía EDSDK (tethering: preview + captura full-res).

⚠️  IMPORTANTE — este módulo NO se pudo probar sin una Canon conectada. Está
escrito siguiendo la API estándar del EDSDK de Canon y el patrón habitual de los
wrappers en Python (ctypes). Puede necesitar ajustes al probarlo con tu cámara.
Cualquier fallo se convierte en CameraError, así la app cae en otra cámara sin
romperse.

--- Requisitos para usarlo ---
1. Registrate (gratis) en el Canon Developers Program y descargá el "EDSDK"
   para Windows: https://developers.canon-europe.com/  (o el portal de tu región).
2. Del ZIP del SDK, copiá los DLL (EDSDK.dll, EdsImage.dll y demás) de la
   carpeta "Dll" a UNA de estas ubicaciones:
     - una carpeta `edsdk/` en la raíz del proyecto (recomendado), o
     - la ruta que indiques en la variable de entorno EDSDK_DIR.
   Usá los DLL de 64 bits (el Python del proyecto es de 64 bits).
3. Conectá la Canon por USB, encendida y en un modo de disparo (P/Av/Tv/M).
   Cerrá cualquier otro programa que la esté usando (EOS Utility, etc.).

El EDSDK de Canon no se puede redistribuir, por eso `edsdk/` está en .gitignore
y cada uno baja el SDK por su cuenta.
"""
from __future__ import annotations

import ctypes
import io
import os
import time

from PIL import Image

from camera import CameraBackend, CameraError

# ------------------------------------------------------------- constantes EDSDK
EDS_ERR_OK = 0
EDS_MAX_NAME = 256

kEdsCameraCommand_TakePicture = 0x00000000
kEdsCameraCommand_PressShutterButton = 0x00000004
kEdsCameraCommand_ShutterButton_OFF = 0x00000000
kEdsCameraCommand_ShutterButton_Completely = 0x00000003

kEdsPropID_SaveTo = 0x0000000B
kEdsSaveTo_Host = 2

kEdsPropID_Evf_Mode = 0x00000501
kEdsPropID_Evf_OutputDevice = 0x00000500
kEdsEvfOutputDevice_PC = 0x00000002

kEdsObjectEvent_DirItemRequestTransfer = 0x00000208


# --------------------------------------------------------------------- structs
class EdsCapacity(ctypes.Structure):
    _fields_ = [("NumberOfFreeClusters", ctypes.c_int),
                ("BytesPerSector", ctypes.c_int),
                ("Reset", ctypes.c_int)]


class EdsDirectoryItemInfo(ctypes.Structure):
    _fields_ = [("size", ctypes.c_uint64),
                ("isFolder", ctypes.c_int),
                ("groupID", ctypes.c_uint),
                ("option", ctypes.c_uint),
                ("szFileName", ctypes.c_char * EDS_MAX_NAME),
                ("format", ctypes.c_uint),
                ("dateTime", ctypes.c_uint)]


# Firma del callback de eventos de objeto (stdcall en Windows).
_OBJECT_HANDLER = ctypes.WINFUNCTYPE(
    ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p)


# ------------------------------------------------------------- ubicación de DLL
def _sdk_dir() -> str | None:
    """Carpeta con los DLL del EDSDK, según env o carpeta del proyecto."""
    env = os.environ.get("EDSDK_DIR")
    candidates = [env] if env else []
    candidates.append(os.path.join(os.getcwd(), "edsdk"))
    for c in candidates:
        if c and os.path.isfile(os.path.join(c, "EDSDK.dll")):
            return c
    return None


def _load_dll() -> ctypes.WinDLL:
    sdk = _sdk_dir()
    if not sdk:
        raise CameraError(
            "No encontré EDSDK.dll. Poné los DLL del EDSDK de Canon en la "
            "carpeta 'edsdk/' del proyecto (ver canon.py).")
    # Permite que EDSDK.dll encuentre sus DLL vecinos (EdsImage.dll, etc.).
    try:
        os.add_dll_directory(sdk)
    except (AttributeError, OSError):
        pass
    return ctypes.WinDLL(os.path.join(sdk, "EDSDK.dll"))


def edsdk_available() -> bool:
    """True si están los DLL del EDSDK (no abre la cámara)."""
    return _sdk_dir() is not None


def _check(err: int, where: str) -> None:
    if err != EDS_ERR_OK:
        raise CameraError(f"EDSDK error 0x{err:08X} en {where}")


class CanonBackend(CameraBackend):
    """Canon por USB usando EDSDK: live view + captura a máxima resolución."""

    name = "Canon (EDSDK)"
    supports_physical_trigger = True  # el fotógrafo puede disparar en la cámara

    def __init__(self) -> None:
        self._dll: ctypes.WinDLL | None = None
        self._camera = ctypes.c_void_p()
        self._session = False
        self._sdk_init = False
        self._evf_on = False
        self._handler_ref = None      # mantiene vivo el callback
        self._incoming: list[Image.Image] = []  # fotos descargadas por procesar

    # ---------- ciclo de vida ----------
    def start(self) -> None:
        self._dll = _load_dll()
        _check(self._dll.EdsInitializeSDK(), "InitializeSDK")
        self._sdk_init = True

        cam_list = ctypes.c_void_p()
        _check(self._dll.EdsGetCameraList(ctypes.byref(cam_list)), "GetCameraList")
        count = ctypes.c_uint(0)
        _check(self._dll.EdsGetChildCount(cam_list, ctypes.byref(count)),
               "GetChildCount")
        if count.value == 0:
            self._dll.EdsRelease(cam_list)
            raise CameraError("No se detectó ninguna Canon conectada por USB.")

        _check(self._dll.EdsGetChildAtIndex(cam_list, 0,
               ctypes.byref(self._camera)), "GetChildAtIndex")
        self._dll.EdsRelease(cam_list)

        _check(self._dll.EdsOpenSession(self._camera), "OpenSession")
        self._session = True

        # Guardar en la PC (no en la tarjeta).
        save_to = ctypes.c_uint(kEdsSaveTo_Host)
        _check(self._dll.EdsSetPropertyData(self._camera, kEdsPropID_SaveTo, 0,
               ctypes.sizeof(save_to), ctypes.byref(save_to)), "SetPropertyData(SaveTo)")
        # Decirle a la cámara que hay espacio de sobra en el host.
        cap = EdsCapacity(0x7FFFFFFF, 512, 1)
        _check(self._dll.EdsSetCapacity(self._camera, cap), "SetCapacity")

        # Registrar el handler que recibe la foto cuando se dispara.
        self._handler_ref = _OBJECT_HANDLER(self._on_object_event)
        _check(self._dll.EdsSetObjectEventHandler(
            self._camera, ctypes.c_uint(0x00000200), self._handler_ref, None),
            "SetObjectEventHandler")

        self._start_live_view()

    def _start_live_view(self) -> None:
        mode = ctypes.c_uint(1)
        _check(self._dll.EdsSetPropertyData(self._camera, kEdsPropID_Evf_Mode, 0,
               ctypes.sizeof(mode), ctypes.byref(mode)), "SetPropertyData(Evf_Mode)")
        device = ctypes.c_uint(kEdsEvfOutputDevice_PC)
        _check(self._dll.EdsSetPropertyData(
            self._camera, kEdsPropID_Evf_OutputDevice, 0,
            ctypes.sizeof(device), ctypes.byref(device)),
            "SetPropertyData(Evf_OutputDevice)")
        self._evf_on = True

    def _stop_live_view(self) -> None:
        if not (self._evf_on and self._dll and self._camera):
            return
        device = ctypes.c_uint(0)
        try:
            self._dll.EdsSetPropertyData(
                self._camera, kEdsPropID_Evf_OutputDevice, 0,
                ctypes.sizeof(device), ctypes.byref(device))
        except Exception:  # noqa: BLE001
            pass
        self._evf_on = False

    # ---------- preview ----------
    def read_preview(self) -> Image.Image | None:
        if not (self._dll and self._evf_on):
            return None
        try:
            stream = ctypes.c_void_p()
            if self._dll.EdsCreateMemoryStream(0, ctypes.byref(stream)) != EDS_ERR_OK:
                return None
            evf = ctypes.c_void_p()
            if self._dll.EdsCreateEvfImageRef(stream, ctypes.byref(evf)) != EDS_ERR_OK:
                self._dll.EdsRelease(stream)
                return None
            # Puede fallar momentáneamente (DEVICE_BUSY) entre cuadros: no es fatal.
            err = self._dll.EdsDownloadEvfImage(self._camera, evf)
            img = None
            if err == EDS_ERR_OK:
                img = self._stream_to_image(stream)
            self._dll.EdsRelease(evf)
            self._dll.EdsRelease(stream)
            return img
        except Exception:  # noqa: BLE001
            return None

    # ---------- captura ----------
    def capture(self) -> Image.Image:
        """Captura sincrónica (la usa el modo cuenta regresiva)."""
        self.trigger()
        deadline = time.time() + 15.0
        while not self._incoming and time.time() < deadline:
            self._pump()
            time.sleep(0.02)
        if not self._incoming:
            raise CameraError("La Canon no devolvió la foto (timeout).")
        return self._incoming.pop(0)

    def trigger(self) -> None:
        """Dispara desde la PC (no espera: la foto llega por poll())."""
        if not self._dll:
            raise CameraError("La Canon no está iniciada.")
        _check(self._dll.EdsSendCommand(
            self._camera, kEdsCameraCommand_TakePicture, 0), "TakePicture")

    def poll(self) -> None:
        """Procesa eventos y entrega por on_photo las fotos que hayan llegado.

        Sirve tanto para el disparo desde la PC como para el obturador físico
        del fotógrafo: ambos generan el mismo evento de transferencia.
        """
        if not self._dll:
            return
        self._pump()
        while self._incoming:
            img = self._incoming.pop(0)
            if self.on_photo is not None:
                self.on_photo(img, None)

    def _pump(self) -> None:
        try:
            self._dll.EdsGetEvent()
        except Exception:  # noqa: BLE001
            pass

    def _on_object_event(self, event, obj_ref, context):
        if event == kEdsObjectEvent_DirItemRequestTransfer:
            try:
                self._download_item(obj_ref)
            except Exception:  # noqa: BLE001
                pass
        else:
            # Otros objetos que no vamos a usar: liberar para no perder memoria.
            if obj_ref:
                self._dll.EdsRelease(obj_ref)
        return EDS_ERR_OK

    def _download_item(self, dir_item) -> None:
        info = EdsDirectoryItemInfo()
        _check(self._dll.EdsGetDirectoryItemInfo(dir_item, ctypes.byref(info)),
               "GetDirectoryItemInfo")
        stream = ctypes.c_void_p()
        _check(self._dll.EdsCreateMemoryStream(info.size, ctypes.byref(stream)),
               "CreateMemoryStream")
        _check(self._dll.EdsDownload(dir_item, info.size, stream), "Download")
        _check(self._dll.EdsDownloadComplete(dir_item), "DownloadComplete")
        img = self._stream_to_image(stream)
        if img is not None:
            self._incoming.append(img)
        self._dll.EdsRelease(stream)
        self._dll.EdsRelease(dir_item)

    def _stream_to_image(self, stream) -> Image.Image | None:
        ptr = ctypes.c_void_p()
        length = ctypes.c_uint64(0)
        if self._dll.EdsGetPointer(stream, ctypes.byref(ptr)) != EDS_ERR_OK:
            return None
        if self._dll.EdsGetLength(stream, ctypes.byref(length)) != EDS_ERR_OK:
            return None
        if not ptr.value or length.value == 0:
            return None
        raw = ctypes.string_at(ptr.value, length.value)
        return Image.open(io.BytesIO(raw)).convert("RGB")

    # ---------- cierre ----------
    def stop(self) -> None:
        if self._dll is None:
            return
        self._stop_live_view()
        try:
            if self._session:
                self._dll.EdsCloseSession(self._camera)
            if self._camera:
                self._dll.EdsRelease(self._camera)
        except Exception:  # noqa: BLE001
            pass
        try:
            if self._sdk_init:
                self._dll.EdsTerminateSDK()
        except Exception:  # noqa: BLE001
            pass
        self._session = False
        self._sdk_init = False
        self._camera = ctypes.c_void_p()
