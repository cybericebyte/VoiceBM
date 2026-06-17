#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# VoiceBM — 1.0 -> 2.0 upgrade
# -----------------------------------------------------------------------------
# Conservative, reversible upgrade:
#   1. Backs up the existing install (code + units + config) to a timestamped
#      archive BEFORE changing anything.
#   2. Additively merges the keys 2.0 introduces into your existing config.json
#      (the active lead-trim, gallery cap, embed timeout, and any ambient/vad
#      blocks) WITHOUT overwriting values you already set.
#   3. Re-runs the global deploy, which lays the 2.0 code over the top.
#
# Your data is never touched: the deploy writes code, config, workers, and
# units — it does not write recordings/, embeddings/, enroll/, or meta/, so
# enrolled voiceprints and galleries carry straight over.
#
# Run with sudo. Point it at your existing config.json:
#     sudo ./scripts/upgrade_v1_to_v2.sh /path/to/your/voicebm/config.json
# (defaults to ./config.json next to the package if you omit the path).
# =============================================================================

C_G=$'\033[0;32m'; C_Y=$'\033[1;33m'; C_R=$'\033[0;31m'; C_N=$'\033[0m'
ok()   { printf '  %bOK%b  %s\n' "$C_G" "$C_N" "$*"; }
warn() { printf '  %b!!%b  %s\n' "$C_Y" "$C_N" "$*"; }
die()  { printf '  %bXX%b  %s\n' "$C_R" "$C_N" "$*" >&2; exit 1; }
head() { printf '\n== %s ==\n' "$*"; }

[[ $EUID -eq 0 ]] || die "Run with sudo — re-deploying systemd units needs root."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKG_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIG="${1:-$PKG_ROOT/config.json}"
[[ -f "$CONFIG" ]] || die "config.json not found at $CONFIG — pass the path to your existing one: sudo ./scripts/upgrade_v1_to_v2.sh /path/to/config.json"

DEPLOY_USER="${SUDO_USER:-$(id -un)}"
USER_HOME="$(getent passwd "$DEPLOY_USER" | cut -d: -f6)"; [[ -n "$USER_HOME" ]] || USER_HOME="/home/$DEPLOY_USER"

# base + interpreter the existing config points at
eval "$(PYTHONNOUSERSITE=1 python3 - "$CONFIG" <<'PY'
import json, sys, shlex
c = json.load(open(sys.argv[1]))
p = c.get("paths", {}); e = c.get("environment", {})
def q(k, v): print(f'{k}={shlex.quote(str(v or ""))}')
q("CF_BASE",  p.get("voicebm_base", ""))
q("CF_PYBIN", e.get("python_bin") or p.get("python_bin", ""))
PY
)"
[[ -n "$CF_BASE" ]] || die "config.json has no paths.voicebm_base — can't locate the existing install."

head "VoiceBM 1.0 -> 2.0 upgrade"
ok "config      : $CONFIG"
ok "install dir : $CF_BASE"

# ── 1. backup ───────────────────────────────────────────────────────────────
head "1. Backup (before any change)"
STAMP="$(date +%Y%m%d-%H%M%S)"
BK="$USER_HOME/voicebm_pre2.0_backup_${STAMP}.tar.gz"
TMPL="$(mktemp)"; trap 'rm -f "$TMPL"' EXIT
{
  # code + config at the base (NOT the big data dirs)
  [[ -d "$CF_BASE/bin" ]]         && find "$CF_BASE/bin" -maxdepth 1 -type f
  find "$CF_BASE" -maxdepth 1 -type f \( -name '*.py' -o -name 'config.json' \) 2>/dev/null
  # installed units
  ls /etc/systemd/system/voicebm-*.service /etc/systemd/system/voicebm-*.timer /etc/systemd/system/voicebm.target 2>/dev/null
} > "$TMPL" || true
if [[ -s "$TMPL" ]]; then
  tar czf "$BK" --ignore-failed-read -T "$TMPL" 2>/dev/null || true
  chown "$DEPLOY_USER:$DEPLOY_USER" "$BK" 2>/dev/null || true
  ok "backed up code + units + config -> $BK"
else
  warn "found no existing files to back up at $CF_BASE — continuing (treating as a fresh layout)"
fi

# ── 2. additive config merge (never overwrites existing values) ─────────────
head "2. Config — add 2.0 keys (keeping yours)"
PYTHONNOUSERSITE=1 python3 - "$CONFIG" <<'PY'
import json, sys
path = sys.argv[1]
c = json.load(open(path))
added = []

def ensure(d, key, value):
    if key not in d:
        d[key] = value
        added.append(key)

comp = c.get("components", {})

# 2.0 active tunables
if comp.get("active", True):
    vb = c.setdefault("voicebm", {})
    for k, v in {"gallery_max": 75, "current_lead_trim_ms": 900, "embed_timeout_s": 30}.items():
        if k not in vb:
            vb[k] = v; added.append(f"voicebm.{k}")

# passive VAD block
if comp.get("passive", False):
    vad = c.setdefault("vad", {})
    for k, v in {"speech_threshold": 0.6, "min_speech_ratio": 0.5, "min_speech_duration": 0.8}.items():
        if k not in vad:
            vad[k] = v; added.append(f"vad.{k}")

# ambient blocks
if comp.get("ambient", False):
    th = c.setdefault("thresholds", {})
    for k, v in {"ambient_context": 0.18, "ambient_margin": 0.05}.items():
        if k not in th:
            th[k] = v; added.append(f"thresholds.{k}")
    amb = c.setdefault("ambient", {})
    for k, v in {"cycle_s": 30, "mode": "attention", "ping_timeout_s": 5}.items():
        if k not in amb:
            amb[k] = v; added.append(f"ambient.{k}")

if added:
    json.dump(c, open(path, "w"), indent=2)
    print("  added: " + ", ".join(added))
else:
    print("  nothing to add — config already carries the 2.0 keys")

# warn (don't fail) on prerequisites the deploy needs
miss = []
if not (c.get("environment", {}).get("python_bin") or c.get("paths", {}).get("python_bin")):
    miss.append("environment.python_bin")
if not c.get("paths", {}).get("voicebm_base"):
    miss.append("paths.voicebm_base")
if comp.get("active", True) and not c.get("active", {}).get("asr_container"):
    miss.append("active.asr_container (handler step will be skipped until set)")
if miss:
    print("  NOTE: config is missing -> " + "; ".join(miss))
    print("        if the interpreter/base is missing, run setup_voicebm.sh to regenerate before deploying.")
PY
ok "config merge complete"

[[ -n "$CF_PYBIN" && -x "$CF_PYBIN" ]] || warn "interpreter not resolvable yet ($CF_PYBIN) — if this is a new box, run setup_voicebm.sh first"

# ── 3. redeploy 2.0 over the top ────────────────────────────────────────────
head "3. Deploy 2.0"
DEPLOY="$SCRIPT_DIR/deploy_global_services.sh"
[[ -x "$DEPLOY" ]] || die "deploy_global_services.sh not found/executable at $DEPLOY"
bash "$DEPLOY" "$CONFIG"

head "Upgrade complete"
ok "2.0 is deployed; your enrollments and galleries were left in place"
printf '  Rollback if needed: stop voicebm.target, restore from %b%s%b, reload systemd.\n' "$C_Y" "$BK" "$C_N"
printf '  Per-node passive services: re-run %bsudo ./scripts/replicate_node.sh <node_id>%b if your units changed.\n' "$C_Y" "$C_N"
echo
