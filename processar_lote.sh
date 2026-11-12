#!/usr/bin/env bash
# Processa TODO o backlog do inbox de uma vez, uma nota por vez, com o Claude Code.
# Uso:  processar_lote.sh [--simular]
#
# Cada nota: snapshot do cofre → Claude organiza → recibo no log → arquiva em _processados/.
# Notas já processadas ficam em _processados/ e não entram de novo (prefixo "_" é ignorado).

set -uo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$DIR/.venv/bin/python"
INBOX="$HOME/Documentos/FernandaOS/MySpace/Inbox"
[ -x "$PY" ] || PY="python3"

EXTRA=""
[ "${1:-}" = "--simular" ] && EXTRA="--dry-run"

n=0; ok=0
for nota in "$INBOX"/*.md; do
  [ -f "$nota" ] || continue
  base="$(basename "$nota")"
  case "$base" in _*) continue ;; esac      # _PROCESSAR, _auto-processador.log etc.
  n=$((n+1))
  echo "════ [$n] $base"
  if "$PY" "$DIR/claude_processar.py" "$nota" $EXTRA; then
    ok=$((ok+1))
  else
    echo "   ✗ falhou — nota mantida no inbox"
  fi
  sleep 3
done

echo
echo "════════════════════════════════════"
echo "notas no backlog: $n | processadas: $ok"
echo "log:  $INBOX/_auto-processador.log"
echo "logs detalhados: $DIR/claude_logs/"
echo "snapshots p/ desfazer: $DIR/claude_logs/snapshots/"
