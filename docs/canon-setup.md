# 🎥 Conectar la cámara Canon

Hay dos formas de usar tu Canon en la fotocabina. Podés usar las dos: la primera
para arrancar ya, la segunda para calidad de impresión.

En el modo **Fotocabina en vivo** hay un **selector de modo** y uno de **cámara**
arriba. Elegí según cómo trabajes.

---

## ⭐ Opción recomendada para foto asistida — EOS Utility + carpeta observada

Es el flujo del negocio con fotógrafo (foto con Papá Noel, fondo temático, etc.):
el fotógrafo dispara, y en la PC la foto aparece sola para imprimir / email / QR.
**No mantiene la cámara "abierta" como webcam todo el día** — la cámara solo
trabaja cuando el fotógrafo aprieta el obturador. Funciona con **todas** tus
Canon (T5, 80D, 6D Mark II).

1. Instalá **EOS Utility** (viene con la cámara o se baja del sitio de Canon).
2. Conectá la Canon por USB y abrí EOS Utility.
3. En EOS Utility activá la **descarga automática** a una carpeta (en
   "Preferencias → Carpeta de destino" / "Descargar imágenes automáticamente").
4. En la app: Fotocabina en vivo → **Modo: "Foto asistida (fotógrafo)"** →
   botón **"📁 Carpeta EOS Utility..."** y elegí **esa misma carpeta**.
5. Listo: cada vez que el fotógrafo dispara, EOS Utility baja la foto a la
   carpeta y la app la toma, la compone con la plantilla y la muestra para
   Imprimir / Email / QR. Con "Nueva sesión" queda esperando la siguiente.

> En modo asistido también podés disparar desde la PC (botón "Disparar (PC)") si
> usás la cámara directa en vez de la carpeta. Y si la plantilla tiene varios
> huecos, se van llenando con cada disparo.

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
4. Abrí la app → Fotocabina en vivo → en el selector de cámara vas a ver **dos**
   opciones Canon:
   - **"Canon (disparo directo) — instantáneo"** ⭐: la sesión queda abierta y la
     foto llega **al instante** cuando disparás (obturador físico o botón
     "Disparar (PC)"), pero la cámara **no transmite video** — no queda "abierta"
     como webcam ni gasta batería de más. Es como trabaja dslrBooth. Ideal para
     el flujo asistido con fotógrafo, y sin depender de EOS Utility.
   - **"Canon (con Live View / preview)"**: además muestra la vista en vivo en
     pantalla (para la fotocabina desatendida con cuenta regresiva). Mantiene el
     Live View encendido mientras esté activa.

> El Live View (video continuo) es lo que "abre" la cámara; el disparo directo
> NO lo usa. Por eso podés tener transferencia instantánea sin tener la cámara
> streameando todo el día.

El EDSDK de Canon **no se puede redistribuir**, por eso `edsdk/` está en
`.gitignore` y no se sube al repositorio: cada quien baja el SDK por su cuenta.

### Si no aparece "Canon (EDSDK)" en el selector
- Verificá que exista `edsdk/EDSDK.dll` en la raíz del proyecto.
- Verificá que sean los DLL de **64 bits**.

### Si aparece pero da error al seleccionarla
- Que la cámara esté encendida y no la esté usando otro programa.
- Probá otro cable/puerto USB.
- Pasame el mensaje de error exacto (dice `EDSDK error 0x...`) para ajustarlo.
