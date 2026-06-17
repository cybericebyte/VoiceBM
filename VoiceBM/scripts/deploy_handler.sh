#!/usr/bin/env bash
# ============================================================================
# VoiceBM — ASR Handler Deploy
# ============================================================================
# The handler is the one real template. Its MQTT credentials are filled from
# config.json (already authored by the wizard), it's copied into the EXISTING
# ASR container, the container is restarted, and the rendered host copy is
# deleted — no residual, no secret left on disk.
#
# The container is NEVER built or rebuilt — only handler.py is replaced.
#
# Usage: sudo ./deploy_handler.sh <container_name> [--config /path/config.json]
#        (container also read from config.json -> active.asr_container if present)
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKG_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
TEMPLATE="${PKG_DIR}/templates/active/handler.py.template"
HANDLER_DST="/app/wyoming_onnx_asr/handler.py"

# Resolve config.json: VOICEBM_BASE env, or --config, or alongside a sibling base.
CONFIG_FILE="${VOICEBM_BASE:+${VOICEBM_BASE}/config.json}"
CONTAINER=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --config) CONFIG_FILE="$2"; shift 2 ;;
    *) CONTAINER="$1"; shift ;;
  esac
done

[[ -n "${CONFIG_FILE:-}" && -f "$CONFIG_FILE" ]] || {
  echo "Need config.json. Set VOICEBM_BASE or pass --config /path/config.json"; exit 1; }
[[ -f "$TEMPLATE" ]] || { echo "Handler template not found: $TEMPLATE"; exit 1; }

# Container name: arg wins, else config.json -> active.asr_container
if [[ -z "$CONTAINER" ]]; then
  CONTAINER="$(python3 -c "import json;print(json.load(open('$CONFIG_FILE')).get('active',{}).get('asr_container',''))" 2>/dev/null || true)"
fi
[[ -n "$CONTAINER" ]] || { echo "No container name (pass it as an arg or set active.asr_container in config.json)"; exit 1; }

command -v docker >/dev/null 2>&1 || { echo "docker not available"; exit 1; }
docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER" || {
  echo "Container '$CONTAINER' not found. The handler goes into an EXISTING container — none is built here."; exit 1; }

# Render: fill the MQTT placeholders from config.json (python handles any chars in the password).
TMP_HANDLER="$(mktemp /tmp/handler.XXXXXX.py)"
trap 'rm -f "$TMP_HANDLER"' EXIT

python3 - "$TEMPLATE" "$CONFIG_FILE" "$TMP_HANDLER" <<'PY'
import json, sys
tmpl, cfg_path, out = sys.argv[1], sys.argv[2], sys.argv[3]
cfg = json.load(open(cfg_path))
m = cfg.get("mqtt", {})
s = open(tmpl).read()
fills = {
    "@@MQTT_BROKER@@": str(m.get("broker", "")),
    "@@MQTT_PORT@@":   str(m.get("port", 1883)),
    "@@MQTT_USER@@":   str(m.get("user", "")),
    "@@MQTT_PASS@@":   str(m.get("password", "")),
}
for k, v in fills.items():
    s = s.replace(k, v)
assert "@@MQTT_" not in s, "unfilled MQTT placeholder remains"
open(out, "w").write(s)
print("rendered handler with MQTT from config.json")
PY

echo "→ copying handler into ${CONTAINER}:${HANDLER_DST}"
docker cp "$TMP_HANDLER" "${CONTAINER}:${HANDLER_DST}"
echo "→ restarting ${CONTAINER}"
docker restart "$CONTAINER" >/dev/null
rm -f "$TMP_HANDLER"
echo "OK — handler deployed, container restarted, host residual deleted."
