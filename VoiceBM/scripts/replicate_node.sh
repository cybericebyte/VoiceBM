#!/usr/bin/env bash
# ============================================================================
# VoiceBM Node Replication — node-parameterized trio (2.0)
# ============================================================================
# Stands up a passive recording node from config.json -> nodes -> {node_id}.
#
# Usage: sudo ./replicate_node.sh <node_id>
# Example: sudo ./replicate_node.sh bedroom
#
# 2.0 model (vs the legacy per-room-copy model):
#   - Reads the 'nodes' section (falls back to legacy 'rooms').
#   - Does NOT generate per-room script copies. Instead it creates THREE
#     systemd services that each invoke the shared, parameterized live
#     scripts with the node id:
#         voicebm-recorder-{node}   -> rec_node.sh   {node}
#         voicebm-embedder-{node}   -> embed_node.sh {node}
#         voicebm-publisher-{node}  -> publish_identity_node.py {node}
#   - Adds all three to voicebm.target and starts them.
#
# Global services (vad_filter, cluster_publisher, global publisher, retention)
# are single instances installed by the global deploy — not per node.
#
# NOTE: the per-node unit stanzas below are built from the canonical recorder
# service pattern plus each script's own runtime needs (recorder/embedder run
# their env inside the shell script; the publisher is a .py launched with the
# resolved env interpreter). If your live units differ, adjust the heredocs.
# ============================================================================

set -euo pipefail

# --- resolve install paths from config.json + the invoking user (runtime) ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKG_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIG_FILE="${VOICEBM_CONFIG:-$PKG_ROOT/config.json}"
[[ -f "$CONFIG_FILE" ]] || { echo "config.json not found at $CONFIG_FILE — run setup_voicebm.sh, or the global deploy, first"; exit 1; }

eval "$(PYTHONNOUSERSITE=1 python3 - "$CONFIG_FILE" <<'PY'
import json, sys, shlex
c = json.load(open(sys.argv[1]))
p = c.get("paths", {}); e = c.get("environment", {})
def q(k, v): print(f'{k}={shlex.quote(str(v or ""))}')
q("VOICEBM_BASE", p.get("voicebm_base", ""))
q("PYTHON_BIN",   e.get("python_bin") or p.get("python_bin", ""))
PY
)"
[[ -n "$VOICEBM_BASE" && -n "$PYTHON_BIN" ]] || { echo "config.json is missing voicebm_base or the interpreter"; exit 1; }
INSTALL_USER="${SUDO_USER:-$(id -un)}"

BIN_DIR="${VOICEBM_BASE}/bin"
SYSTEMD_DIR="/etc/systemd/system"
TARGET_FILE="${SYSTEMD_DIR}/voicebm.target"

# Colors
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'

# Root required (writes unit files)
if [[ $EUID -ne 0 ]]; then
  echo -e "${RED}This script must be run as root (use sudo)${NC}"; exit 1
fi

if [[ $# -ne 1 ]]; then
  echo -e "${RED}Usage: $0 <node_id>${NC}"; echo -e "${YELLOW}Example: $0 bedroom${NC}"; exit 1
fi
NODE="$1"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}VoiceBM Node Replication (2.0)${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "Node: ${GREEN}${NODE}${NC}\n"

[[ -f "$CONFIG_FILE" ]] || { echo -e "${RED}Config not found: ${CONFIG_FILE}${NC}"; exit 1; }

# Validate node + pull rtsp_url from nodes (fallback rooms). recorder_enabled must be true.
echo -e "${YELLOW}→${NC} Reading config.json..."
RTSP_URL=$(NODE="$NODE" "$PYTHON_BIN" - "$CONFIG_FILE" <<'PY'
import json, os, sys
node = os.environ["NODE"]
cfg = json.load(open(sys.argv[1]))
n = cfg.get("nodes", {}).get(node)
if n is None:
    n = cfg.get("rooms", {}).get(node)
if n is None:
    print("ERROR: node not found in 'nodes' or 'rooms'"); sys.exit(0)
if not n.get("rtsp_url"):
    print("ERROR: no rtsp_url configured"); sys.exit(0)
if not n.get("recorder_enabled", False):
    print("ERROR: recorder_enabled is not true (ambient-only nodes are served by the ambient service, not replicate_node.sh)"); sys.exit(0)
print(n["rtsp_url"])
PY
)
if [[ "$RTSP_URL" == ERROR:* ]]; then
  echo -e "${RED}${RTSP_URL#ERROR: }${NC}"; exit 1
fi
echo -e "${GREEN}✓${NC} Node validated"
echo -e "  RTSP: ${RTSP_URL}\n"

# Directories
echo -e "${YELLOW}→${NC} Creating directories..."
mkdir -p "${VOICEBM_BASE}/recordings/${NODE}" "${VOICEBM_BASE}/embeddings/${NODE}"
chown -R "${INSTALL_USER}:${INSTALL_USER}" "${VOICEBM_BASE}/recordings/${NODE}" "${VOICEBM_BASE}/embeddings/${NODE}"
echo -e "${GREEN}✓${NC} ${VOICEBM_BASE}/recordings/${NODE}/  +  embeddings/${NODE}/\n"

# --- Service writers (shared stanza, per-role ExecStart) ---
write_recorder_service() {
  cat > "${SYSTEMD_DIR}/voicebm-recorder-${NODE}.service" << SVC
[Unit]
Description=VoiceBM Recorder (${NODE})
After=network-online.target
Wants=network-online.target
PartOf=voicebm.target

[Service]
Type=simple
User=${INSTALL_USER}
WorkingDirectory=${VOICEBM_BASE}
ExecStart=/usr/bin/env bash ${BIN_DIR}/rec_node.sh ${NODE}
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
SVC
}

write_embedder_service() {
  cat > "${SYSTEMD_DIR}/voicebm-embedder-${NODE}.service" << SVC
[Unit]
Description=VoiceBM Embedder (${NODE})
After=network-online.target
Wants=network-online.target
PartOf=voicebm.target

[Service]
Type=simple
User=${INSTALL_USER}
WorkingDirectory=${VOICEBM_BASE}
ExecStart=/usr/bin/env bash ${BIN_DIR}/embed_node.sh ${NODE}
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
SVC
}

write_publisher_service() {
  cat > "${SYSTEMD_DIR}/voicebm-publisher-${NODE}.service" << SVC
[Unit]
Description=VoiceBM Identity Publisher (${NODE})
After=network-online.target
Wants=network-online.target
PartOf=voicebm.target

[Service]
Type=simple
User=${INSTALL_USER}
WorkingDirectory=${VOICEBM_BASE}
Environment=PYTHONNOUSERSITE=1
ExecStart=${PYTHON_BIN} ${BIN_DIR}/publish_identity_node.py ${NODE}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SVC
}

echo -e "${YELLOW}→${NC} Writing systemd services..."
write_recorder_service
write_embedder_service
write_publisher_service
echo -e "${GREEN}✓${NC} voicebm-recorder-${NODE}.service"
echo -e "${GREEN}✓${NC} voicebm-embedder-${NODE}.service"
echo -e "${GREEN}✓${NC} voicebm-publisher-${NODE}.service\n"

# Update voicebm.target (must already exist — global deploy creates it)
echo -e "${YELLOW}→${NC} Updating voicebm.target..."
[[ -f "$TARGET_FILE" ]] || { echo -e "${RED}voicebm.target not found at ${TARGET_FILE} — run the global deploy first${NC}"; exit 1; }

add_to_target() {
  local svc="$1"
  if grep -q "Wants=${svc}" "$TARGET_FILE"; then
    echo -e "${YELLOW}ℹ${NC} ${svc} already in target"; return 0
  fi
  if grep -q '^Wants=' "$TARGET_FILE"; then
    # keep Wants together: insert right after the LAST existing Wants= line
    awk -v line="Wants=${svc}" '
      /^Wants=/ { last=NR } { rows[NR]=$0 }
      END { for (i=1;i<=NR;i++){ print rows[i]; if (i==last) print line } }
    ' "$TARGET_FILE" > "${TARGET_FILE}.tmp" && mv "${TARGET_FILE}.tmp" "$TARGET_FILE"
  elif grep -q '^\[Unit\]' "$TARGET_FILE"; then
    sed -i "/^\[Unit\]/a Wants=${svc}" "$TARGET_FILE"
  else
    printf 'Wants=%s\n' "$svc" >> "$TARGET_FILE"
  fi
  echo -e "${GREEN}✓${NC} added ${svc}"
}

for role in recorder embedder publisher; do
  add_to_target "voicebm-${role}-${NODE}.service"
done
echo

echo -e "${YELLOW}→${NC} Reloading systemd..."
systemctl daemon-reload
echo -e "${GREEN}✓${NC} reloaded\n"

echo -e "${YELLOW}→${NC} Enabling + starting services..."
fail=0
for role in recorder embedder publisher; do
  svc="voicebm-${role}-${NODE}.service"
  systemctl enable "$svc" >/dev/null 2>&1 || true
  systemctl start "$svc" || true
  sleep 1
  if systemctl is-active --quiet "$svc"; then
    echo -e "${GREEN}✓${NC} ${svc} active"
  else
    echo -e "${RED}✗${NC} ${svc} not active — check: journalctl -u ${svc} -n 50"
    fail=1
  fi
done
echo

echo -e "${BLUE}========================================${NC}"
if [[ $fail -eq 0 ]]; then
  echo -e "${GREEN}✓ Node '${NODE}' replicated — recorder + embedder + publisher up${NC}"
else
  echo -e "${YELLOW}Node '${NODE}' created, but one or more services need attention${NC}"
fi
echo -e "${BLUE}========================================${NC}"
echo -e "  Recorder:  ${BLUE}sudo systemctl status voicebm-recorder-${NODE}${NC}"
echo -e "  Embedder:  ${BLUE}sudo systemctl status voicebm-embedder-${NODE}${NC}"
echo -e "  Publisher: ${BLUE}sudo systemctl status voicebm-publisher-${NODE}${NC}\n"
