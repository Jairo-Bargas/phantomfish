@echo off
title Phantom Fish - Gestion
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Instalando por primera vez, esto puede tardar un par de minutos...
    py -m venv .venv
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)

if not exist ".env" copy ".env.example" ".env" >nul

echo.
echo ===============================================================
echo   Phantom Fish esta corriendo.
echo.
echo   En esta PC:              http://localhost:8000
setlocal enabledelayedexpansion
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do (
    set "ip=%%a"
    set "ip=!ip: =!"
    echo   Desde el celular ^(wifi^): http://!ip!:8000
)
endlocal
echo.
echo   Dejala esta ventana abierta mientras uses la app.
echo   Para cerrar la app: cerra esta ventana.
echo ===============================================================
echo.

".venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8000
pause
