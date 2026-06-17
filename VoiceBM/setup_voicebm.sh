#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# VoiceBM 2.0 — Setup Wizard
# =============================================================================
# VoiceBM is a system orchestrator. The compute is a sliver (one embedding, one
# cosine compare); the real work is wiring the pieces together and presenting
# that state up into Home Assistant / the dashboard. This wizard lays that
# orchestration down against a FIXED baseline, then hands config.json to the
# render/deploy engine.
#
#   Navigation: at ANY prompt, type  b = back a step   q = quit
#   Back returns to the start of the previous section; your answers are kept
#   as defaults, so re-walking a section is just pressing enter.
#
#   Rules baked in:
#     - Nothing installed/created/changed without a yes.
#     - System and site packages are NEVER touched. No --break-system-packages.
#     - We install OUR baseline to defaults only. We never relocate a package
#       or pass a custom install prefix. Found-elsewhere we wire to; we do not
#       move it. Anything outside that is the user's customization, out of scope.
#     - conda is OPTIONAL — a question, never auto-created.
#     - Path-agnostic. Defaults under the running user's home. No hardcoded user.
#
#   Run as your normal user (NOT root). Provisioning happens in your space; the
#   wizard uses sudo only at the final systemd deploy.
# =============================================================================

# ----------------------------------------------------------------------------
# Baseline resources (the sources we use). The installer pulls THESE — period.
# ----------------------------------------------------------------------------
MINIFORGE_URL_BASE="https://github.com/conda-forge/miniforge/releases/latest/download"
TITANET_MODEL_URL="https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/nemo_en_titanet_small.onnx"

PIP_FOUNDATION=( "paho-mqtt" "numpy" "sherpa-onnx" )
PIP_EXTRA_WATCHDOG=( "watchdog" )
PIP_BRIDGE=( "fastapi" "uvicorn" "soundfile" "requests" )
PIP_AMBIENT=( "torch" "transformers" "numpy" )
PIP_EMOTE=( "torch" "soundfile" "funasr" )

HF_MODEL_AMBIENT="MIT/ast-finetuned-audioset-10-10-0.4593"
HF_MODEL_EMOTE="FunAudioLLM/SenseVoiceSmall"

WHEEL_CACHE="${WHEEL_CACHE:-}"

NAV_BACK=10
NAV_QUIT=20

# ----------------------------------------------------------------------------
# Chrome -> STDERR so $(...) captures stay clean.
# ----------------------------------------------------------------------------
if [[ -t 2 ]]; then
  C_R='\033[0;31m'; C_G='\033[0;32m'; C_Y='\033[1;33m'; C_B='\033[0;36m'; C_D='\033[2m'; C_N='\033[0m'
else
  C_R=''; C_G=''; C_Y=''; C_B=''; C_D=''; C_N=''
fi
hr()   { printf '%b\n' "${C_D}--------------------------------------------------------------${C_N}" >&2; }
head() { printf '\n%b\n' "${C_B}== $* ==${C_N}" >&2; }
say()  { printf '%b\n' "$*" >&2; }
ok()   { printf '%b\n' "  ${C_G}OK${C_N}  $*" >&2; }
warn() { printf '%b\n' "  ${C_Y}!! ${C_N} $*" >&2; }
err()  { printf '%b\n' "  ${C_R}XX${C_N}  $*" >&2; }
die()  { err "$*"; exit 1; }

NAV_HINT="${C_D}(b=back q=quit)${C_N}"

# ----------------------------------------------------------------------------
# Nav-aware prompts. Each SETS a named var and RETURNS 0 / NAV_BACK / NAV_QUIT.
# Callers propagate with:  nav_read VAR "prompt" "default" || return $?
# ----------------------------------------------------------------------------
_nav_token() {                # echoes "back"/"quit"/"" for a reply
  case "$1" in
    '<'|b|B|back|Back|BACK) echo back ;;
    q|Q|quit|Quit|QUIT)     echo quit ;;
    *)                      echo "" ;;
  esac
}
nav_read() {
  local __var="$1" prompt="$2" default="${3:-}" reply hint tok
  [[ -n "$default" ]] && hint=" [${default}]" || hint=""
  read -rp "$(printf '%b' "  ${C_B}?${C_N} ${prompt}${hint} ${NAV_HINT}: ")" reply || true
  tok="$(_nav_token "$reply")"
  [[ "$tok" == back ]] && return "$NAV_BACK"
  [[ "$tok" == quit ]] && return "$NAV_QUIT"
  [[ -z "$reply" ]] && reply="$default"
  printf -v "$__var" '%s' "$reply"
  return 0
}
nav_required() {
  local __var="$1" prompt="$2" reply tok
  while :; do
    read -rp "$(printf '%b' "  ${C_B}?${C_N} ${prompt} ${NAV_HINT}: ")" reply || true
    tok="$(_nav_token "$reply")"
    [[ "$tok" == back ]] && return "$NAV_BACK"
    [[ "$tok" == quit ]] && return "$NAV_QUIT"
    [[ -n "$reply" ]] && { printf -v "$__var" '%s' "$reply"; return 0; }
    warn "Required — type a value, or b to go back."
  done
}
nav_secret() {
  local __var="$1" prompt="$2" reply tok
  read -rsp "$(printf '%b' "  ${C_B}?${C_N} ${prompt} ${NAV_HINT}: ")" reply || true
  printf '\n' >&2
  tok="$(_nav_token "$reply")"
  [[ "$tok" == back ]] && return "$NAV_BACK"
  [[ "$tok" == quit ]] && return "$NAV_QUIT"
  printf -v "$__var" '%s' "$reply"
  return 0
}
nav_yn() {                    # sets named var to 1/0
  local __var="$1" prompt="$2" default="${3:-n}" reply hint tok
  [[ "$default" == "y" ]] && hint="[Y/n]" || hint="[y/N]"
  read -rp "$(printf '%b' "  ${C_B}?${C_N} ${prompt} ${hint} ${NAV_HINT}: ")" reply || true
  tok="$(_nav_token "$reply")"
  [[ "$tok" == back ]] && return "$NAV_BACK"
  [[ "$tok" == quit ]] && return "$NAV_QUIT"
  [[ -z "$reply" ]] && reply="$default"
  if [[ "$reply" =~ ^[Yy] ]]; then printf -v "$__var" '%s' 1; else printf -v "$__var" '%s' 0; fi
  return 0
}
confirm() {                   # terminal yes/no (no nav) for the deploy tail
  local p="$1" d="${2:-n}" r h
  [[ "$d" == y ]] && h="[Y/n]" || h="[y/N]"
  read -rp "$(printf '%b' "  ${C_B}?${C_N} ${p} ${h}: ")" r || true
  r="${r:-$d}"; [[ "$r" =~ ^[Yy] ]]
}

# ----------------------------------------------------------------------------
# Detection.
# ----------------------------------------------------------------------------
have()       { command -v "$1" >/dev/null 2>&1; }
arch_tag()   { uname -m; }
ram_mb()     { awk '/MemTotal/{print int($2/1024)}' /proc/meminfo 2>/dev/null || echo 0; }
disk_mb()    { local p="$1"; while [[ ! -d "$p" && "$p" != "/" ]]; do p="$(dirname "$p")"; done
               df -Pm "$p" 2>/dev/null | awk 'NR==2{print $4}' || echo 0; }
py_has_mod() { "$1" -c "import importlib,sys; sys.exit(0 if importlib.util.find_spec('$2') else 1)" 2>/dev/null; }
docker_has() { have docker && docker ps -a --format '{{.Names}}' 2>/dev/null | grep -qx "$1"; }

# ----------------------------------------------------------------------------
# State.
# ----------------------------------------------------------------------------
WANT_ACTIVE=0; WANT_PASSIVE=0; WANT_AMBIENT=0; WANT_EMOTE=0
INSTALL_USER="${SUDO_USER:-$(id -un)}"
USER_HOME="$(getent passwd "$INSTALL_USER" | cut -d: -f6)"; USER_HOME="${USER_HOME:-$HOME}"
ENV_TYPE=""; ENV_CHOICE=""; CONDA_PATH=""; ENV_NAME=""; VENV_PATH=""
VB_PYTHON=""; VB_PIP=""
VOICEBM_BASE=""; SHERPA_BIN=""; SHERPA_MODEL=""
MQTT_BROKER=""; MQTT_PORT=""; MQTT_USER=""; MQTT_PASS=""
HA_HOST=""; VB_HOST=""; AUDIO_HOST=""; AUDIO_PORT=""
ASR_CONTAINER=""; CONFIG_PATH=""; VOICEBM_BASE_DEFAULT=""
THR_PASSIVE="0.22"; THR_ACTIVE="0.50"; THR_AMB_CTX="0.18"; THR_AMB_MARGIN="0.05"
NODES_TMP="$(mktemp)"; trap 'rm -f "$NODES_TMP"' EXIT
NODE_COUNT=0

# ============================================================================
intro() {
  head "VoiceBM 2.0 Setup Wizard"
  say "  Builds ${C_B}config.json${C_N} from your answers, then deploys what you chose."
  say "  ${C_D}Installs our baseline. Nothing changed without your yes.${C_N}"
  say "  ${C_D}At any prompt: ${C_N}${C_B}b${C_N}${C_D} = back a step, ${C_N}${C_B}q${C_N}${C_D} = quit.${C_N}"
  hr
  ok "Install user : ${INSTALL_USER}  (home: ${USER_HOME})"
  ok "Architecture : $(arch_tag)"
  if [[ "$(id -u)" -eq 0 ]]; then
    warn "Running as root. conda/venv/pip and downloads should be owned by your user."
    warn "Re-run as your normal user; the wizard sudo's only for the systemd deploy."
    confirm "Continue anyway?" "n" || exit 0
  fi
}

# ---- PHASE 1 ---------------------------------------------------------------
select_components() {
  head "1. What do you want to install?"
  say "  Any combination. They're independent — except emote, which rides active."
  local da dp dab de _add
  while :; do
    da=$([[ $WANT_ACTIVE  -eq 1 ]] && echo y || echo n)
    dp=$([[ $WANT_PASSIVE -eq 1 ]] && echo y || echo n)
    dab=$([[ $WANT_AMBIENT -eq 1 ]] && echo y || echo n)
    de=$([[ $WANT_EMOTE   -eq 1 ]] && echo y || echo n)
    say ""
    nav_yn WANT_ACTIVE  "Install VoiceBM ${C_B}Active${C_N}  (live STT identity + injection)?"         "$da"  || return $?
    nav_yn WANT_PASSIVE "Install VoiceBM ${C_B}Passive${C_N} (continuous per-node background scoring)?" "$dp"  || return $?
    nav_yn WANT_AMBIENT "Install VoiceBM ${C_B}Ambient${C_N} (audio-event detection, 1.0 beta)?"       "$dab" || return $?
    nav_yn WANT_EMOTE   "Install VoiceBM ${C_B}Emote${C_N}   (speech-emotion on active, 1.0 beta)?"    "$de"  || return $?
    if [[ $WANT_EMOTE -eq 1 && $WANT_ACTIVE -eq 0 ]]; then
      say ""; warn "Emote is a plug-in inside the Active pipeline. It needs Active."
      nav_yn _add "Add Active so Emote can be installed?" "y" || return $?
      if [[ $_add -eq 1 ]]; then WANT_ACTIVE=1; else warn "Skipping Emote."; WANT_EMOTE=0; fi
    fi
    [[ $((WANT_ACTIVE+WANT_PASSIVE+WANT_AMBIENT+WANT_EMOTE)) -gt 0 ]] && break
    warn "Nothing selected — pick at least one (or q to quit)."
  done
  say ""
  ok "Selected:$([[ $WANT_ACTIVE  -eq 1 ]] && printf ' active')$([[ $WANT_PASSIVE -eq 1 ]] && printf ' passive')$([[ $WANT_AMBIENT -eq 1 ]] && printf ' ambient')$([[ $WANT_EMOTE   -eq 1 ]] && printf ' emote')"
  return 0
}

# ---- PHASE 2 ---------------------------------------------------------------
footprint() {
  head "2. Baseline footprint for your selection"
  say "  The compute is a sliver — one embedding, one compare. Mostly orchestration."
  say ""
  say "  ${C_B}Identity core${C_N} (active or passive): CPU only, no GPU."
  say "    ~200 MB working, ~70 ms/clip. Mini PC / NUC / Pi 4-5 class, x86_64 or"
  say "    ARM64, Python 3.9+. TitaNet model ~40 MB on disk."
  [[ $WANT_ACTIVE  -eq 1 ]] && { \
    say "  ${C_B}Active${C_N}: STT (ONNX ASR container) is the heavy piece (~2.6 GB resident)."; \
    say "    VoiceBM does identity, not transcription — STT can live on another box."; }
  [[ $WANT_PASSIVE -eq 1 ]] && say "  ${C_B}Passive${C_N}: ffmpeg per node. Node hardware is whatever serves the RTSP audio."
  [[ $WANT_AMBIENT -eq 1 ]] && say "  ${C_B}Ambient${C_N}: our baseline audio-tagging model on CPU; ffmpeg per node."
  [[ $WANT_EMOTE   -eq 1 ]] && say "  ${C_B}Emote${C_N}: our baseline emotion model on CPU, inside the active pipeline."
  hr
  ok "This machine: $(arch_tag), $(ram_mb) MB RAM, $(( $(disk_mb "$USER_HOME") / 1024 )) GB free at ${USER_HOME}"
  if [[ $WANT_PASSIVE -eq 1 || $WANT_AMBIENT -eq 1 ]]; then
    if have ffmpeg; then ok "ffmpeg present"
    else warn "ffmpeg not found — install it with your OS package manager (we don't touch system packages)."; fi
  fi
  say ""
  local _go
  nav_yn _go "Proceed?" "y" || return $?
  [[ $_go -eq 1 ]] || return "$NAV_BACK"
  return 0
}

# ---- PHASE 3 ---------------------------------------------------------------
gather_global() {
  head "3. Where to install + how to reach things"

  nav_read VOICEBM_BASE "Install directory" "$VOICEBM_BASE" || return $?
  nav_read SHERPA_BIN   "sherpa_embed.py path" "$SHERPA_BIN" || return $?
  nav_read SHERPA_MODEL "TitaNet model path" "$SHERPA_MODEL" || return $?

  if [[ ! -d "$VOICEBM_BASE" ]]; then
    local _mk
    nav_yn _mk "Create $VOICEBM_BASE now?" "y" || return $?
    if [[ $_mk -eq 1 ]]; then
      mkdir -p "$VOICEBM_BASE"/{bin,enroll,recordings,embeddings,meta,out,pending_active}
      ok "Created $VOICEBM_BASE and its subtree"
    fi
  fi

  say ""
  say "  ${C_B}MQTT broker${C_N} (VoiceBM publishes everything here):"
  nav_required MQTT_BROKER "Broker host/IP" || return $?
  nav_read MQTT_PORT "Broker port" "$MQTT_PORT" || return $?
  nav_read MQTT_USER "MQTT username" "$MQTT_USER" || return $?
  if [[ -n "$MQTT_PASS" ]]; then
    local _keep
    nav_yn _keep "Keep the MQTT password already entered?" "y" || return $?
    [[ $_keep -eq 1 ]] || { nav_secret MQTT_PASS "MQTT password" || return $?; }
  else
    nav_secret MQTT_PASS "MQTT password" || return $?
  fi

  say ""
  nav_read HA_HOST "Home Assistant host/IP" "${HA_HOST:-$MQTT_BROKER}" || return $?
  nav_read VB_HOST "This VoiceBM host's IP (for audio URLs)" "${VB_HOST:-$(hostname -I 2>/dev/null | awk '{print $1}')}" || return $?
  nav_read AUDIO_HOST "Audio HTTP server bind host" "${AUDIO_HOST:-$VB_HOST}" || return $?
  nav_read AUDIO_PORT "Audio HTTP server port" "$AUDIO_PORT" || return $?

  say ""
  say "  ${C_B}Match thresholds${C_N} (enter to accept):"
  nav_read THR_PASSIVE "passive threshold" "$THR_PASSIVE" || return $?
  nav_read THR_ACTIVE  "active threshold" "$THR_ACTIVE" || return $?
  if [[ $WANT_AMBIENT -eq 1 ]]; then
    nav_read THR_AMB_CTX    "ambient context threshold" "$THR_AMB_CTX" || return $?
    nav_read THR_AMB_MARGIN "ambient margin" "$THR_AMB_MARGIN" || return $?
  fi
  return 0
}

# ---- PHASE 4 ---------------------------------------------------------------
choose_environment() {
  head "4. How should VoiceBM's Python run?"
  say "  conda is optional. We only ever install to a place that's ours (a conda"
  say "  env or a venv) or wire to an interpreter you already manage — never system."
  local choice rc
  while :; do
    say ""
    nav_read choice "Run under: [1] conda  [2] venv  [3] an interpreter you manage" "${ENV_CHOICE:-2}" || return $?
    ENV_CHOICE="$choice"
    case "$choice" in
      1) ENV_TYPE="conda";  if env_conda;    then break; else rc=$?; [[ $rc -eq $NAV_BACK ]] && continue || return "$rc"; fi ;;
      2) ENV_TYPE="venv";   if env_venv;     then break; else rc=$?; [[ $rc -eq $NAV_BACK ]] && continue || return "$rc"; fi ;;
      3) ENV_TYPE="system"; if env_existing; then break; else rc=$?; [[ $rc -eq $NAV_BACK ]] && continue || return "$rc"; fi ;;
      *) warn "Pick 1, 2, or 3 (or b to go back a section)." ;;
    esac
  done
  [[ -n "$VB_PYTHON" ]] || die "No interpreter resolved."
  ok "VoiceBM will run under: ${VB_PYTHON}"
  return 0
}

env_conda() {
  local found="" _use _inst
  for c in "$USER_HOME/miniforge3" "$USER_HOME/miniconda3" "$USER_HOME/anaconda3" /opt/miniforge3; do
    [[ -x "$c/bin/conda" ]] && { found="$c"; break; }
  done
  [[ -z "$found" ]] && have conda && found="$(conda info --base 2>/dev/null || true)"

  if [[ -n "$found" ]]; then
    ok "Found conda at: $found"
    nav_yn _use "Use this conda?" "y" || return $?
    [[ $_use -eq 1 ]] || return "$NAV_BACK"
    CONDA_PATH="$found"
  else
    warn "No conda found."
    nav_yn _inst "Install Miniforge to its default in your home?" "n" || return $?
    [[ $_inst -eq 1 ]] || return "$NAV_BACK"
    CONDA_PATH="$USER_HOME/miniforge3"
    install_miniforge "$CONDA_PATH"
  fi

  nav_read ENV_NAME "conda environment name to use/create" "${ENV_NAME:-vb}" || return $?
  if [[ -x "$CONDA_PATH/envs/$ENV_NAME/bin/python3" ]]; then
    ok "Using existing env '$ENV_NAME'."
  else
    local _cr
    nav_yn _cr "Env '$ENV_NAME' does not exist. Create it (python 3.10)?" "y" || return $?
    [[ $_cr -eq 1 ]] || return "$NAV_BACK"
    # shellcheck disable=SC1091
    source "$CONDA_PATH/etc/profile.d/conda.sh"
    conda create -y -n "$ENV_NAME" python=3.10
  fi
  VB_PYTHON="$CONDA_PATH/envs/$ENV_NAME/bin/python3"
  VB_PIP="$CONDA_PATH/envs/$ENV_NAME/bin/pip"
  return 0
}

env_venv() {
  local _cr
  nav_read VENV_PATH "Create venv at" "${VENV_PATH:-$VOICEBM_BASE/.venv}" || return $?
  if [[ -x "$VENV_PATH/bin/python3" ]]; then
    ok "Using existing venv."
  else
    nav_yn _cr "Create venv at $VENV_PATH?" "y" || return $?
    [[ $_cr -eq 1 ]] || return "$NAV_BACK"
    python3 -m venv "$VENV_PATH"
    "$VENV_PATH/bin/pip" install --upgrade pip >/dev/null
  fi
  VB_PYTHON="$VENV_PATH/bin/python3"
  VB_PIP="$VENV_PATH/bin/pip"
  return 0
}

env_existing() {
  warn "Point me at an interpreter that ALREADY has the packages. I won't install"
  warn "into it — you manage its dependencies. (Using one already there is fine;"
  warn "what I won't do is install our deps to a place we don't own.)"
  local p=""
  nav_required p "Path to python interpreter" || return $?
  [[ -x "$p" ]] || { warn "Not executable: $p"; return "$NAV_BACK"; }
  VB_PYTHON="$p"; VB_PIP=""
  return 0
}

install_miniforge() {
  local dest="$1" a tag
  a="$(arch_tag)"
  case "$a" in
    x86_64)  tag="Linux-x86_64" ;;
    aarch64) tag="Linux-aarch64" ;;
    *) die "No Miniforge auto-install for arch $a — install conda yourself, then re-run.";;
  esac
  say "  Downloading Miniforge ($tag)..."
  curl -fsSL "$MINIFORGE_URL_BASE/Miniforge3-${tag}.sh" -o /tmp/miniforge.sh || die "Miniforge download failed."
  bash /tmp/miniforge.sh -b -p "$dest" || die "Miniforge install failed."
  rm -f /tmp/miniforge.sh
  ok "Miniforge installed at $dest (its default layout)"
}

env_pip_install() {
  [[ -z "$VB_PIP" ]] && return 0
  local args=( install )
  [[ -n "$WHEEL_CACHE" && -d "$WHEEL_CACHE" ]] && args+=( --no-index --find-links "$WHEEL_CACHE" )
  PYTHONNOUSERSITE=1 "$VB_PIP" "${args[@]}" "$@"
}

# ---- PHASE 5 ---------------------------------------------------------------
install_components() {
  head "5. Finding and wiring the pieces"
  if [[ $WANT_ACTIVE -eq 1 || $WANT_PASSIVE -eq 1 ]]; then
    wire_pip "identity core" "${PIP_FOUNDATION[@]}" || return $?
    wire_pip "enrollment watcher" "${PIP_EXTRA_WATCHDOG[@]}" || return $?
    wire_sherpa_embed || return $?
    wire_titanet_model || return $?
  fi
  if [[ $WANT_ACTIVE -eq 1 ]]; then
    wire_pip "STT bridge (OpenAI/OpenWebUI compatibility)" "${PIP_BRIDGE[@]}" || return $?
  fi
  if [[ $WANT_AMBIENT -eq 1 ]]; then
    wire_pip "ambient" "${PIP_AMBIENT[@]}" || return $?
    note_hf_model "Ambient" "$HF_MODEL_AMBIENT" || return $?
  fi
  if [[ $WANT_EMOTE -eq 1 ]]; then
    wire_pip "emote" "${PIP_EMOTE[@]}" || return $?
    note_hf_model "Emote" "$HF_MODEL_EMOTE" || return $?
  fi
  [[ $WANT_ACTIVE -eq 1 ]] && { require_asr_container || return $?; }
  return 0
}

wire_pip() {
  local label="$1"; shift
  local pkgs=("$@") missing=() _do _cont
  say "  ${C_B}${label}${C_N} dependencies:"
  for p in "${pkgs[@]}"; do
    local mod="$p"
    case "$p" in paho-mqtt) mod="paho";; sherpa-onnx) mod="sherpa_onnx";; esac
    if py_has_mod "$VB_PYTHON" "$mod"; then ok "$p present (using it)"; else warn "$p not found"; missing+=("$p"); fi
  done
  [[ ${#missing[@]} -eq 0 ]] && return 0
  if [[ -z "$VB_PIP" ]]; then
    err "Missing in your interpreter: ${missing[*]} — you manage it, install these yourself, then re-run."
    nav_yn _cont "Continue anyway?" "n" || return $?
    [[ $_cont -eq 1 ]] || return "$NAV_BACK"
    return 0
  fi
  nav_yn _do "Install into the ${ENV_TYPE} env: ${missing[*]}?" "y" || return $?
  if [[ $_do -eq 1 ]]; then env_pip_install "${missing[@]}"; ok "Installed: ${missing[*]}"
  else warn "Skipped — these services won't start until installed."; fi
  return 0
}

wire_sherpa_embed() {
  local src="" _put
  for cand in "$(dirname "$0")/templates/global/sherpa_embed.py" "$(dirname "$0")/sherpa_embed.py"; do
    [[ -f "$cand" ]] && { src="$cand"; break; }
  done
  if [[ -f "$SHERPA_BIN" ]]; then ok "sherpa_embed.py present at $SHERPA_BIN (using it)"; return 0; fi
  [[ -z "$src" ]] && { warn "sherpa_embed.py ships with the deploy step — placed there."; return 0; }
  nav_yn _put "Place our sherpa_embed.py at $SHERPA_BIN?" "y" || return $?
  if [[ $_put -eq 1 ]]; then
    mkdir -p "$(dirname "$SHERPA_BIN")"; install -m 0755 "$src" "$SHERPA_BIN"; ok "Placed -> $SHERPA_BIN"
  fi
  return 0
}

wire_titanet_model() {
  local _dl
  if [[ -f "$SHERPA_MODEL" ]]; then ok "TitaNet model present (using it)"; return 0; fi
  nav_yn _dl "Download our TitaNet model (~40 MB) to $SHERPA_MODEL?" "y" || return $?
  if [[ $_dl -eq 1 ]]; then
    mkdir -p "$(dirname "$SHERPA_MODEL")"; curl -fL "$TITANET_MODEL_URL" -o "$SHERPA_MODEL" || die "Model download failed."
    ok "Model -> $SHERPA_MODEL"
  else warn "Skipped — embedding won't work until the model is in place."; fi
  return 0
}

note_hf_model() {
  local pillar="$1" mid="$2" _pf
  say "  ${pillar} model ${C_B}${mid}${C_N} downloads from Hugging Face on first inference (its default cache)."
  if [[ -n "$VB_PIP" ]]; then
    nav_yn _pf "Pre-fetch it now instead?" "n" || return $?
    if [[ $_pf -eq 1 ]]; then
      PYTHONNOUSERSITE=1 "$VB_PYTHON" - "$mid" <<'PY' || warn "Pre-fetch skipped (pulls on first run)."
import sys
from huggingface_hub import snapshot_download
snapshot_download(sys.argv[1]); print("ok")
PY
    fi
  fi
  return 0
}

require_asr_container() {
  local _cont
  nav_read ASR_CONTAINER "Name of your ONNX ASR Docker container" "${ASR_CONTAINER:-}" || return $?
  [[ -z "$ASR_CONTAINER" ]] && { warn "No container named — handler step skipped; set it up later."; return 0; }
  if docker_has "$ASR_CONTAINER"; then ok "Found '$ASR_CONTAINER' — handler.py is copied into it at deploy."
  else
    warn "'$ASR_CONTAINER' not found (or docker not accessible)."
    warn "Active copies handler.py into an EXISTING ASR container — it does not build one."
    nav_yn _cont "Continue and wire it later?" "y" || return $?
    [[ $_cont -eq 1 ]] || return "$NAV_BACK"
  fi
  return 0
}

# ---- PHASE 6 ---------------------------------------------------------------
gather_nodes() {
  [[ $WANT_PASSIVE -eq 0 && $WANT_AMBIENT -eq 0 ]] && return 0
  : > "$NODES_TMP"; NODE_COUNT=0          # rebuild fresh on (re)entry
  head "6. Set up your nodes (RTSP audio sources)"
  say "  A node is an RTSP audio feed — not a camera, not a room. Whatever emits it"
  say "  is your business. Each node can feed passive, ambient, or both."
  local _add rc
  while :; do
    say ""
    nav_yn _add "Add a node?" "$([[ $NODE_COUNT -eq 0 ]] && echo y || echo n)" || return $?
    [[ $_add -eq 1 ]] || break
    if add_one_node; then :; else rc=$?; [[ $rc -eq $NAV_BACK ]] && { warn "Node cancelled."; continue; } || return "$rc"; fi
  done
  [[ $NODE_COUNT -eq 0 ]] && warn "No nodes added — add later by re-running or with the node manager."
  return 0
}

add_one_node() {
  local node_id="" friendly rtsp filt rec=0 amb=0 _re
  while :; do
    nav_required node_id "Node id (lowercase, no spaces — e.g. living, front_entry)" || return $?
    node_id="$(printf '%s' "$node_id" | tr '[:upper:] ' '[:lower:]_' | tr -cd 'a-z0-9_')"
    if grep -q "\"node_id\": \"$node_id\"" "$NODES_TMP" 2>/dev/null; then warn "'$node_id' already added."; else break; fi
  done
  nav_read friendly "Friendly name (display + LLM context)" "$(printf '%s' "$node_id" | sed 's/_/ /g' | awk '{for(i=1;i<=NF;i++)$i=toupper(substr($i,1,1))substr($i,2)}1')" || return $?

  while :; do
    nav_required rtsp "RTSP URL" || return $?
    validate_rtsp "$rtsp" && break
    nav_yn _re "Re-enter the URL?" "y" || return $?
    [[ $_re -eq 1 ]] || { warn "Proceeding without audio confirmation."; break; }
  done

  [[ $WANT_PASSIVE -eq 1 ]] && { nav_yn rec "Use this node for ${C_B}passive${C_N} scoring?" "y" || return $?; }
  [[ $WANT_AMBIENT -eq 1 ]] && { nav_yn amb "Use this node for ${C_B}ambient${C_N} detection?" "y" || return $?; }
  [[ $rec -eq 0 && $amb -eq 0 ]] && { warn "Node feeds neither pillar — skipping."; return 0; }

  nav_read filt "ffmpeg audio filter (optional, e.g. highpass=f=80)" "" || return $?

  PYTHONNOUSERSITE=1 python3 - "$node_id" "$friendly" "$rtsp" "$filt" "$rec" "$amb" >>"$NODES_TMP" <<'PY'
import json, sys
nid, friendly, rtsp, filt, rec, amb = sys.argv[1:7]
obj = {"friendly_name": friendly, "rtsp_url": rtsp}
obj["audio_filter"] = filt
if rec == "1": obj["recorder_enabled"] = True
if amb == "1": obj["ambient_enabled"] = True
print(json.dumps({"node_id": nid, "obj": obj}))
PY
  NODE_COUNT=$((NODE_COUNT+1))
  ok "Added '$node_id'$([[ $rec -eq 1 ]] && printf ' [passive]')$([[ $amb -eq 1 ]] && printf ' [ambient]')"
  return 0
}

validate_rtsp() {
  local url="$1"
  have ffprobe || { warn "ffprobe not present — can't validate, accepting as-is."; return 0; }
  say "    checking for an audio track..." >&2
  if ffprobe -v quiet -rtsp_transport tcp -i "$url" -select_streams a -show_streams -print_format json 2>/dev/null \
       | grep -q '"codec_type": "audio"'; then ok "Reachable — audio track confirmed."; return 0; fi
  warn "No audio track confirmed."; return 1
}

# ---- PHASE 7 ---------------------------------------------------------------
build_config() {
  head "7. Building config.json"
  local out _ow; out="$(dirname "$0")/config.json"
  if [[ -f "$out" ]]; then
    nav_yn _ow "config.json exists at $out — overwrite?" "n" || return $?
    if [[ $_ow -ne 1 ]]; then
      warn "Keeping existing $out."
      CONFIG_PATH="$out"; return 0
    fi
  fi
  CONDA_PATH="${CONDA_PATH:-}"

  CFG_OUT="$out" \
  C_VB_BASE="$VOICEBM_BASE" C_SHERPA_BIN="$SHERPA_BIN" C_SHERPA_MODEL="$SHERPA_MODEL" \
  C_ENV_TYPE="$ENV_TYPE" C_CONDA_PATH="$CONDA_PATH" C_ENV_NAME="${ENV_NAME:-}" \
  C_VENV="${VENV_PATH:-}" C_PYBIN="$VB_PYTHON" \
  C_MB="$MQTT_BROKER" C_MP="$MQTT_PORT" C_MU="$MQTT_USER" C_MPW="$MQTT_PASS" \
  C_HA="$HA_HOST" C_VBHOST="$VB_HOST" C_AH="$AUDIO_HOST" C_AP="$AUDIO_PORT" \
  C_TP="$THR_PASSIVE" C_TA="$THR_ACTIVE" C_TAC="$THR_AMB_CTX" C_TAM="$THR_AMB_MARGIN" \
  C_ACTIVE="$WANT_ACTIVE" C_PASSIVE="$WANT_PASSIVE" C_AMBIENT="$WANT_AMBIENT" C_EMOTE="$WANT_EMOTE" \
  C_NODES_FILE="$NODES_TMP" C_ASR="${ASR_CONTAINER:-}" \
  PYTHONNOUSERSITE=1 python3 <<'PY'
import json, os
g = os.environ.get
base = g("C_VB_BASE")
cfg = {
    "mqtt": {"broker": g("C_MB"), "port": int(g("C_MP") or 1883), "user": g("C_MU"), "password": g("C_MPW")},
    "hosts": {"home_assistant": g("C_HA"), "voicebm_host": g("C_VBHOST")},
    "paths": {"voicebm_base": base, "sherpa_bin": g("C_SHERPA_BIN"),
              "sherpa_model": g("C_SHERPA_MODEL"), "conda_path": g("C_CONDA_PATH"), "python_bin": g("C_PYBIN")},
    "environment": {"type": g("C_ENV_TYPE"), "conda_path": g("C_CONDA_PATH"), "env_name": g("C_ENV_NAME"),
                    "venv_path": g("C_VENV"), "python_bin": g("C_PYBIN")},
    "audio_server": {"host": g("C_AH"), "port": int(g("C_AP") or 9090),
                     "base_url": f'http://{g("C_VBHOST")}:{g("C_AP") or 9090}'},
    "components": {"active": g("C_ACTIVE")=="1", "passive": g("C_PASSIVE")=="1",
                   "ambient": g("C_AMBIENT")=="1", "emote": g("C_EMOTE")=="1"},
    "nodes": {},
    "thresholds": {"passive": float(g("C_TP") or 0.22), "active": float(g("C_TA") or 0.50)},
}
nf = g("C_NODES_FILE")
if nf and os.path.exists(nf):
    for line in open(nf):
        line = line.strip()
        if line:
            r = json.loads(line); cfg["nodes"][r["node_id"]] = r["obj"]
if cfg["components"]["active"]:
    cfg["voicebm"] = {"gallery_max": 75, "current_lead_trim_ms": 900, "embed_timeout_s": 30,
                      "inject_identity": True, "transcript_preferred": True}
    cfg["active"] = {"asr_container": g("C_ASR")}
if cfg["components"]["passive"]:
    cfg["vad"] = {"speech_threshold": 0.6, "min_speech_ratio": 0.5, "min_speech_duration": 0.8}
if cfg["components"]["ambient"]:
    cfg["thresholds"]["ambient_context"] = float(g("C_TAC") or 0.18)
    cfg["thresholds"]["ambient_margin"]  = float(g("C_TAM") or 0.05)
    cfg["ambient"] = {"cycle_s": 30, "mode": "attention", "ping_timeout_s": 5}
if cfg["components"]["emote"]:
    cfg["emote"] = {"ser_script": f"{base}/bin/ser_infer.sh", "ser_timeout_s": 60}
with open(g("CFG_OUT"), "w") as f:
    json.dump(cfg, f, indent=2)
print(g("CFG_OUT"))
PY
  CONFIG_PATH="$out"; ok "Wrote $CONFIG_PATH"
  return 0
}

# ---- deploy tail (terminal; no back) ---------------------------------------
deploy_handoff() {
  head "8. Deploy"
  say "  config.json is built. Deployment renders templates into live files and"
  say "  installs the systemd units (this part needs sudo)."
  say ""
  say "    ${C_D}sudo ./scripts/deploy_global_services.sh${C_N}        global services + foundation"
  [[ $WANT_PASSIVE -eq 1 ]] && say "    ${C_D}sudo ./scripts/replicate_node.sh <node_id>${C_N}     per passive node (recorder+embedder+publisher)"
  [[ $WANT_AMBIENT -eq 1 ]] && say "    ambient reads every node with ambient_enabled from config.json — one service."
  [[ $WANT_ACTIVE  -eq 1 ]] && say "    active: handler.py renders from config.json, is copied into '${ASR_CONTAINER:-<container>}', then the host copy is deleted."
  say ""
  if confirm "Run the global deploy now (sudo)?" "n"; then
    local deploy; deploy="$(dirname "$0")/scripts/deploy_global_services.sh"
    [[ -x "$deploy" ]] || die "Deploy script not found/executable at $deploy"
    sudo "$deploy" "$CONFIG_PATH"
  else
    say "  ${C_D}Stopped before deploy. config.json ready at:${C_N} $CONFIG_PATH"
  fi
}

# ============================================================================
# main — the walk, as a back/next/quit state machine
# ============================================================================
main() {
  VOICEBM_BASE_DEFAULT="$USER_HOME/voicebm"
  VOICEBM_BASE="$VOICEBM_BASE_DEFAULT"
  SHERPA_BIN="$USER_HOME/.local/bin/sherpa_embed.py"
  SHERPA_MODEL="$USER_HOME/sherpa_models/nemo_en_titanet_small.onnx"
  MQTT_PORT="1883"; MQTT_USER="mqtt-user"; AUDIO_PORT="9090"

  intro

  local PHASES=( select_components footprint gather_global choose_environment install_components gather_nodes build_config )
  local idx=0 n=${#PHASES[@]} rc
  while (( idx < n )); do
    if "${PHASES[idx]}"; then rc=0; else rc=$?; fi
    case "$rc" in
      0)            idx=$((idx+1)) ;;
      "$NAV_BACK")  if (( idx > 0 )); then idx=$((idx-1)); else say "  ${C_D}(already at the first step)${C_N}"; fi ;;
      "$NAV_QUIT")  say "  ${C_D}Quit — nothing deployed.${C_N}"; exit 0 ;;
      *)            exit "$rc" ;;
    esac
  done

  deploy_handoff
  head "Done"
  ok "config.json: $CONFIG_PATH"
  say ""
  say "  ${C_D}Note: this installed our baseline (Sherpa embedder, ONNX ASR handler, our"
  say "  package versions). The system is designed to let you swap any of those for"
  say "  something else later — that's your customization, and it's out of scope here.${C_N}"
}

main "$@"
