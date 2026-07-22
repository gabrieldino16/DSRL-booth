@echo off
REM ============================================================
REM  DSRL Booth - arranque
REM  La primera vez crea el entorno e instala dependencias.
REM  Las siguientes veces abre la app directamente.
REM ============================================================
setlocal
cd /d "%~dp0"

REM --- ubicar Python ---
set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not defined PY (
    echo No se encontro Python. Instalalo desde https://www.python.org/downloads/
    pause
    exit /b 1
)

REM --- crear entorno virtual la primera vez ---
if not exist ".venv\Scripts\python.exe" (
    echo Creando entorno virtual e instalando dependencias, esto tarda un momento...
    "%PY%" -m venv .venv
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)

REM --- abrir la app ---
".venv\Scripts\python.exe" src\main.py
if errorlevel 1 pause
endlocal
