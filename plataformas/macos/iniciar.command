#!/usr/bin/env bash
# Sussurro — iniciar (macOS, duplo clique no Finder)
cd "$(dirname "$0")/../.."
if [ ! -x .venv/bin/python ]; then
  echo "Ambiente não encontrado. Rode antes: plataformas/macos/instalar.command"; read -r; exit 1
fi
exec .venv/bin/python sussurro.py
