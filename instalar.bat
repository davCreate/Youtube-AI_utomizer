@echo off
chcp 65001 >nul
title Instalar YouTube AI-utomizer
cd /d "%~dp0"

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY goto :nopython

if exist .venv\Scripts\python.exe goto :install
echo Preparando el entorno, solo la primera vez...
%PY% -m venv .venv
if errorlevel 1 goto :error

:install
echo Instalando dependencias...
.venv\Scripts\python.exe -m pip install --quiet --upgrade pip
.venv\Scripts\python.exe -m pip install --quiet -e .
if errorlevel 1 goto :error

.venv\Scripts\python.exe -m yt_automizer setup
pause
exit /b 0

:nopython
echo No tienes Python. Se abrira la pagina de descarga.
echo Instalalo y MARCA la casilla "Add python.exe to PATH". Luego abre otra vez este archivo.
start "" https://www.python.org/downloads/
pause
exit /b 1

:error
echo.
echo Algo ha fallado. Copia el mensaje de arriba y pegaselo a Claude.
pause
exit /b 1
