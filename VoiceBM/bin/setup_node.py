#!/usr/bin/env python3
"""
VoiceBM — Passive Node Setup (interactive)
Adds and manages passive recording nodes in config.json -> nodes.

Same idea as setup_ambient.py: this authors its slice of config.json. The main
config (MQTT, broker, audio, thresholds) is already written by the questionnaire;
this only asks the per-node unknowns — node id, RTSP stream + credentials,
optional audio filter — and writes them in. Never overwrites
a node already configured; only appends or modifies.

Base path is derived from this file's own location ({base}/bin/setup_node.py),
so the package is path-agnostic. Override with the VOICEBM_BASE env var if needed.

After saving, run replicate_node.sh <node_id> (printed for you) to build the
recorder + embedder + publisher services for each recorder-enabled node.

Usage: python3 setup_node.py
"""

import json
import sys
import os
import re
import subprocess

# ─────────────────────────────────────────────────────────────────────────────
# Base path — self-located, so this works wherever the package is installed
# ─────────────────────────────────────────────────────────────────────────────
VOICEBM_BASE = os.environ.get('VOICEBM_BASE') or \
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(VOICEBM_BASE, 'config.json')


# ─────────────────────────────────────────────────────────────────────────────
# Permissions check — fail clean before touching anything
# ─────────────────────────────────────────────────────────────────────────────
def check_permissions():
    if not os.path.exists(CONFIG_FILE):
        print(f'ERROR: config.json not found at {CONFIG_FILE}')
        print('Run the main setup first — it builds config.json (MQTT, paths, etc.).')
        sys.exit(1)
    if not os.access(CONFIG_FILE, os.W_OK):
        print(f'ERROR: No write permission on {CONFIG_FILE}')
        sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# Config I/O
# ─────────────────────────────────────────────────────────────────────────────
def load_config():
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)


def save_config(cfg):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(cfg, f, indent=2)
    print(f'\n  config.json saved.')


# ─────────────────────────────────────────────────────────────────────────────
# RTSP validation — quick ffprobe, no file written, 10s timeout
# ─────────────────────────────────────────────────────────────────────────────
def validate_rtsp(rtsp_url):
    print(f'    Validating stream...')
    try:
        result = subprocess.run(
            [
                'ffprobe', '-v', 'quiet',
                '-rtsp_transport', 'tcp',
                '-i', rtsp_url,
                '-show_streams',
                '-select_streams', 'a',
                '-print_format', 'json',
            ],
            capture_output=True,
            timeout=10,
        )
        if result.returncode == 0:
            try:
                data = json.loads(result.stdout.decode('utf-8', errors='replace'))
                if data.get('streams'):
                    print(f'    Stream valid — audio confirmed.')
                    return True
                else:
                    print(f'    Stream reachable but no audio track found.')
                    return False
            except Exception:
                print(f'    Stream reachable.')
                return True
        else:
            err = result.stderr.decode('utf-8', errors='replace').strip()
            lines = [l for l in err.splitlines() if l.strip()]
            hint = lines[-1] if lines else 'no detail available'
            print(f'    Stream unreachable: {hint}')
            return False
    except subprocess.TimeoutExpired:
        print(f'    Timed out — stream did not respond within 10 seconds.')
        return False
    except FileNotFoundError:
        print(f'    ffprobe not found — skipping validation.')
        return True   # can't validate, allow entry


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def slugify(raw):
    s = raw.strip().lower().replace(' ', '_')
    return re.sub(r'[^a-z0-9_]', '', s)


def get_required(prompt):
    while True:
        val = input(f'    {prompt}: ').strip()
        if val:
            return val
        print('    (required — cannot be blank)')


def get_optional(prompt):
    return input(f'    {prompt} (enter to skip): ').strip()


def yes_no(prompt, default=True):
    d = 'Y/n' if default else 'y/N'
    raw = input(f'    {prompt} [{d}]: ').strip().lower()
    if not raw:
        return default
    return raw != 'n' if default else raw == 'y'


# ─────────────────────────────────────────────────────────────────────────────
# Display
# ─────────────────────────────────────────────────────────────────────────────
def show_nodes(cfg):
    nodes = cfg.get('nodes', {})
    if not nodes:
        print('    (none configured yet)')
        return
    for node_id, n in nodes.items():
        rec = 'on' if n.get('recorder_enabled') else 'off'
        amb = 'on' if n.get('ambient_enabled') else 'off'
        print(f'    [{node_id}]  {n.get("friendly_name", node_id)}')
        print(f'         rtsp:     {n.get("rtsp_url", "(none)")}')
        print(f'         filter:   {n.get("audio_filter") or "(none)"}')
        print(f'         recorder: {rec}   ambient: {amb}')


# ─────────────────────────────────────────────────────────────────────────────
# Operations
# ─────────────────────────────────────────────────────────────────────────────
def add_node(cfg):
    print('\n  ── Add Passive Node ───────────────────────────────────')
    nodes = cfg.setdefault('nodes', {})

    while True:
        node_id = slugify(get_required('Node id — lowercase, no spaces e.g. living, front_entry, parking_lot'))
        if not node_id:
            print('    (id became empty after cleanup — try letters/numbers)')
        elif node_id in nodes:
            print(f'    "{node_id}" already exists. Choose a different id (or edit it from the menu).')
        else:
            break

    default_friendly = node_id.replace('_', ' ').title()
    friendly = input(f'    Friendly name (display + LLM context) [{default_friendly}]: ').strip() or default_friendly

    while True:
        rtsp_url = get_required('RTSP URL (include credentials if the stream needs them)')
        if validate_rtsp(rtsp_url):
            break
        if not yes_no('Re-enter URL?', default=True):
            print('    Proceeding without validation confirmation.')
            break

    audio_filter = get_optional('ffmpeg audio filter e.g. highpass=f=80')

    recorder_enabled = yes_no('Use this node for passive recording (recorder/embedder/publisher)?', default=True)
    ambient_enabled = yes_no('Also use this node for ambient detection?', default=False)

    node = {
        'friendly_name':   friendly,
        'rtsp_url':        rtsp_url,
        'recorder_enabled': recorder_enabled,
        'ambient_enabled':  ambient_enabled,
        'audio_filter':     audio_filter if audio_filter else '',
    }
    nodes[node_id] = node
    print(f'\n    Added node "{node_id}" (recorder {"on" if recorder_enabled else "off"}, '
          f'ambient {"on" if ambient_enabled else "off"})')
    return cfg


def toggle_recorder(cfg):
    nodes = cfg.get('nodes', {})
    if not nodes:
        print('    No nodes configured.')
        return cfg
    print('\n  Current nodes:')
    show_nodes(cfg)
    node_id = input('\n    Node id to toggle recorder on/off: ').strip()
    if node_id in nodes:
        nodes[node_id]['recorder_enabled'] = not nodes[node_id].get('recorder_enabled', False)
        state = 'on' if nodes[node_id]['recorder_enabled'] else 'off'
        print(f'    {node_id} recorder -> {state}')
    else:
        print('    No such node.')
    return cfg


def remove_node(cfg):
    nodes = cfg.get('nodes', {})
    if not nodes:
        print('    No nodes configured.')
        return cfg
    print('\n  Current nodes:')
    show_nodes(cfg)
    node_id = input('\n    Node id to remove from config: ').strip()
    if node_id in nodes:
        nodes.pop(node_id)
        print(f'    Removed "{node_id}" from config.')
        print(f'    NOTE: this only edits config.json. To tear down its services, run:')
        print(f'      sudo {VOICEBM_BASE}/bin/manage_nodes.sh remove {node_id}')
    else:
        print('    No such node.')
    return cfg


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def main():
    check_permissions()

    print('=' * 60)
    print('VoiceBM — Passive Node Setup')
    print(f'  base: {VOICEBM_BASE}')
    print('=' * 60)

    cfg = load_config()
    cfg.setdefault('nodes', {})

    while True:
        print('\n  ── Passive Nodes ──────────────────────────────────────')
        show_nodes(cfg)
        print('\n  [1] Add node')
        print('  [2] Toggle recorder on/off')
        print('  [3] Remove node')
        print('  [4] Save and exit')
        print('  [5] Exit without saving')

        choice = input('\n  Choice: ').strip()

        if choice == '1':
            cfg = add_node(cfg)
        elif choice == '2':
            cfg = toggle_recorder(cfg)
        elif choice == '3':
            cfg = remove_node(cfg)
        elif choice == '4':
            save_config(cfg)
            rec_nodes = [nid for nid, n in cfg.get('nodes', {}).items() if n.get('recorder_enabled')]
            if rec_nodes:
                print('\n  Build the services for each recorder-enabled node:')
                for nid in rec_nodes:
                    print(f'    sudo {VOICEBM_BASE}/bin/replicate_node.sh {nid}')
            amb_nodes = [nid for nid, n in cfg.get('nodes', {}).items() if n.get('ambient_enabled')]
            if amb_nodes:
                print('\n  Ambient-enabled nodes are served by the single ambient service:')
                print('    sudo systemctl restart voicebm-ambient.service')
            break
        elif choice == '5':
            print('  Exiting without saving.')
            break
        else:
            print('  Invalid choice.')


if __name__ == '__main__':
    main()
