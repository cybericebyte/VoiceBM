#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# VoiceBM — global deploy (foundation + active + singleton services)
# -----------------------------------------------------------------------------
# Lays the cleaned package files onto this machine using the values in
# config.json, installs the systemd units, deploys the ASR handler into the
# existing ONNX ASR container, and starts voicebm.target.
#
# Per-node passive services (recorder/embedder/publisher) are NOT installed
# here — they are generated one node at a time by scripts/replicate_node.sh.
#
# Run with sudo (installing units needs root). config.json is produced by
# setup_voicebm.sh, which passes its path as $1. Run directly and it reads
# ./config.json next to the package. Nothing here rebuilds Docker; the handler
# is copied in and the container is restarted, per the project rules.
# =============================================================================

C_G=$'\033[0;32m'; C_Y=$'\033[1;33m'; C_R=$'\033[0;31m'; C_N=$'\033[0m'
ok()   { printf '  %bOK%b  %s\n' "$C_G" "$C_N" "$*"; }
warn() { printf '  %b!!%b  %s\n' "$C_Y" "$C_N" "$*"; }
die()  { printf '  %bXX%b  %s\n' "$C_R" "$C_N" "$*" >&2; exit 1; }
head() { printf '\n== %s ==\n' "$*"; }

[[ $EUID -eq 0 ]] || die "Run with sudo — installing systemd units needs root."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKG_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIG="${1:-$PKG_ROOT/config.json}"
[[ -f "$CONFIG" ]] || die "config.json not found at $CONFIG (run ./setup_voicebm.sh to generate it."

DEPLOY_USER="${SUDO_USER:-$(id -un)}"
USER_HOME="$(getent passwd "$DEPLOY_USER" | cut -d: -f6)"
[[ -n "$USER_HOME" ]] || USER_HOME="/home/$DEPLOY_USER"

# ── read config.json (shell-safe via shlex) ─────────────────────────────────
eval "$(PYTHONNOUSERSITE=1 python3 - "$CONFIG" <<'PY'
import json, sys, shlex
c = json.load(open(sys.argv[1]))
p = c.get("paths", {}); e = c.get("environment", {})
a = c.get("audio_server", {}); comp = c.get("components", {}); act = c.get("active", {})
def q(k, v): print(f'{k}={shlex.quote(str(v if v is not None else ""))}')
q("CF_BASE",      p.get("voicebm_base", ""))
q("CF_PYBIN",     e.get("python_bin") or p.get("python_bin", ""))
q("CF_CONDA",     e.get("conda_path") or p.get("conda_path", ""))
q("CF_SHERPABIN", p.get("sherpa_bin", ""))
q("CF_ACTIVE",    "1" if comp.get("active") else "0")
q("CF_ASR",       act.get("asr_container", ""))
PY
)"

[[ -n "$CF_BASE"  ]] || die "config.json is missing paths.voicebm_base"
[[ -n "$CF_PYBIN" ]] || die "config.json is missing the interpreter (environment.python_bin)"
[[ -x "$CF_PYBIN" ]] || warn "interpreter $CF_PYBIN is not executable yet — services may not start until the environment is in place"
CF_SHERPABIN="${CF_SHERPABIN:-$USER_HOME/.local/bin/sherpa_embed.py}"
WORKER_DIR="$(dirname "$CF_SHERPABIN")"

head "VoiceBM global deploy"
ok "config      : $CONFIG"
ok "install dir : $CF_BASE"
ok "interpreter : $CF_PYBIN"
ok "workers ->  : $WORKER_DIR"
ok "run as user : $DEPLOY_USER"

# ── the rewrite: shipped /home/user generics -> real values from config ─────
# Order matters: most-specific paths first, bare home last.
rewrite() {  # rewrite <file>
  sed -i \
    -e "s#/home/user/miniforge3/envs/vb/bin/python3#${CF_PYBIN}#g" \
    -e "s#/home/user/miniforge3/envs/vb/bin/python#${CF_PYBIN}#g" \
    -e "s#source /home/user/miniforge3/etc/profile.d/conda.sh#:#g" \
    -e "s#conda activate vb#:#g" \
    -e "s#/home/user/.local/bin#${WORKER_DIR}#g" \
    -e "s#/home/user/voicebm#${CF_BASE}#g" \
    -e "s#/home/user/miniforge3#${CF_CONDA:-$USER_HOME/miniforge3}#g" \
    -e "s#/home/user#${USER_HOME}#g" \
    "$1"
}

# ── 1. directory skeleton (owned by the deploy user) ────────────────────────
head "1. Directories"
install -d -o "$DEPLOY_USER" -g "$DEPLOY_USER" \
  "$CF_BASE" "$CF_BASE/bin" "$CF_BASE/meta" "$CF_BASE/out" \
  "$CF_BASE/recordings" "$CF_BASE/embeddings" "$CF_BASE/enroll" "$CF_BASE/pending_active" \
  "$WORKER_DIR"
ok "base tree under $CF_BASE"

# ── 2. engine files ─────────────────────────────────────────────────────────
# voicebm_config.py + voicebm_dashboard.py sit at the base ROOT (every service
# adds the base to sys.path and imports voicebm_config from there). The workers
# go to the worker dir. Everything else goes in bin/.
head "2. Engine"
for f in "$PKG_ROOT"/bin/*; do
  b="$(basename "$f")"
  case "$b" in
    sherpa_embed.py|ser_worker.py)          continue ;;
    voicebm_config.py|voicebm_dashboard.py) dst="$CF_BASE/$b" ;;
    *)                                      dst="$CF_BASE/bin/$b" ;;
  esac
  install -m 0755 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$f" "$dst"
  rewrite "$dst"
done
ok "engine -> $CF_BASE  (config + dashboard at root, scripts in bin/)"

# ── 3. workers ──────────────────────────────────────────────────────────────
head "3. Workers"
install -m 0755 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$PKG_ROOT/bin/sherpa_embed.py" "$CF_SHERPABIN"; rewrite "$CF_SHERPABIN"
install -m 0755 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$PKG_ROOT/bin/ser_worker.py"   "$WORKER_DIR/ser_worker.py"; rewrite "$WORKER_DIR/ser_worker.py"
ok "sherpa_embed.py + ser_worker.py -> $WORKER_DIR"

# ── 4. config.json -> base root (where voicebm_config.py reads it) ──────────
head "4. Config"
install -m 0644 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$CONFIG" "$CF_BASE/config.json"
ok "config.json -> $CF_BASE/config.json"

# ── 5. systemd units ────────────────────────────────────────────────────────
head "5. Services"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
INSTALLED_UNITS=(); installed=0; skipped=0
for s in "$PKG_ROOT"/services/*.service; do
  b="$(basename "$s")"
  cp "$s" "$TMP/$b"
  rewrite "$TMP/$b"
  # Each unit keeps the interpreter it was authored with: rewrite() above already
  # substituted your configured interpreter (config.json) wherever the generic
  # placeholder appeared, and units written against /usr/bin/python3 stay there.
  # Where that interpreter lives — base system, a venv, or a conda env — is your
  # config's call, not this script's.
  sed -i -e "s#^User=user\$#User=${DEPLOY_USER}#" -e "s#^Group=user\$#Group=${DEPLOY_USER}#" "$TMP/$b"
  # Skip any unit whose interpreter isn't present (e.g. an external proxy that
  # ships pointed at its own venv) so it can't wedge the install.
  binpath="$(awk -F= '/^ExecStart=/{print $2; exit}' "$TMP/$b" | awk '{print $1}')"
  if [[ -n "$binpath" && "$binpath" != "/usr/bin/python3" && ! -x "$binpath" ]]; then
    warn "skip $b — interpreter '$binpath' not present (external/optional component)"
    skipped=$((skipped+1)); continue
  fi
  install -m 0644 "$TMP/$b" "/etc/systemd/system/$b"
  INSTALLED_UNITS+=("$b"); installed=$((installed+1))
done
install -m 0644 "$PKG_ROOT/services/voicebm.target" "/etc/systemd/system/voicebm.target"
# timers (e.g. periodic cleanup) install alongside their service
TIMERS=()
for t in "$PKG_ROOT"/services/*.timer; do
  [[ -e "$t" ]] || continue
  tb="$(basename "$t")"
  install -m 0644 "$t" "/etc/systemd/system/$tb"
  TIMERS+=("$tb")
done
ok "installed $installed unit(s), ${#TIMERS[@]} timer(s), skipped $skipped"
systemctl daemon-reload
ok "daemon-reload"

# ── 6. ASR handler (active only; copy into the existing container) ──────────
if [[ "$CF_ACTIVE" == "1" ]]; then
  head "6. ASR handler"
  if [[ -n "$CF_ASR" && -x "$SCRIPT_DIR/deploy_handler.sh" ]]; then
    if bash "$SCRIPT_DIR/deploy_handler.sh" "$CONFIG" "$CF_ASR"; then
      ok "handler.py deployed into '$CF_ASR'"
    else
      warn "handler deploy reported a problem — re-run scripts/deploy_handler.sh once the container is up"
    fi
  else
    warn "active is enabled but no asr_container is set in config.json — deploy the handler later with scripts/deploy_handler.sh"
  fi
fi

# ── 7. the guide (copy + try to open) ───────────────────────────────────────
head "7. Guide"
GUIDE_SRC="$PKG_ROOT/VoiceBM_Guide.html"
if [[ -f "$GUIDE_SRC" ]]; then
  install -m 0644 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$GUIDE_SRC" "$CF_BASE/VoiceBM_Guide.html"
  ok "guide -> $CF_BASE/VoiceBM_Guide.html"
  if command -v xdg-open >/dev/null 2>&1 && [[ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]]; then
    sudo -u "$DEPLOY_USER" xdg-open "$CF_BASE/VoiceBM_Guide.html" >/dev/null 2>&1 || true
  fi
  printf '\n  %bOpen this in a browser to get started — worth a bookmark:%b\n  file://%s\n' "$C_Y" "$C_N" "$CF_BASE/VoiceBM_Guide.html"
fi

# ── 8. enable + start ───────────────────────────────────────────────────────
head "8. Start"
if [[ ${#INSTALLED_UNITS[@]} -gt 0 ]]; then
  systemctl enable "${INSTALLED_UNITS[@]}" voicebm.target >/dev/null 2>&1 || true
fi
if [[ ${#TIMERS[@]} -gt 0 ]]; then
  systemctl enable --now "${TIMERS[@]}" >/dev/null 2>&1 || true
fi
systemctl start voicebm.target || warn "voicebm.target did not start cleanly — check: systemctl status voicebm.target"
ok "voicebm.target started"

head "Done"
printf '  Check status : %bsystemctl status voicebm.target%b\n' "$C_Y" "$C_N"
printf '  Live logs    : %bjournalctl -u voicebm-stt.service -f%b\n' "$C_Y" "$C_N"
[[ "$CF_ACTIVE" == "1" ]] && printf '  Passive nodes: %bsudo ./scripts/replicate_node.sh <node_id>%b   (one per node)\n' "$C_Y" "$C_N"
echo
