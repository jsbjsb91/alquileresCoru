@echo off
title Alquileres Coruna - Inteligencia Inmobiliaria
cd /d "%~dp0"

echo =======================================================
echo   🏠 ALQUILERES A CORUÑA — INTELIGENCIA INMOBILIARIA
echo =======================================================
echo.
echo [1/2] Abriendo navegador en http://127.0.0.1:8000 ...
start http://127.0.0.1:8000

echo [2/2] Iniciando servidor FastAPI + Machine Learning...
echo.
py -m uvicorn backend.main:app --host 127.0.0.1 --port 8000

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Intentando con ruta absoluta de Python...
    "C:\Users\seijo\AppData\Local\Programs\Python\Python314\python.exe" -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
)

pause
