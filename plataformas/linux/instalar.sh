#!/usr/bin/env bash
# Sussurro — instalador para Linux (Ubuntu/Debian)
set -e
cd "$(dirname "$(readlink -f "$0")")/../.."
RAIZ="$PWD"

echo "==> Dependências do sistema (pede senha)"
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-tk libportaudio2 ffmpeg

echo "==> Criando ambiente Python em $RAIZ/.venv"
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -r requirements.txt google-generativeai

[ -f config.json ] || cp config.example.json config.json

echo "==> Criando atalho no menu de aplicativos"
mkdir -p "$HOME/.local/share/applications"
cat > "$HOME/.local/share/applications/sussurro.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=Sussurro
Comment=Gravador e transcritor
Exec=bash "$RAIZ/plataformas/linux/iniciar.sh"
Icon=audio-input-microphone
Terminal=false
Categories=Audio;Utility;
DESK

echo "Pronto! Abra o Sussurro pelo menu ou com: plataformas/linux/iniciar.sh"
