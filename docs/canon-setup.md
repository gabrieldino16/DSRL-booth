# 🎥 Conectar la cámara Canon

Hay dos formas de usar tu Canon en la fotocabina. Podés usar las dos: la primera
para arrancar ya, la segunda para calidad de impresión.

En el modo **Fotocabina en vivo** hay un **selector de cámara** arriba a la
derecha. Las cámaras que detecte aparecen ahí; elegís la que quieras.

---

## Opción 1 — EOS Webcam Utility (rápido, funciona ya)

Tu Canon aparece como una webcam común. Calidad ~1080p (no full-res del sensor),
pero sin instalar ningún SDK.

1. Descargá **EOS Webcam Utility** (gratis) desde el sitio de Canon e instalalo.
2. Conectá la Canon por USB y encendela.
3. (Solo la primera vez) instalá OpenCV para que la app lea webcams:
   ```
   .venv\Scripts\python.exe -m pip install opencv-python
   ```
4. Abrí la app → Fotocabina en vivo → en el selector de cámara elegí
   **"Cámara USB #N (webcam / EOS Webcam Utility)"**. Si tenés webcam integrada,
   la Canon suele ser el índice más alto (#1 en vez de #0); probá cuál es.

---

## Opción 2 — EDSDK (calidad de impresión, tethering real)

Preview en vivo + captura a **máxima resolución** del sensor. Requiere el SDK
oficial de Canon (gratis, pero hay que registrarse).

> ⚠️ Este backend se escribió siguiendo la API estándar del EDSDK pero **no se
> pudo probar sin una Canon**. Puede necesitar ajustes al usarlo con tu cámara;
> si algo falla, avisá con el error que aparezca y lo corregimos.

1. Registrate (gratis) en el **Canon Developers Program** y descargá el **EDSDK**
   para Windows: https://developers.canon-europe.com/ (o el portal de tu región).
2. Del ZIP, copiá **todos los DLL de 64 bits** (EDSDK.dll, EdsImage.dll, etc.,
   carpeta `Dll`) a una carpeta **`edsdk/`** en la raíz del proyecto:
   ```
   DSRL-booth/
     edsdk/
       EDSDK.dll
       EdsImage.dll
       ... (los demás DLL)
   ```
   (Alternativa: poné los DLL donde quieras y seteá la variable de entorno
   `EDSDK_DIR` con esa ruta.)
3. Conectá la Canon por USB, encendida, en modo de disparo (P/Av/Tv/M), y **cerrá
   EOS Utility** u otros programas que la usen.
4. Abrí la app → Fotocabina en vivo → en el selector elegí
   **"Canon (EDSDK) — máxima calidad"**.

El EDSDK de Canon **no se puede redistribuir**, por eso `edsdk/` está en
`.gitignore` y no se sube al repositorio: cada quien baja el SDK por su cuenta.

### Si no aparece "Canon (EDSDK)" en el selector
- Verificá que exista `edsdk/EDSDK.dll` en la raíz del proyecto.
- Verificá que sean los DLL de **64 bits**.

### Si aparece pero da error al seleccionarla
- Que la cámara esté encendida y no la esté usando otro programa.
- Probá otro cable/puerto USB.
- Pasame el mensaje de error exacto (dice `EDSDK error 0x...`) para ajustarlo.
