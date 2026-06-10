#!/usr/bin/env bash
# Auto-processador do inbox do Sussurro (disparado por evento após salvar a captura).
# CAMADA 1 (barata): Gemini planeja + script arquiva  → processar_inbox.py
# CAMADA 2 (exceção): se a Gemini se declarar insegura (exit 3), o Claude assume.
# Uso: auto_processar.sh /caminho/para/nota_inbox.md
set -uo pipefail

NOTE="${1:-}"
VAULT_ROOT="$HOME/FernandaOS"
PESSOAL="$VAULT_ROOT/fernanda-obsidian-main"
LOG="$PESSOAL/Inbox/_auto-processador.log"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$HOME/.venvs/sussurro/bin/python"
CLAUDE="$HOME/.local/bin/claude"
TS() { date '+%Y-%m-%d %H:%M:%S'; }

if [ -z "$NOTE" ] || [ ! -f "$NOTE" ]; then
  echo "$(TS)  ✗ sem arquivo válido ($NOTE)" >> "$LOG"
  exit 1
fi
[ -x "$PY" ] || PY="python3"

# ── Camada 1: Gemini ──────────────────────────────────────────────────────────
"$PY" "$DIR/processar_inbox.py" "$NOTE"
RC=$?
[ "$RC" -ne 3 ] && exit "$RC"   # 0 = feito pela Gemini; 1 = erro tratado

# ── Camada 2: Claude (só quando a Gemini escala) ──────────────────────────────
read -r -d '' PROMPT <<EOF
Você é a camada de exceção do inbox da Fernanda — a Gemini não deu conta desta nota.
Processe SOMENTE esta nota: $NOTE
Siga "fernanda-obsidian-main/Inbox/_PROCESSAR (instruções pro Claude).md":
decomponha em notas atômicas, aplique o template do tipo certo (use Write), crie os
[[links]] cruzados (e o book/página-mãe se for ficção), marque a nota do inbox como
'status: processado' preservando a transcrição, e acrescente 1 linha em
"fernanda-obsidian-main/Inbox/_auto-processador.log".
Não apague nada; ambíguo → '#revisar'; ops que precisem de Calendar/Gmail → 'TODO (interativo)'.
EOF

echo "$(TS)  ⇧ Claude assumindo $(basename "$NOTE")" >> "$LOG"
cd "$VAULT_ROOT" || exit 1
if "$CLAUDE" -p "$PROMPT" --permission-mode acceptEdits --add-dir "$VAULT_ROOT" >> "$LOG" 2>&1; then
  echo "$(TS)  ✓ Claude ok $(basename "$NOTE")" >> "$LOG"
else
  echo "$(TS)  ✗ Claude falhou $(basename "$NOTE") (rode 'processa meu inbox')" >> "$LOG"
fi
