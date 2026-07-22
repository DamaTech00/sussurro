#!/bin/bash
# Sobe pro Drive (gdrive_ferda:, raiz) qualquer .wav novo em transcricoes/,
# numerando sequencialmente (1.wav, 2.wav, ...). Rodado via cron.
set -euo pipefail

DIR="/home/ferda/Documentos/FernandaOS/Dev/sussurro/transcricoes"
STATE="/home/ferda/Documentos/FernandaOS/Dev/sussurro/.drive_sync_state.tsv"
LOG="/home/ferda/Documentos/FernandaOS/Dev/sussurro/.drive_sync.log"
REMOTE="gdrive_ferda:"
RCLONE="/home/ferda/.local/bin/rclone"

touch "$STATE"

next=$(awk -F'\t' '$2 ~ /^[0-9]+$/ {print $2}' "$STATE" | sort -n | tail -1)
next=$((${next:-0} + 1))

for f in "$DIR"/*.wav; do
  [ -e "$f" ] || continue
  base=$(basename "$f")
  if ! grep -qF -- "$(printf '%s\t' "$base")" "$STATE"; then
    if "$RCLONE" copyto "$f" "${REMOTE}${next}.wav" >> "$LOG" 2>&1; then
      printf '%s\t%d\n' "$base" "$next" >> "$STATE"
      echo "$(date '+%F %T') uploaded $base as ${next}.wav" >> "$LOG"
      next=$((next + 1))
    else
      echo "$(date '+%F %T') FAILED $base" >> "$LOG"
    fi
  fi
done
