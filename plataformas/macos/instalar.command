#!/usr/bin/env bash
# Sussurro — instalador para macOS (duplo clique no Finder)
set -e
cd "$(dirname "$0")/../.."

if ! command -v brew >/dev/null 2>&1; then
  echo "Instalando Homebrew (gerenciador de pacotes)..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  eval "$(/opt/homebrew/bin/brew shellenv 2>/dev/null || /usr/local/bin/brew shellenv)"
fi

echo "==> Dependências do sistema"
brew install python@3.12 python-tk@3.12 portaudio ffmpeg

PY="$(brew --prefix)/bin/python3.12"
echo "==> Criando ambiente Python em .venv"
"$PY" -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -r requirements.txt google-generativeai

[ -f config.json ] || cp config.example.json config.json
chmod +x plataformas/macos/iniciar.command
echo "Pronto! Abra com duplo clique em plataformas/macos/iniciar.command"
echo "(Na 1ª gravação o macOS vai pedir permissão de microfone para o Terminal.)"
