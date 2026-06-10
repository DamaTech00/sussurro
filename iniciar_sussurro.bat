@echo off
title Sussurro — Gravador e Transcritor
cd /d "%~dp0"
echo Iniciando Sussurro...
echo.
echo Na primeira execucao, o modelo Whisper sera baixado (~150MB).
echo Aguarde alguns segundos apos abrir a janela.
echo.
python sussurro.py
pause
