#!/usr/bin/env bash
# Sussurro — Gravador e Transcritor (Linux)
# Na 1a execucao, o modelo Whisper (~150MB) sera baixado. Aguarde apos abrir a janela.
set -e
cd "$(dirname "$(readlink -f "$0")")"

VENV="$HOME/.venvs/sussurro"
PY="$VENV/bin/python"

if [ ! -x "$PY" ]; then
  echo "venv nao encontrado em $VENV."
  echo "Rode antes:  python3 -m venv $VENV && $VENV/bin/pip install -r requirements.txt google-generativeai"
  exit 1
fi

echo "Iniciando Sussurro..."
exec "$PY" sussurro.py
