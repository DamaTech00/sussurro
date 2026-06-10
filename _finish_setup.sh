#!/usr/bin/env bash
# Finaliza o setup do Sussurro no Linux APOS o apt (python3-tk, python3-venv, libportaudio2).
set -e
cd "$(dirname "$(readlink -f "$0")")"
VENV="$HOME/.venvs/sussurro"

echo "==> criando venv em $VENV"
python3 -m venv "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip

echo "==> instalando libs Python"
"$VENV/bin/pip" install -r requirements.txt google-generativeai

echo "==> smoke test (imports)"
"$VENV/bin/python" - <<'PY'
import tkinter, sounddevice, soundcard, numpy, faster_whisper, dotenv
import google.generativeai
print("Todos os imports OK — Sussurro pronto pra abrir.")
PY
echo "==> pronto. Abra com: ./iniciar_sussurro.sh"
