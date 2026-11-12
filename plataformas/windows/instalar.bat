@echo off
chcp 65001 >nul
title Sussurro - Instalador (Windows)
cd /d "%~dp0\..\.."

where py >nul 2>&1
if errorlevel 1 (
  echo Instalando Python 3.12 pelo winget...
  winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
)
where ffmpeg >nul 2>&1
if errorlevel 1 (
  echo Instalando ffmpeg pelo winget...
  winget install -e --id Gyan.FFmpeg --accept-source-agreements --accept-package-agreements
)

echo Criando ambiente Python em .venv ...
py -3.12 -m venv .venv || py -3 -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\pip install -r requirements.txt google-generativeai

if not exist config.json copy config.example.json config.json >nul

echo Criando atalho na Area de Trabalho...
powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\Sussurro.lnk'); $s.TargetPath='%CD%\plataformas\windows\iniciar.bat'; $s.WorkingDirectory='%CD%'; $s.Save()"

echo.
echo Pronto! Abra pelo atalho "Sussurro" na Area de Trabalho.
pause
