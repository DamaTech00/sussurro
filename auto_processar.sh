#!/usr/bin/env bash
# Auto-processador do inbox do Sussurro — disparado por evento quando a captura é salva.
#
# ANTES (até jun/2026): CAMADA 1 = Gemini planejava (barato) → CAMADA 2 = Claude nas exceções.
#   Morreu quando o Gemini ficou sem crédito (HTTP 402): a camada 1 falhava com exit 1,
#   então o Claude nunca era chamado e o inbox parou de ser processado.
#
# AGORA (01/nov/2026): o Claude Code é a camada PRINCIPAL — roda na assinatura da Fê
#   (Claude Pro), custo marginal zero. Toda a lógica vive em claude_processar.py
#   (snapshot do cofre antes de escrever, ferramentas restritas, recibo no log, arquivamento).
#
# Uso: auto_processar.sh /caminho/para/nota_inbox.md

set -uo pipefail

NOTE="${1:-}"
shift || true          # o resto dos argumentos (ex.: --dry-run) vai pro Python
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$DIR/.venv/bin/python"
LOG="$HOME/Documentos/FernandaOS/MySpace/Inbox/_auto-processador.log"

ts() { date '+%Y-%m-%d %H:%M:%S'; }

if [ -z "$NOTE" ] || [ ! -f "$NOTE" ]; then
  mkdir -p "$(dirname "$LOG")"
  echo "$(ts)  ✗ auto_processar: captura inválida ($NOTE)" >> "$LOG"
  exit 1
fi

[ -x "$PY" ] || PY="python3"

exec "$PY" "$DIR/claude_processar.py" "$NOTE" "$@"
