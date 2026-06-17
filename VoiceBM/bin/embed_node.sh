#!/usr/bin/env bash
# ============================================================================
# VoiceBM Embedder — node-parameterized (2.0)
# Usage: embed_node.sh <node_id>
# Watches recordings/{node}, embeds via Sherpa, logs to meta/logs.jsonl
# with node_id={node}. One script serves every node.
# ============================================================================
set -euo pipefail

NODE="${1:?Usage: embed_node.sh <node_id>}"

source /home/user/miniforge3/etc/profile.d/conda.sh
conda activate vb

IN=/home/user/voicebm/recordings/$NODE
OUT=/home/user/voicebm/embeddings/$NODE
LOG=/home/user/voicebm/meta/logs.jsonl

PYTHON=/home/user/miniforge3/envs/vb/bin/python3
SHERPA_WORKER=/home/user/.local/bin/sherpa_embed.py
SHERPA_MODEL=/home/user/sherpa_models/nemo_en_titanet_small.onnx

mkdir -p "$OUT" "$(dirname "$LOG")"

while true; do
  shopt -s nullglob
  for f in "$IN"/*.wav; do
    [[ -f "$f" ]] || continue
    b=$(basename "$f" .wav)
    t="$OUT/$b.txt"
    [[ -f "$t" ]] && continue
    size=$(stat -c%s "$f" 2>/dev/null) || continue
    [[ "$size" -lt 1000 ]] && continue
    "$PYTHON" "$SHERPA_WORKER" --model "$SHERPA_MODEL" --wav "$f" --out "$t" 2>/dev/null || true
    python3 - "$f" "$t" "$NODE" >>"$LOG" <<'PY'
import json, os, sys, time
row=dict(ts_iso=time.strftime('%Y-%m-%dT%H:%M:%SZ'),
         node_id=sys.argv[3], wav=sys.argv[1], emb=sys.argv[2],
         model='sherpa-nemo-titanet', device='cpu')
print(json.dumps(row))
PY
  done
  sleep 2
done
