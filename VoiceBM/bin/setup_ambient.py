#!/usr/bin/env python3
"""
VoiceBM Ambient Edition — Interactive Setup
Adds and manages ambient monitoring sources in config.json.

Run this before starting voicebm-ambient.service.
NOTE (2.0): the ambient service reads nodes with an ambient_enabled flag
first (set those via setup_node.py); this sources list is the legacy
fallback, used only when no nodes are defined.
Can be run multiple times to add/remove/toggle sources safely.
Never overwrites sources already configured — only appends or modifies.

Usage: python3 setup_ambient.py
"""

import json
import sys
import os
import subprocess

VOICEBM_BASE = os.environ.get('VOICEBM_BASE') or \
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(VOICEBM_BASE, 'config.json')


# ─────────────────────────────────────────────────────────────────────────────
# Permissions check — fail clean before touching anything
# ─────────────────────────────────────────────────────────────────────────────
def check_permissions():
    if not os.path.exists(CONFIG_FILE):
        print(f'ERROR: config.json not found at {CONFIG_FILE}')
        sys.exit(1)
    if not os.access(CONFIG_FILE, os.W_OK):
        print(f'ERROR: No write permission on {CONFIG_FILE}')
        print(f'Fix the ownership/permissions on {CONFIG_FILE}')
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
# RTSP validation
# ─────────────────────────────────────────────────────────────────────────────
def validate_rtsp(rtsp_url):
    """
    Quick ffprobe connection test — no file written, 10 second timeout.
    Returns True if stream is reachable and has an audio track.
    """
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
            # Confirm at least one audio stream was found
            try:
                data = json.loads(result.stdout.decode('utf-8', errors='replace'))
                if data.get('streams'):
                    print(f'    Stream valid — audio confirmed.')
                    return True
                else:
                    print(f'    Stream reachable but no audio track found.')
                    return False
            except Exception:
                # ffprobe returned 0 — stream at minimum connected
                print(f'    Stream reachable.')
                return True
        else:
            err = result.stderr.decode('utf-8', errors='replace').strip()
            # Show last meaningful line only — ffprobe stderr is verbose
            lines = [l for l in err.splitlines() if l.strip()]
            hint  = lines[-1] if lines else 'no detail available'
            print(f'    Stream unreachable: {hint}')
            return False
    except subprocess.TimeoutExpired:
        print(f'    Timed out — stream did not respond within 10 seconds.')
        return False
    except FileNotFoundError:
        print(f'    ffprobe not found — skipping validation.')
        return True   # can't validate, allow entry


# ─────────────────────────────────────────────────────────────────────────────
# Display helpers
# ─────────────────────────────────────────────────────────────────────────────
def show_existing_sources(cfg):
    sources = cfg.get('ambient', {}).get('sources', [])
    if not sources:
        print('    (none configured yet)')
        return
    for i, s in enumerate(sources):
        status = 'enabled' if s.get('enabled', True) else 'DISABLED'
        print(f'    [{i + 1}] {s["name"]}')
        print(f'         room:    {s["room"]}')
        print(f'         rtsp:    {s["rtsp_url"]}')
        print(f'         status:  {status}')


def show_available_rtsp(cfg):
    """Show RTSP URLs already in rooms config as a convenience reference."""
    rooms = cfg.get('rooms', {})
    if not rooms:
        return
    existing_urls = {
        s['rtsp_url']
        for s in cfg.get('ambient', {}).get('sources', [])
    }
    available = {
        name: rcfg['rtsp_url']
        for name, rcfg in rooms.items()
        if rcfg.get('rtsp_url') and rcfg['rtsp_url'] not in existing_urls
    }
    if available:
        print('\n    RTSP sources from rooms config (not yet added to ambient):')
        for room_name, url in available.items():
            print(f'      {room_name}: {url}')
    else:
        print('\n    (all rooms config RTSP sources already added to ambient)')
    print()


# ─────────────────────────────────────────────────────────────────────────────
# Input helpers
# ─────────────────────────────────────────────────────────────────────────────
def get_required(prompt):
    while True:
        val = input(f'    {prompt}: ').strip()
        if val:
            return val
        print('    (required — cannot be blank)')


def get_optional(prompt):
    return input(f'    {prompt} (enter to skip): ').strip()


def get_with_default(prompt, default):
    val = input(f'    {prompt} [{default}]: ').strip()
    return val if val else str(default)


# ─────────────────────────────────────────────────────────────────────────────
# Operations
# ─────────────────────────────────────────────────────────────────────────────
def add_source(cfg):
    print('\n  ── Add Ambient Source ─────────────────────────────────')
    show_available_rtsp(cfg)

    # Check for duplicate name
    existing_names = {s['name'] for s in cfg.get('ambient', {}).get('sources', [])}

    while True:
        name = get_required('Source name — descriptive, no spaces e.g. living_room_cam, rear_porch_cam')
        if name in existing_names:
            print(f'    "{name}" already exists. Choose a different name.')
        else:
            break

    room        = get_required('Room label — used in MQTT topic e.g. living_room, rear_porch')

    # RTSP URL with validation loop
    while True:
        rtsp_url = get_required('RTSP URL')
        if validate_rtsp(rtsp_url):
            break
        retry = input('    Re-enter URL? [Y/n]: ').strip().lower()
        if retry == 'n':
            print('    Proceeding without validation confirmation.')
            break

    enabled_raw   = input('    Enable this source? [Y/n]: ').strip().lower()
    enabled       = enabled_raw != 'n'

    source = {
        'name':           name,
        'room':           room,
        'rtsp_url':       rtsp_url,
        'enabled':        enabled,
    }

    if 'ambient' not in cfg:
        cfg['ambient'] = {}
    if 'sources' not in cfg['ambient']:
        cfg['ambient']['sources'] = []

    cfg['ambient']['sources'].append(source)
    print(f'\n    Added: {name} ({"enabled" if enabled else "disabled"})')
    return cfg


def toggle_source(cfg):
    sources = cfg.get('ambient', {}).get('sources', [])
    if not sources:
        print('    No sources configured.')
        return cfg

    print('\n  Current sources:')
    show_existing_sources(cfg)

    try:
        raw = input('\n    Source number to toggle: ').strip()
        idx = int(raw) - 1
        if 0 <= idx < len(sources):
            sources[idx]['enabled'] = not sources[idx].get('enabled', True)
            status = 'enabled' if sources[idx]['enabled'] else 'disabled'
            print(f'    {sources[idx]["name"]} -> {status}')
            print(f'    Restart voicebm-ambient.service for change to take effect.')
        else:
            print('    Invalid number.')
    except ValueError:
        print('    Invalid input.')
    return cfg


def remove_source(cfg):
    sources = cfg.get('ambient', {}).get('sources', [])
    if not sources:
        print('    No sources configured.')
        return cfg

    print('\n  Current sources:')
    show_existing_sources(cfg)

    try:
        raw = input('\n    Source number to remove: ').strip()
        idx = int(raw) - 1
        if 0 <= idx < len(sources):
            removed = sources.pop(idx)
            print(f'    Removed: {removed["name"]}')
            print(f'    Restart voicebm-ambient.service for change to take effect.')
        else:
            print('    Invalid number.')
    except ValueError:
        print('    Invalid input.')
    return cfg


def configure_global_settings(cfg):
    print('\n  ── Global Ambient Settings ────────────────────────────')
    ambient = cfg.get('ambient', {})

    current_mode    = ambient.get('mode', 'attention')
    current_cycle   = ambient.get('cycle_s', 45)
    current_segment = ambient.get('segment_s', 5)
    current_thresh  = ambient.get('threshold', 0.25)

    print(f'\n    Modes:')
    print(f'      rotate    — sequential rotation, fixed cycle')
    print(f'      trigger   — idle until an external motion trigger fires')
    print(f'      attention — rotating baseline + motion interrupt with lockout/queue (recommended)')

    mode_raw = input(f'\n    Mode (rotate/trigger/attention) [{current_mode}]: ').strip().lower()
    mode     = mode_raw if mode_raw in ('rotate', 'trigger', 'attention') else current_mode

    cycle_raw = get_with_default('Cycle time seconds', current_cycle)
    try:
        cycle_s = int(cycle_raw)
    except ValueError:
        cycle_s = current_cycle

    seg_raw = get_with_default('Capture segment seconds', current_segment)
    try:
        segment_s = int(seg_raw)
    except ValueError:
        segment_s = current_segment

    thresh_raw = get_with_default('Detection threshold (0.0-1.0)', current_thresh)
    try:
        threshold = float(thresh_raw)
    except ValueError:
        threshold = current_thresh

    if 'ambient' not in cfg:
        cfg['ambient'] = {}

    # Only update keys — never touch sources
    cfg['ambient'].update({
        'mode':      mode,
        'cycle_s':   cycle_s,
        'segment_s': segment_s,
        'threshold': threshold,
    })

    print(f'\n    Saved: mode={mode}, cycle={cycle_s}s, segment={segment_s}s, threshold={threshold}')
    print(f'    Restart voicebm-ambient.service for changes to take effect.')
    return cfg


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def main():
    check_permissions()

    print('=' * 60)
    print('VoiceBM Ambient Edition — Setup')
    print('=' * 60)

    cfg = load_config()

    # Ensure ambient section exists with safe defaults — never overwrite existing
    if 'ambient' not in cfg:
        cfg['ambient'] = {
            'mode':      'attention',
            'cycle_s':   45,
            'segment_s': 5,
            'threshold': 0.25,
            'sources':   [],
        }
    if 'sources' not in cfg['ambient']:
        cfg['ambient']['sources'] = []

    while True:
        print('\n  ── Ambient Configuration ──────────────────────────────')
        ambient = cfg.get('ambient', {})
        print(f'  Mode: {ambient.get("mode", "attention")} | '
              f'Cycle: {ambient.get("cycle_s", 45)}s | '
              f'Segment: {ambient.get("segment_s", 5)}s | '
              f'Threshold: {ambient.get("threshold", 0.25)}')
        print('\n  Sources:')
        show_existing_sources(cfg)

        print('\n  [1] Add source')
        print('  [2] Toggle source enabled/disabled')
        print('  [3] Remove source')
        print('  [4] Global settings (mode, cycle time, threshold)')
        print('  [5] Save and exit')
        print('  [6] Exit without saving')

        choice = input('\n  Choice: ').strip()

        if choice == '1':
            cfg = add_source(cfg)
        elif choice == '2':
            cfg = toggle_source(cfg)
        elif choice == '3':
            cfg = remove_source(cfg)
        elif choice == '4':
            cfg = configure_global_settings(cfg)
        elif choice == '5':
            save_config(cfg)
            sources = cfg.get('ambient', {}).get('sources', [])
            enabled = [s for s in sources if s.get('enabled', True)]
            print(f'\n  {len(enabled)} source(s) enabled.')
            if enabled:
                print('\n  Restart service to pick up changes:')
                print('    sudo systemctl restart voicebm-ambient.service')
                print('\n  Watch logs:')
                print('    sudo journalctl -u voicebm-ambient.service -f')
            break
        elif choice == '6':
            print('  Exiting without saving.')
            break
        else:
            print('  Invalid choice.')


if __name__ == '__main__':
    main()
