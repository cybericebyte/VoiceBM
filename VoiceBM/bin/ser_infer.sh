#!/usr/bin/env bash
set -euo pipefail

# VoiceBM Emote Edition — SER inference wrapper
# Usage: ./ser_infer.sh <input_wav> <output_json>

INPUT="$1"
OUTPUT="$2"

echo "[ser_infer.sh] START: $(date '+%Y-%m-%d %H:%M:%S.%3N')" >&2
echo "[ser_infer.sh] INPUT:  $INPUT" >&2
echo "[ser_infer.sh] OUTPUT: $OUTPUT" >&2

PYTHON="/home/user/miniforge3/envs/vb/bin/python3"
SER_WORKER="/home/user/.local/bin/ser_worker.py"

echo "[ser_infer.sh] PYTHON: $PYTHON" >&2
echo "[ser_infer.sh] WORKER: $SER_WORKER" >&2

if [ ! -f "$INPUT" ]; then
    echo "[ser_infer.sh] ERROR: Input WAV not found: $INPUT" >&2
    exit 1
fi

echo "[ser_infer.sh] Input file size: $(stat -c%s "$INPUT") bytes" >&2

echo "[ser_infer.sh] Calling SER worker..." >&2
START_TIME=$(date +%s%3N)

"$PYTHON" "$SER_WORKER" \
    --wav "$INPUT" \
    --out "$OUTPUT" 2>&1

SER_EXIT=$?
END_TIME=$(date +%s%3N)
ELAPSED=$((END_TIME - START_TIME))

echo "[ser_infer.sh] Exit code: $SER_EXIT, elapsed: ${ELAPSED}ms" >&2

if [ ! -f "$OUTPUT" ]; then
    echo "[ser_infer.sh] ERROR: Output JSON not created: $OUTPUT" >&2
    exit 1
fi

OUTPUT_SIZE=$(stat -c%s "$OUTPUT")
echo "[ser_infer.sh] Output file size: $OUTPUT_SIZE bytes" >&2

if [ "$OUTPUT_SIZE" -eq 0 ]; then
    echo "[ser_infer.sh] ERROR: Output JSON is empty" >&2
    exit 1
fi

echo "[ser_infer.sh] SUCCESS" >&2
echo "[ser_infer.sh] END: $(date '+%Y-%m-%d %H:%M:%S.%3N')" >&2

exit 0
