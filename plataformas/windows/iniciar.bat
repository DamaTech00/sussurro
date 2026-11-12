@echo off
title Sussurro - Gravador e Transcritor
cd /d "%~dp0\..\.."
if not exist .venv\Scripts\pythonw.exe (
  echo Ambiente nao encontrado. Rode antes: plataformas\windows\instalar.bat
  pause
  exit /b 1
)
start "" .venv\Scripts\pythonw.exe sussurro.py
