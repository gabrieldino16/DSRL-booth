# 🧩 Cómo conseguir e instalar el EDSDK de Canon (paso a paso)

Esta guía es para activar el **disparo directo con la Canon** (calidad full-res,
foto instantánea). Se hace **una sola vez**. Tus tres cámaras (T5, 80D,
6D Mark II) son compatibles con el EDSDK.

> El EDSDK de Canon **no se puede redistribuir**, por eso no viene con el
> proyecto: cada uno lo baja con su cuenta gratuita. Por eso la carpeta `edsdk/`
> está en `.gitignore`.

---

## Paso 0 — Confirmar que tu Python es de 64 bits

Desde la carpeta del proyecto, en PowerShell:

```powershell
.venv\Scripts\python.exe -c "import struct; print(struct.calcsize('P')*8)"
```

Tiene que decir **64**. (Si dijera 32, avisame.) Esto define qué DLL usar.

---

## Paso 1 — Registrarte en el programa de desarrolladores de Canon (gratis)

El EDSDK se descarga desde el portal de desarrolladores de Canon. Según tu región:

- **Canon Europa:** https://developers.canon-europe.com/ ← **usá esta desde Argentina**
- **Canon USA:** https://developer.usa.canon.com/ (alternativa si la de arriba falla)
- Si esos links cambian, buscá en Google: **"Canon EDSDK developer program"**.

> **Desde Argentina:** andá por **Canon Europa**. No exige ser empresa ni
> residente de la UE, y es la vía habitual para conseguir el EDSDK fuera de
> EE.UU. y Japón. El portal de Canon USA a veces limita el acceso a
> desarrolladores estadounidenses. No existe un portal de desarrolladores propio
> de Canon Latinoamérica. Si por Europa te rechazan, probá el de USA.

Pasos:
1. Creá una cuenta (gratis) y confirmá el email.
2. Entrá a la sección de **SDKs / Downloads** y buscá **EDSDK** (EOS Digital SDK).
3. Aceptá el acuerdo de licencia (uso del SDK).
4. Puede que la aprobación sea inmediata o tarde un poco (a veces revisan la
   solicitud). Cuando esté habilitada, vas a poder descargar.

---

## Paso 2 — Descargar el EDSDK para Windows

1. Descargá el **EDSDK para Windows** (el ZIP más reciente, ej.
   "EDSDK 13.x.x Windows").
2. Descomprimí el ZIP en cualquier lado (ej. el Escritorio).

---

## Paso 3 — Encontrar los DLL de 64 bits

Dentro de lo descomprimido vas a ver carpetas parecidas a estas (los nombres
cambian un poco según la versión):

```
EDSDK_Windows/
  EDSDK/         <- versión 32 bits
    Dll/
  EDSDK_64/      <- versión 64 bits  ← ESTA es la que necesitás
    Dll/
      EDSDK.dll
      EdsImage.dll
      ... (varios .dll más: Mc*.dll, etc.)
  Header/
  ...
```

Lo que te importa es la carpeta **`Dll` de la versión de 64 bits** (`EDSDK_64/Dll`
o similar). Ahí están `EDSDK.dll`, `EdsImage.dll` y varios DLL de apoyo.

> Si solo ves una carpeta `EDSDK/Dll` (sin la de 64), fijate si adentro hay una
> subcarpeta o si el ZIP traía ambas versiones. Tenés que usar los **64 bits**.

---

## Paso 4 — Copiar los DLL a la carpeta `edsdk/` del proyecto

1. Creá una carpeta llamada **`edsdk`** en la raíz del proyecto (al lado de `src`,
   `marcos`, etc.):
   ```
   DSRL-booth/
     edsdk/        <- crear esta
     src/
     marcos/
     ...
   ```
2. Copiá **TODOS** los archivos `.dll` de la carpeta `Dll` de 64 bits adentro de
   `edsdk/`. Debe quedar así:
   ```
   DSRL-booth/
     edsdk/
       EDSDK.dll
       EdsImage.dll
       ... (todos los demás .dll)
   ```
   > Copiá **todos** los DLL, no solo EDSDK.dll: EDSDK.dll necesita a los otros
   > para funcionar.

---

## Paso 5 — Verificar que la app los encuentra

Desde la carpeta del proyecto:

```powershell
.venv\Scripts\python.exe -c "import sys; sys.path.insert(0,'src'); import canon; print('EDSDK detectado:', canon.edsdk_available())"
```

- Si dice **`EDSDK detectado: True`** → ¡listo, los DLL están bien puestos!
- Si dice **False** → revisá que exista `edsdk/EDSDK.dll` exactamente con ese
  nombre en esa carpeta.

---

## Paso 6 — Probar con la cámara

1. Conectá la Canon por USB, **encendida**, en un modo de disparo (P/Av/Tv/M).
2. **Cerrá EOS Utility** y cualquier otro programa que use la cámara.
3. Abrí la app (`run.bat`) → **Fotocabina en vivo**.
4. En el selector de cámara, elegí **"Canon (disparo directo) — instantáneo"**.
5. Poné **Modo: "Foto asistida (fotógrafo)"**.
6. Dispará (con el obturador de la cámara o el botón "Disparar (PC)").
7. La foto debería aparecer en pantalla y guardarse en `salida/<evento>/`.

---

## Si algo falla

- **No aparece "Canon (disparo directo)" en el selector:** los DLL no están o no
  son de 64 bits. Repetí el Paso 5.
- **Aparece pero da un error `EDSDK error 0x........`:** copiá el número de error
  y el momento en que pasó (al abrir, al disparar, etc.) y pasámelo. Con eso lo
  ajusto — el backend está escrito pero no se pudo probar sin una Canon, así que
  este es el momento de afinarlo con datos reales.
- **La cámara se apaga sola / entra en reposo:** desactivá el "auto apagado" en
  el menú de la cámara para eventos largos.
- **Dice que la cámara está ocupada:** seguro quedó EOS Utility u otro programa
  abierto usándola. Cerralo.

---

## Nota

No hace falta el EDSDK para el modo **Carpeta observada (EOS Utility)** — ese ya
funciona sin SDK. El EDSDK es solo para el **disparo directo instantáneo** (y, a
futuro, boomerang/video). Ver también `docs/canon-setup.md`.
