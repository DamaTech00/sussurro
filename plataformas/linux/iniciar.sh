#!/usr/bin/env bash
# Sussurro — iniciar (Linux)
cd "$(dirname "$(readlink -f "$0")")/../.."
if [ ! -x .venv/bin/python ]; then
  echo "Ambiente não encontrado. Rode antes: plataformas/linux/instalar.sh"; exit 1
fi
exec .venv/bin/python sussurro.py
