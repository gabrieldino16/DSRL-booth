# 📸 DSRL Booth — Plan de la fotocabina

> Documento de visión y hoja de ruta. Nace de reemplazar **dslrBooth**
> (https://dslrbooth.com/es, cuesta ~50 USD/mes) por una herramienta propia.
> Guardado para no perder el contexto entre sesiones.

## 🎯 Unidad de negocio

Saco fotos en eventos y las **imprimo al instante**. La gente después puede
**escanear un QR** para descargar la foto o **recibirla por email**.

Hoy uso **dslrBooth**. Quiero mi propio programa que cubra dos flujos de trabajo:

### Flujo A — Lote / manual (YA RESUELTO ✅)
Saco fotos con la cámara, voy a la PC, cargo la tanda, elijo un marco PNG y el
tamaño, y salen todas compuestas listas para imprimir. Esto ya funciona (ver
`src/gui.py`, modo lote).

### Flujo B — Fotocabina en vivo (A CONSTRUIR 🚧)
Conecto la cámara **Canon vía USB** y voy sacando fotos en vivo. El programa:
1. Muestra **vista en vivo** (preview) de la cámara.
2. Dispara la captura (puede ser **una o varias** capturas por sesión).
3. Compone la **foto de salida**: mete las capturas en sus lugares dentro de una
   plantilla + marco PNG (como una tira de fotocabina tradicional: p. ej. 3
   capturas de la cámara dentro de una foto de salida).
4. Muestra el resultado.
5. Ofrece: **Imprimir**, **Email**, **QR para descargar**.

## 🧩 Editor de plantillas (como el "Screen/Print Editor" de dslrBooth)

La foto de salida se arma con una **plantilla** que define:
- Tamaño de papel (4x6 / 10x15, etc.) y resolución (300 dpi).
- Uno o más **huecos de foto** ("Photo From Booth") con posición (X, Y), tamaño
  (W, H) y rotación — ahí van las capturas de la cámara.
- Imágenes/marcos PNG por encima, textos, formas, código QR, color de fondo.
- Capas (layers) con orden (traer al frente / enviar atrás).

Referencia visual (capturas de dslrBooth que pasó el usuario):
- **Pantalla de eventos guardados**: grilla de eventos, botones Crear/Duplicar/
  Renombrar/Eliminar/Lanzar evento.
- **Menú de inicio del evento**: Editor de pantallas, Diseño de impresión,
  Efectos y pegatinas, Eliminación de fondo, Configuración de captura/cámara/
  impresión, Compartir (email/SMS/QR), Diapositivas, etc.
- **Pantalla final**: la foto compuesta + íconos de Email / SMS / Escanear QR /
  Impresión al costado; tiempo de espera configurable antes de volver al inicio.
- **Editor de plantilla de impresión**: lienzo con huecos de foto, panel ADD
  (Image, Photo From Booth, Text, Session Data, Shape, QR Code, Background
  Color), panel de posición/tamaño/rotación, alineación y capas.

## ☁️ Entrega (QR / email / descarga)

El usuario tiene suscripción a **SmugMug** — posible backend para subir las fotos
y generar el enlace/QR de descarga. Alternativas a evaluar:
- **SmugMug API**: subir foto → obtener URL → generar QR que apunta a esa URL.
- Auto-hospedado (servidor propio / carpeta compartida) si se quiere sin costo.
- Email vía SMTP (Gmail u otro) para el envío directo.

## 🏗️ Arquitectura actual del código

| Archivo | Rol | Estado |
|---|---|---|
| `src/config.py` | Tamaños de impresión, DPI, modos de ajuste, formatos | ✅ |
| `src/processor.py` | Motor de composición foto+marco. `compose_image()` ya trabaja en memoria (sirve para captura en vivo) | ✅ |
| `src/imaging_qt.py` | Puentes PIL↔Qt + impresión con QtPrintSupport | ✅ base |
| `src/camera.py` | Abstracción `CameraBackend` (Webcam/OpenCV + Dummy). Canon EDSDK pendiente | 🚧 base |
| `src/gui.py` | UI del **modo lote** (Flujo A) | ✅ |
| `src/main.py` | Punto de entrada | ✅ |

## 🌿 Ramas de trabajo

- `main` — app original (solo lote).
- `fotocabina` — checkpoint con la base de cámara/impresión (commit e236d5f).
- `fotocabina-vivo` — **rama activa** para construir la fotocabina en vivo.

## 🗺️ Hoja de ruta propuesta (de a poco)

> El modo lote actual queda como **una de las opciones** (pantalla de inicio con
> selector de modo).

1. **Pantalla de inicio / selector de modo**: "Preparar tanda (lote)" vs
   "Fotocabina en vivo". El lote actual pasa a ser una opción.
2. **Modo fotocabina — mínimo viable**: preview de webcam, botón de disparo,
   componer con marco existente, mostrar resultado, botón Imprimir. (Reusa
   `camera.py`, `processor.compose_image`, `imaging_qt.print_image`.)
3. **Sesión multi-captura**: cuenta regresiva, N capturas seguidas, y armado de
   la foto de salida con N huecos (tira de fotocabina).
4. **Plantillas**: formato de plantilla (JSON) con huecos de foto + capas +
   marco. Al principio plantillas prearmadas; después el editor visual.
5. **Cámara Canon (EDSDK)**: `CanonBackend` que implemente `CameraBackend`.
6. **Entrega**: Imprimir (hecho), luego Email (SMTP) y QR (SmugMug u otro).
7. **Editor visual de plantillas**: arrastrar huecos/imágenes/textos, capas,
   guardar/cargar. (Lo más grande; va al final.)

## ❓ Decisiones pendientes
- Backend de QR/descarga: SmugMug API vs auto-hospedado.
- Modelo(s) de cámara Canon y si el EDSDK está disponible.
