#!/usr/bin/env bash
# ============================================================================
# VoiceBM Recorder — node-parameterized (2.0)
# Usage: rec_node.sh <node_id>
# RTSP source read from config.json -> nodes -> {node_id} -> rtsp_url
# (falls back to legacy rooms section). One script serves every node.
# ============================================================================
set -euo pipefail

NODE="${1:?Usage: rec_node.sh <node_id>}"
CONFIG="/home/user/voicebm/config.json"

RTSP_URL=$(python3 -c "
import json
c = json.load(open('$CONFIG'))
n = c.get('nodes', {}).get('$NODE') or c.get('rooms', {}).get('$NODE') or {}
print(n.get('rtsp_url', ''))
")

if [[ -z "$RTSP_URL" ]]; then
    echo "ERROR: no rtsp_url for node '$NODE' in $CONFIG"
    exit 1
fi

REC_DIR="/home/user/voicebm/recordings/$NODE"

# Safety limit - prevent disk from filling up
# At 6-second segments, 5000 files = ~8.3 hours of recordings
MAX_FILES=5000

mkdir -p "$REC_DIR"

# Safety check: Exit if too many files (systemd will retry via RestartSec)
FILE_COUNT=$(find "$REC_DIR" -name "*.wav" -type f 2>/dev/null | wc -l)
if [ "$FILE_COUNT" -ge "$MAX_FILES" ]; then
    echo "SAFETY LIMIT: ${FILE_COUNT} files (max ${MAX_FILES}). Exiting for cleanup."
    echo "  Retention service should clear old files. Systemd will retry."
    exit 1
fi

# Run ffmpeg as main process
# When ffmpeg exits (error or signal), script exits, systemd restarts
exec ffmpeg -hide_banner -nostdin -rtsp_transport tcp \
    -i "$RTSP_URL" \
    -map 0:a:0 -ac 1 -ar 16000 -vn \
    -f segment -segment_time 6 -reset_timestamps 1 -strftime 1 -y \
    "$REC_DIR/${NODE}_%Y%m%d_%H%M%S.wav"
