#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# VoiceBM 2.0 Patch  (B-01/B-03/B-04/B-05/B-06/F-01/F-02)
# -----------------------------------------------------------------------------
# Backs up the live files, renders the 2.0 templates against your existing
# config.json, installs them, and restarts the affected services.
#
# Run from the scripts/ directory of the VoiceBM 2.0 package:
#   sudo ./apply_2_0_patch.sh
#
# config.json must be at ../config.json (standard package layout) or ./config.json.
#
# NOTHING is deleted. Originals are copied to a timestamped backup dir so you
# can roll back with the printed one-liner.
# =============================================================================

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATES_DIR="${SCRIPT_DIR}/../templates/global"
STAMP="$(date +%Y%m%d_%H%M%S)"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}VoiceBM 2.0 Patch Applier${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# =============================================================================
# FIND CONFIG.JSON
# =============================================================================

if [[ -f "${SCRIPT_DIR}/../config.json" ]]; then
    CONFIG_FILE="${SCRIPT_DIR}/../config.json"
elif [[ -f "${SCRIPT_DIR}/config.json" ]]; then
    CONFIG_FILE="${SCRIPT_DIR}/config.json"
else
    echo -e "${RED}ERROR: config.json not found${NC}"
    echo "Expected at: $(cd "${SCRIPT_DIR}/.." && pwd)/config.json"
    exit 1
fi

echo -e "${GREEN}✓${NC} Found config.json: $CONFIG_FILE"

# Detect install user (real user, not root)
if [[ -n "${SUDO_USER:-}" ]]; then
    INSTALL_USER="$SUDO_USER"
else
    INSTALL_USER="$(whoami)"
fi

echo -e "${GREEN}✓${NC} Install user: $INSTALL_USER"

# =============================================================================
# READ CONFIG VALUES
# =============================================================================

echo -e "${YELLOW}Reading configuration...${NC}"

MQTT_BROKER=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE'))['mqtt']['broker'])")
MQTT_PORT=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE'))['mqtt']['port'])")
MQTT_USER=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE'))['mqtt']['user'])")
MQTT_PASS=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE'))['mqtt']['password'])")

VOICEBM_BASE=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE'))['paths']['voicebm_base'])")
SHERPA_BIN=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE'))['paths']['sherpa_bin'])")
SHERPA_MODEL=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE'))['paths']['sherpa_model'])")
CONDA_PATH=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE'))['paths']['conda_path'])")

AUDIO_HOST=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE'))['audio_server']['host'])")
AUDIO_PORT=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE'))['audio_server']['port'])")

# ONNX ASR source path — where handler.py lives on the host before docker cp
ONNX_ASR_SOURCE=$(python3 -c "
import json
c = json.load(open('$CONFIG_FILE'))
print(c.get('paths', {}).get('onnx_asr_source', ''))
" 2>/dev/null || echo "")

if [[ -z "$ONNX_ASR_SOURCE" ]]; then
    ONNX_ASR_SOURCE="$(dirname "$VOICEBM_BASE")/onnx-asr-addon/onnx-asr"
    echo -e "${YELLOW}  ⚠${NC} onnx_asr_source not in config.json — inferring: $ONNX_ASR_SOURCE"
fi

BIN_DIR="${VOICEBM_BASE}/bin"
CONFIG_LIVE="${VOICEBM_BASE}/config.json"
BACKUP_DIR="${VOICEBM_BASE}/backups/patch_2.0_${STAMP}"
DOCKER_CONTAINER="nifty_grothendieck"
DOCKER_HANDLER_DST="/app/wyoming_onnx_asr/handler.py"
HANDLER_HOST_PATH="${ONNX_ASR_SOURCE}/handler.py"

echo -e "${GREEN}✓${NC} VoiceBM Base: $VOICEBM_BASE"
echo -e "${GREEN}✓${NC} ONNX ASR Source: $ONNX_ASR_SOURCE"
echo ""

# =============================================================================
# VERIFY TEMPLATES PRESENT
# =============================================================================

REQUIRED_TEMPLATES=(
    "voicebm_config.py.template"
    "voicebm_stt_service.py.template"
    "mqtt_commands.py.template"
    "enrollment_watcher.py.template"
    "handler.py.template"
)

MISSING=0
for t in "${REQUIRED_TEMPLATES[@]}"; do
    if [[ ! -f "${TEMPLATES_DIR}/${t}" ]]; then
        echo -e "${RED}  MISSING template: ${TEMPLATES_DIR}/${t}${NC}"
        MISSING=1
    fi
done
[[ "$MISSING" -eq 1 ]] && { echo "Aborting — templates incomplete."; exit 1; }

echo -e "${GREEN}✓${NC} All required templates present"
echo ""

# =============================================================================
# ESCAPE SPECIAL CHARACTERS FOR SED
# =============================================================================

escape_sed() {
    echo "$1" | sed -e 's/[\/&]/\\&/g' -e 's/$/\\n/' | tr -d '\n'
}

MQTT_BROKER_ESC=$(escape_sed "$MQTT_BROKER")
MQTT_USER_ESC=$(escape_sed "$MQTT_USER")
MQTT_PASS_ESC=$(escape_sed "$MQTT_PASS")
AUDIO_HOST_ESC=$(escape_sed "$AUDIO_HOST")
VOICEBM_BASE_ESC=$(escape_sed "$VOICEBM_BASE")
SHERPA_BIN_ESC=$(escape_sed "$SHERPA_BIN")
SHERPA_MODEL_ESC=$(escape_sed "$SHERPA_MODEL")
CONDA_PATH_ESC=$(escape_sed "$CONDA_PATH")

render_template() {
    local template_file="$1"
    local output_file="$2"

    sed -e "s|{MQTT_BROKER}|${MQTT_BROKER_ESC}|g" \
        -e "s|{MQTT_PORT}|${MQTT_PORT}|g" \
        -e "s|{MQTT_USER}|${MQTT_USER_ESC}|g" \
        -e "s|{MQTT_PASS}|${MQTT_PASS_ESC}|g" \
        -e "s|{AUDIO_HOST}|${AUDIO_HOST_ESC}|g" \
        -e "s|{AUDIO_PORT}|${AUDIO_PORT}|g" \
        -e "s|{VOICEBM_BASE}|${VOICEBM_BASE_ESC}|g" \
        -e "s|{SHERPA_BIN}|${SHERPA_BIN_ESC}|g" \
        -e "s|{SHERPA_MODEL}|${SHERPA_MODEL_ESC}|g" \
        -e "s|{CONDA_PATH}|${CONDA_PATH_ESC}|g" \
        -e "s|{INSTALL_USER}|${INSTALL_USER}|g" \
        "$template_file" > "$output_file"
}

# =============================================================================
# [1/5] BACKUP LIVE FILES
# =============================================================================

echo -e "${YELLOW}[1/5] Backing up live files...${NC}"

mkdir -p "$BACKUP_DIR"

declare -A BACKUP_MAP=(
    ["voicebm_config.py"]="${BIN_DIR}/voicebm_config.py"
    ["voicebm_stt_service.py"]="${BIN_DIR}/voicebm_stt_service.py"
    ["mqtt_commands.py"]="${BIN_DIR}/mqtt_commands.py"
    ["enrollment_watcher.py"]="${BIN_DIR}/enrollment_watcher.py"
)

for fname in "${!BACKUP_MAP[@]}"; do
    src="${BACKUP_MAP[$fname]}"
    if [[ -f "$src" ]]; then
        cp -p "$src" "${BACKUP_DIR}/${fname}"
        echo -e "${GREEN}  ✓${NC} saved ${src}"
    else
        echo -e "${YELLOW}  ⚠${NC} not found (first install): ${src}"
    fi
done

# Backup live Docker handler
if docker exec "${DOCKER_CONTAINER}" test -f "${DOCKER_HANDLER_DST}" 2>/dev/null; then
    docker cp "${DOCKER_CONTAINER}:${DOCKER_HANDLER_DST}" "${BACKUP_DIR}/handler.py" 2>/dev/null || true
    echo -e "${GREEN}  ✓${NC} saved (docker) ${DOCKER_HANDLER_DST}"
fi

# Backup config.json
if [[ -f "${CONFIG_LIVE}" ]]; then
    cp -p "${CONFIG_LIVE}" "${BACKUP_DIR}/config.json"
    echo -e "${GREEN}  ✓${NC} saved ${CONFIG_LIVE}"
fi

echo ""

# =============================================================================
# [2/5] PATCH config.json — ADD 2.0 TUNABLES IF MISSING
# =============================================================================

echo -e "${YELLOW}[2/5] Ensuring config.json has 2.0 tunables...${NC}"

if [[ -f "${CONFIG_LIVE}" ]]; then
    python3 -c "
import json
p = '${CONFIG_LIVE}'
with open(p) as f:
    cfg = json.load(f)
vb = cfg.get('voicebm', {})
changed = False
if 'gallery_max' not in vb:
    vb['gallery_max'] = 75
    changed = True
if 'active_lead_trim_ms' not in vb:
    vb['active_lead_trim_ms'] = 0
    changed = True
if changed:
    cfg['voicebm'] = vb
    with open(p, 'w') as f:
        json.dump(cfg, f, indent=2)
    print('  Added voicebm tunables: ' + str(vb))
else:
    print('  voicebm section already present: ' + str(vb))
"
else
    echo -e "${YELLOW}  ⚠${NC} ${CONFIG_LIVE} not found — defaults will apply (gallery_max=75, active_lead_trim_ms=0)"
fi

echo ""

# =============================================================================
# [3/5] RENDER AND INSTALL HOST PYTHON FILES
# =============================================================================

echo -e "${YELLOW}[3/5] Rendering and installing patched host files...${NC}"

declare -A INSTALL_MAP=(
    ["voicebm_config.py.template"]="${BIN_DIR}/voicebm_config.py"
    ["voicebm_stt_service.py.template"]="${BIN_DIR}/voicebm_stt_service.py"
    ["mqtt_commands.py.template"]="${BIN_DIR}/mqtt_commands.py"
    ["enrollment_watcher.py.template"]="${BIN_DIR}/enrollment_watcher.py"
)

for tmpl in "${!INSTALL_MAP[@]}"; do
    dst="${INSTALL_MAP[$tmpl]}"
    render_template "${TEMPLATES_DIR}/${tmpl}" "$dst"
    chown "$INSTALL_USER:$INSTALL_USER" "$dst"
    chmod 644 "$dst"
    echo -e "${GREEN}  ✓${NC} $(basename $dst)"
done

echo ""

# =============================================================================
# [4/5] RESTART HOST SERVICES
# =============================================================================

echo -e "${YELLOW}[4/5] Restarting host services...${NC}"

RESTART_SERVICES=(
    "voicebm-stt.service"
    "voicebm-commands.service"
    "voicebm-enrollment-watcher.service"
)

for svc in "${RESTART_SERVICES[@]}"; do
    if systemctl list-unit-files 2>/dev/null | grep -q "^${svc}"; then
        systemctl restart "$svc"
        sleep 1
        if systemctl is-active --quiet "$svc"; then
            echo -e "${GREEN}  ✓${NC} $svc"
        else
            echo -e "${RED}  ✗${NC} $svc (check: journalctl -u $svc -n 30 --no-pager)"
        fi
    else
        echo -e "${YELLOW}  ⚠${NC} not installed: $svc"
    fi
done

echo ""

# =============================================================================
# [5/5] UPDATE DOCKER HANDLER (copy + restart only — never rebuild)
# =============================================================================

echo -e "${YELLOW}[5/5] Updating Docker handler.py...${NC}"

render_template "${TEMPLATES_DIR}/handler.py.template" "${HANDLER_HOST_PATH}"
chown "$INSTALL_USER:$INSTALL_USER" "${HANDLER_HOST_PATH}"
echo -e "${GREEN}  ✓${NC} rendered to ${HANDLER_HOST_PATH}"

docker cp "${HANDLER_HOST_PATH}" "${DOCKER_CONTAINER}:${DOCKER_HANDLER_DST}"
docker restart "${DOCKER_CONTAINER}"
echo -e "${GREEN}  ✓${NC} copied into ${DOCKER_CONTAINER} and restarted"

echo ""

# =============================================================================
# COMPLETION + ROLLBACK INSTRUCTIONS
# =============================================================================

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}VoiceBM 2.0 Patch Complete${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Backup dir: ${BACKUP_DIR}"
echo ""
echo "Rollback (if needed):"
for fname in "${!BACKUP_MAP[@]}"; do
    echo "  cp ${BACKUP_DIR}/${fname} ${BACKUP_MAP[$fname]}"
done
echo "  cp ${BACKUP_DIR}/config.json ${CONFIG_LIVE}"
echo "  sudo systemctl restart ${RESTART_SERVICES[*]}"
echo "  sudo docker cp ${BACKUP_DIR}/handler.py ${DOCKER_CONTAINER}:${DOCKER_HANDLER_DST} && sudo docker restart ${DOCKER_CONTAINER}"
echo ""
echo "What changed in 2.0:"
echo "  voicebm/transcript/debug     — renamed raw transcript feed (was the old single topic)"
echo "  voicebm/transcript/preferred — new gate-enforced feed (blocked = empty payload)"
echo "  voicebm/current_speaker      — corrected global topic (was voicebm/living/current_speaker)"
echo "  voicebm/inject_identity      — corrected global topic (was voicebm/living/inject_identity)"
echo "  gallery_max / active_lead_trim_ms — new tunables in config.json voicebm section"
echo ""
echo "Automations on the old transcript topic must repoint to:"
echo "  voicebm/transcript/preferred  (recommended — gate-enforced)"
echo "  voicebm/transcript/debug      (raw — same behavior as old topic)"
echo ""
