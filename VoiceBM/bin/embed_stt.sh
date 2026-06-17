#!/usr/bin/env bash
set -euo pipefail

# Voice biometrics embedding script for STT analysis
# Usage: ./embed_stt.sh <input_wav> <output_txt>

INPUT="$1"
OUTPUT="$2"

# DEBUG LOGGING
echo "[embed_stt.sh] START: $(date '+%Y-%m-%d %H:%M:%S.%3N')" >&2
echo "[embed_stt.sh] INPUT: $INPUT" >&2
echo "[embed_stt.sh] OUTPUT: $OUTPUT" >&2

# CRITICAL: Use vb Python
PYTHON="/home/user/miniforge3/envs/vb/bin/python3"
SHERPA_WORKER="/home/user/.local/bin/sherpa_embed.py"
SHERPA_MODEL="/home/user/sherpa_models/nemo_en_titanet_small.onnx"

echo "[embed_stt.sh] PYTHON: $PYTHON" >&2
echo "[embed_stt.sh] WORKER: $SHERPA_WORKER" >&2
echo "[embed_stt.sh] MODEL: $SHERPA_MODEL" >&2

# Check if input file exists
if [ ! -f "$INPUT" ]; then
    echo "[embed_stt.sh] ERROR: Input WAV not found: $INPUT" >&2
    exit 1
fi

echo "[embed_stt.sh] Input file size: $(stat -c%s "$INPUT") bytes" >&2

# Create embedding
echo "[embed_stt.sh] Calling Sherpa..." >&2
START_TIME=$(date +%s%3N)

"$PYTHON" "$SHERPA_WORKER" \
    --model "$SHERPA_MODEL" \
    --wav "$INPUT" \
    --out "$OUTPUT" 2>&1

SHERPA_EXIT=$?
END_TIME=$(date +%s%3N)
ELAPSED=$((END_TIME - START_TIME))

echo "[embed_stt.sh] Sherpa exit code: $SHERPA_EXIT" >&2
echo "[embed_stt.sh] Sherpa execution time: ${ELAPSED}ms" >&2

# Check if output was created
if [ ! -f "$OUTPUT" ]; then
    echo "[embed_stt.sh] ERROR: Output embedding not created: $OUTPUT" >&2
    exit 1
fi

OUTPUT_SIZE=$(stat -c%s "$OUTPUT")
echo "[embed_stt.sh] Output file size: $OUTPUT_SIZE bytes" >&2

if [ "$OUTPUT_SIZE" -eq 0 ]; then
    echo "[embed_stt.sh] ERROR: Output embedding is empty" >&2
    exit 1
fi

echo "[embed_stt.sh] SUCCESS: Embedding created" >&2
echo "[embed_stt.sh] END: $(date '+%Y-%m-%d %H:%M:%S.%3N')" >&2

exit 0
