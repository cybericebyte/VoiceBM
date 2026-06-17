#!/usr/bin/env python3
"""
VoiceBM Ambient Edition — Audio Event Detection Service
Independently versioned. Own systemd service. Own MQTT topics.

Modes (switchable live from HA):
  rotate    — sequential rotation through all enabled streams, fixed cycle
  trigger   — idle until Frigate motion fires, process that stream, return to idle
  attention — rotating baseline with motion-triggered interrupts, lockout+queue (default)

HA Controls (all hot-swappable, all persisted to config.json):
  Global:
    voicebm/ambient/enabled/set       — master on/off switch (OFF pauses processing)
    voicebm/ambient/mode/set          — rotate / trigger / attention
    voicebm/ambient/threshold/set     — detection confidence threshold (0.0-1.0)
    voicebm/ambient/cycle_s/set       — rotation cycle time in seconds
    voicebm/ambient/speech_forward/set — copy speech WAV to passive pipeline

  Per-stream:
    voicebm/ambient/{room}/enabled/set — enable/disable individual stream

Output topics (per stream):
  voicebm/ambient/{room}/state     — dominant event string (retained)
  voicebm/ambient/{room}/category  — bucketed category (retained)
  voicebm/ambient/{room}/scores    — top-10 JSON array (retained)
  voicebm/ambient/{room}/event     — full context payload (retained)
  voicebm/ambient/{room}/speech    — speech detected pulse (not retained)

System topics:
  voicebm/ambient/mode             — current mode (retained)
  voicebm/ambient/enabled          — master enabled state (retained)
  voicebm/ambient/threshold        — current threshold (retained)
  voicebm/ambient/cycle_s          — current cycle time (retained)
  voicebm/ambient/speech_forward   — speech forward state (retained)
  voicebm/ambient/active_source    — stream currently being processed (retained)

Config: config.json -> ambient section
  Run setup_ambient.py to configure streams.
"""

import os
import sys
import json
import time
import wave
import shutil
import signal
import threading
import collections
import subprocess

import numpy as np
import torch
from transformers import AutoFeatureExtractor, ASTForAudioClassification
import paho.mqtt.client as mqtt

sys.path.insert(0, '/home/user/voicebm')
from voicebm_config import get_mqtt_config

# ── Ambient soft hooks — passive context (identity + emote) ─────────────────
# Plug-in contract: voicebm_ambient_hooks.py present in bin/ -> active.
# Absent or broken -> ambient runs exactly as before.
try:
    import voicebm_ambient_hooks as ambient_hooks
    HOOKS_LOADED = True
    print('[ambient] passive context soft hooks loaded')
except Exception as _hook_err:
    ambient_hooks = None
    HOOKS_LOADED = False
    print(f'[ambient] soft hooks not loaded ({_hook_err}) — running without passive context')

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────
CONFIG_FILE = '/home/user/voicebm/config.json'
MODEL_NAME  = 'MIT/ast-finetuned-audioset-10-10-0.4593'
PASSIVE_REC_BASE = '/home/user/voicebm/recordings'

# System control topics
TOPIC_ENABLED         = 'voicebm/ambient/enabled'
TOPIC_ENABLED_SET     = 'voicebm/ambient/enabled/set'
TOPIC_MODE            = 'voicebm/ambient/mode'
TOPIC_MODE_SET        = 'voicebm/ambient/mode/set'
TOPIC_THRESHOLD       = 'voicebm/ambient/threshold'
TOPIC_THRESHOLD_SET   = 'voicebm/ambient/threshold/set'
TOPIC_CYCLE_S         = 'voicebm/ambient/cycle_s'
TOPIC_CYCLE_S_SET     = 'voicebm/ambient/cycle_s/set'
TOPIC_SPEECH_FWD      = 'voicebm/ambient/speech_forward'
TOPIC_SPEECH_FWD_SET  = 'voicebm/ambient/speech_forward/set'
TOPIC_ACTIVE_SRC      = 'voicebm/ambient/active_source'

VALID_MODES = ('rotate', 'trigger', 'attention')

# ─────────────────────────────────────────────────────────────────────────────
# Category map
# ─────────────────────────────────────────────────────────────────────────────
CATEGORY_MAP = {
    'Speech': 'speech', 'Male speech, man speaking': 'speech',
    'Female speech, woman speaking': 'speech', 'Child speech, kid speaking': 'speech',
    'Conversation': 'speech', 'Narration, monologue': 'speech',
    'Whispering': 'speech', 'Laughter': 'speech', 'Baby cry, infant cry': 'speech',
    'Crying, sobbing': 'speech', 'Shout': 'speech', 'Screaming': 'speech',
    'Crowd': 'speech', 'Hubbub, speech noise, speech babble': 'speech',
    'Music': 'music', 'Singing': 'music', 'Musical instrument': 'music',
    'Guitar': 'music', 'Electric guitar': 'music', 'Bass guitar': 'music',
    'Acoustic guitar': 'music', 'Piano': 'music', 'Keyboard (musical)': 'music',
    'Drum': 'music', 'Drum kit': 'music', 'Violin, fiddle': 'music',
    'Cello': 'music', 'Trumpet': 'music', 'Saxophone': 'music',
    'Synthesizer': 'music', 'Orchestra': 'music', 'Choir': 'music',
    'Pop music': 'music', 'Hip hop music': 'music', 'Rock music': 'music',
    'Jazz': 'music', 'Classical music': 'music', 'Electronic music': 'music',
    'Reggae': 'music', 'Country': 'music', 'Marimba, xylophone': 'music',
    'Animal': 'animal', 'Domestic animals, pets': 'animal',
    'Dog': 'animal', 'Bark': 'animal', 'Yip': 'animal', 'Howl': 'animal',
    'Bow-wow': 'animal', 'Growling': 'animal', 'Whimper (dog)': 'animal',
    'Cat': 'animal', 'Purr': 'animal', 'Meow': 'animal', 'Hiss': 'animal',
    'Caterwaul': 'animal', 'Bird': 'animal',
    'Bird vocalization, bird call, bird song': 'animal',
    'Chirp, tweet': 'animal', 'Squawk': 'animal', 'Pigeon, dove': 'animal',
    'Frog': 'animal', 'Insect': 'animal', 'Cricket': 'animal',
    'Mosquito': 'animal', 'Livestock, farm animals, working animals': 'animal',
    'Horse': 'animal', 'Cattle, bovine': 'animal', 'Chicken, rooster': 'animal',
    'Wild animals': 'animal', 'Roaring cats (lions, tigers)': 'animal',
    'Vehicle': 'vehicle', 'Car': 'vehicle', 'Truck': 'vehicle',
    'Motorcycle': 'vehicle', 'Bicycle': 'vehicle',
    'Traffic noise, roadway noise': 'vehicle',
    'Vehicle horn, car horn, honking': 'vehicle', 'Car alarm': 'vehicle',
    'Tire squeal': 'vehicle', 'Skidding': 'vehicle',
    'Race car, auto racing': 'vehicle', 'Aircraft': 'vehicle',
    'Jet engine': 'vehicle', 'Helicopter': 'vehicle',
    'Propeller, airscrew': 'vehicle', 'Train': 'vehicle',
    'Train whistle': 'vehicle', 'Train horn': 'vehicle',
    'Subway, metro, underground': 'vehicle', 'Boat, Water vehicle': 'vehicle',
    'Motorboat, speedboat': 'vehicle', 'Ship': 'vehicle',
    'Glass': 'impact', 'Breaking': 'impact', 'Shatter': 'impact',
    'Smash, crash': 'impact', 'Bang': 'impact', 'Explosion': 'impact',
    'Gunshot, gunfire': 'impact', 'Artillery fire': 'impact',
    'Burst, pop': 'impact', 'Hammer': 'impact', 'Drill': 'impact',
    'Jackhammer': 'impact', 'Chainsaw': 'impact',
    'Smoke detector, smoke alarm': 'alarm', 'Fire alarm': 'alarm',
    'Alarm': 'alarm', 'Siren': 'alarm', 'Civil defense siren': 'alarm',
    'Police car (siren)': 'alarm', 'Ambulance (siren)': 'alarm',
    'Fire engine, fire truck (siren)': 'alarm', 'Doorbell': 'alarm',
    'Knock': 'alarm',
    'Television': 'media', 'Radio': 'media', 'Telephone': 'media',
    'Cell phone': 'media', 'Ringtone': 'media', 'Jingle, tinkle': 'media',
}


# ─────────────────────────────────────────────────────────────────────────────
# Config I/O
# ─────────────────────────────────────────────────────────────────────────────
def load_ambient_config():
    with open(CONFIG_FILE, 'r') as f:
        cfg = json.load(f)
    ambient = cfg.get('ambient', {})

    # ── Node schema (2.0) ────────────────────────────────────────────────
    # config.json -> nodes. The key is the node_id: immutable, machine-facing,
    # lives in topics/dirs/identifiers and never changes. friendly_name is
    # display-only and freely editable. A node feeds ambient if the
    # 'ambient_enabled' key is PRESENT; its value is the HA toggle state.
    # Falls back to legacy ambient.sources if no nodes are defined.
    nodes   = cfg.get('nodes', {})
    sources = []
    for node_id, node in nodes.items():
        if 'ambient_enabled' not in node:
            continue
        sources.append({
            'name':           node_id,
            'room':           node_id,
            'friendly_name':  node.get('friendly_name', node_id.replace('_', ' ').title()),
            'rtsp_url':       node.get('rtsp_url', ''),
            'frigate_camera': node.get('frigate_camera', ''),
            'audio_filter':   node.get('audio_filter', ''),
            'enabled':        bool(node.get('ambient_enabled', True)),
        })

    if not sources:
        sources = ambient.get('sources', [])
        for s in sources:
            s.setdefault('friendly_name', s.get('name', '').replace('_', ' ').title())

    if not [s for s in sources if s.get('enabled', True)]:
        print('[ambient] ERROR: no enabled nodes in config.json (nodes / ambient.sources)')
        print('[ambient] Run: python3 /home/user/voicebm/bin/setup_ambient.py')
        sys.exit(1)
    return {
        'enabled':        ambient.get('enabled', True),
        'mode':           ambient.get('mode', 'attention'),
        'cycle_s':        int(ambient.get('cycle_s', 45)),
        'ping_timeout_s': float(ambient.get('ping_timeout_s', 5)),
        'segment_s':      int(ambient.get('segment_s', 5)),
        'threshold':      float(ambient.get('threshold', 0.25)),
        'speech_forward': ambient.get('speech_forward', False),
        'sources':        sources,   # ALL ambient nodes, not just enabled
    }


# ─────────────────────────────────────────────────────────────────────────────
# Offline tracker
# ─────────────────────────────────────────────────────────────────────────────
class OfflineTracker:
    def __init__(self, cycle_s):
        self.cooldown_s = cycle_s * 2
        self._offline   = {}
        self._lock      = threading.Lock()

    def mark_offline(self, name):
        with self._lock:
            self._offline[name] = time.time() + self.cooldown_s
            print(f'[ambient] {name} offline — cooldown {self.cooldown_s}s')

    def is_offline(self, name):
        with self._lock:
            expires = self._offline.get(name, 0)
            if time.time() < expires:
                return True
            self._offline.pop(name, None)
            return False

    def mark_online(self, name):
        with self._lock:
            self._offline.pop(name, None)


# ─────────────────────────────────────────────────────────────────────────────
# Audio / inference helpers
# ─────────────────────────────────────────────────────────────────────────────
def ping_stream(rtsp_url, timeout=5):
    try:
        r = subprocess.run(
            ['ffprobe', '-v', 'quiet', '-rtsp_transport', 'tcp',
             '-i', rtsp_url, '-show_streams', '-select_streams', 'a',
             '-print_format', 'json'],
            capture_output=True, timeout=timeout,
        )
        return r.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def capture_segment(rtsp_url, wav_path, segment_s, interrupt_event, audio_filter=''):
    cmd = [
        'ffmpeg', '-y', '-rtsp_transport', 'tcp', '-i', rtsp_url,
        '-t', str(segment_s), '-ar', '16000', '-ac', '1',
    ]
    # Per-node audio enhancement (config.json -> nodes -> audio_filter).
    # ffmpeg filter chain, e.g. "highpass=f=80,speechnorm". Empty = raw passthrough.
    if audio_filter:
        cmd += ['-af', audio_filter]
    cmd += ['-f', 'wav', wav_path]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    while proc.poll() is None:
        if interrupt_event is not None and interrupt_event.is_set():
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
            return False, True
        time.sleep(0.1)
    return proc.returncode == 0, False


def run_inference(extractor, model, wav_path):
    with wave.open(wav_path, 'rb') as f:
        sr  = f.getframerate()
        raw = f.readframes(f.getnframes())
    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    inputs  = extractor(samples, sampling_rate=sr, return_tensors='pt')
    with torch.no_grad():
        logits = model(**inputs).logits
    probs = torch.sigmoid(logits[0])
    top   = torch.topk(probs, 10)
    return [
        {'name': model.config.id2label[idx.item()], 'prob': round(probs[idx].item(), 4)}
        for idx in top.indices
    ]


# ─────────────────────────────────────────────────────────────────────────────
# HA MQTT discovery
# ─────────────────────────────────────────────────────────────────────────────
def publish_discovery(client, sources):
    device = {
        'identifiers': ['voicebm'],
        'name': 'Voice Biometrics',
        'manufacturer': 'David M. Dryver Sr.',
        'model': 'Home Assistant Voice Biometrics',
        'sw_version': '2.0',
    }
    p = 'homeassistant'

    # ── Master enable switch ──────────────────────────────────────────────
    client.publish(f'{p}/switch/voicebm_ambient_enabled/config', json.dumps({
        'name': 'Ambient Enabled',
        'unique_id': 'voicebm_ambient_enabled',
        'command_topic': TOPIC_ENABLED_SET,
        'state_topic': TOPIC_ENABLED,
        'payload_on': 'ON', 'payload_off': 'OFF',
        'icon': 'mdi:ear-hearing', 'device': device,
    }), qos=1, retain=True)

    # ── Mode select ───────────────────────────────────────────────────────
    client.publish(f'{p}/select/voicebm_ambient_mode/config', json.dumps({
        'name': 'Ambient Mode',
        'unique_id': 'voicebm_ambient_mode',
        'command_topic': TOPIC_MODE_SET,
        'state_topic': TOPIC_MODE,
        'options': list(VALID_MODES),
        'icon': 'mdi:swap-horizontal', 'device': device,
    }), qos=1, retain=True)

    # ── Threshold slider ──────────────────────────────────────────────────
    client.publish(f'{p}/number/voicebm_ambient_threshold/config', json.dumps({
        'name': 'Ambient Threshold',
        'unique_id': 'voicebm_ambient_threshold',
        'command_topic': TOPIC_THRESHOLD_SET,
        'state_topic': TOPIC_THRESHOLD,
        'min': 0.05, 'max': 0.95, 'step': 0.05, 'mode': 'slider',
        'icon': 'mdi:tune', 'device': device,
    }), qos=1, retain=True)

    # ── Cycle time slider ─────────────────────────────────────────────────
    client.publish(f'{p}/number/voicebm_ambient_cycle_s/config', json.dumps({
        'name': 'Ambient Cycle Time (s)',
        'unique_id': 'voicebm_ambient_cycle_s',
        'command_topic': TOPIC_CYCLE_S_SET,
        'state_topic': TOPIC_CYCLE_S,
        'min': 30, 'max': 300, 'step': 15, 'mode': 'slider',
        'unit_of_measurement': 's',
        'icon': 'mdi:timer', 'device': device,
    }), qos=1, retain=True)

    # ── Speech forward switch ─────────────────────────────────────────────
    client.publish(f'{p}/switch/voicebm_ambient_speech_forward/config', json.dumps({
        'name': 'Ambient Speech Forward',
        'unique_id': 'voicebm_ambient_speech_forward',
        'command_topic': TOPIC_SPEECH_FWD_SET,
        'state_topic': TOPIC_SPEECH_FWD,
        'payload_on': 'ON', 'payload_off': 'OFF',
        'icon': 'mdi:account-voice', 'device': device,
    }), qos=1, retain=True)

    # ── Active stream sensor ──────────────────────────────────────────────
    client.publish(f'{p}/sensor/voicebm_ambient_active_source/config', json.dumps({
        'name': 'Ambient Active Stream',
        'unique_id': 'voicebm_ambient_active_source',
        'state_topic': TOPIC_ACTIVE_SRC,
        'icon': 'mdi:access-point', 'device': device,
    }), qos=1, retain=True)

    # ── Per-stream entities ───────────────────────────────────────────────
    # All per-node ambient entities live on the NODE's room device
    # (identifiers ["voicebm_{node}"]) — merging with the passive side's
    # device when one exists, creating it when not. Names are prefixed
    # "Ambient" so add-on entities are unmistakable next to passive ones.
    for source in sources:
        room     = source['room']
        name     = source['name']
        friendly = source.get('friendly_name', name.replace('_', ' ').title())
        uid      = room.replace(' ', '_').lower()

        node_device = {
            'identifiers': [f'voicebm_{uid}'],
            'name': f'Voice Biometrics {friendly}',
            'manufacturer': 'David M. Dryver Sr.',
            'model': 'Home Assistant Voice Biometrics',
            'sw_version': '2.0',
        }

        # Per-stream enable switch
        client.publish(
            f'{p}/switch/voicebm_ambient_stream_{uid}_enabled/config',
            json.dumps({
                'name': 'Ambient Enabled',
                'unique_id': f'voicebm_ambient_stream_{uid}_enabled',
                'command_topic': f'voicebm/ambient/{room}/enabled/set',
                'state_topic': f'voicebm/ambient/{room}/enabled',
                'payload_on': 'ON', 'payload_off': 'OFF',
                'icon': 'mdi:access-point', 'device': node_device,
            }), qos=1, retain=True
        )

        # Focus button (attention button primitive)
        client.publish(f'{p}/button/voicebm_ambient_focus_{uid}/config', json.dumps({
            'name': 'Ambient Focus',
            'unique_id': f'voicebm_ambient_focus_{uid}',
            'command_topic': f'voicebm/ambient/{room}/focus/set',
            'payload_press': 'PRESS',
            'icon': 'mdi:target',
            'device': node_device,
        }), qos=1, retain=True)

        # State sensor
        client.publish(f'{p}/sensor/voicebm_ambient_state_{uid}/config', json.dumps({
            'name': 'Ambient State',
            'unique_id': f'voicebm_ambient_state_{uid}',
            'state_topic': f'voicebm/ambient/{room}/state',
            'icon': 'mdi:ear-hearing', 'device': node_device,
        }), qos=1, retain=True)

        # Category sensor
        client.publish(f'{p}/sensor/voicebm_ambient_category_{uid}/config', json.dumps({
            'name': 'Ambient Category',
            'unique_id': f'voicebm_ambient_category_{uid}',
            'state_topic': f'voicebm/ambient/{room}/category',
            'icon': 'mdi:shape', 'device': node_device,
        }), qos=1, retain=True)

        # Scores sensor
        client.publish(f'{p}/sensor/voicebm_ambient_scores_{uid}/config', json.dumps({
            'name': 'Ambient Scores',
            'unique_id': f'voicebm_ambient_scores_{uid}',
            'state_topic': f'voicebm/ambient/{room}/scores',
            'value_template': "{{ value_json[0].name if value_json else 'none' }}",
            'json_attributes_topic': f'voicebm/ambient/{room}/scores',
            'json_attributes_template': "{{ {'scores': value_json} | tojson }}",
            'icon': 'mdi:chart-bar', 'device': node_device,
        }), qos=1, retain=True)

        # Event sensor
        client.publish(f'{p}/sensor/voicebm_ambient_event_{uid}/config', json.dumps({
            'name': 'Ambient Event',
            'unique_id': f'voicebm_ambient_event_{uid}',
            'state_topic': f'voicebm/ambient/{room}/event',
            'value_template': "{{ value_json.state }}",
            'json_attributes_topic': f'voicebm/ambient/{room}/event',
            'icon': 'mdi:bell', 'device': node_device,
        }), qos=1, retain=True)

    print(f'[ambient] HA discovery published ({len(sources)} streams)')


# ─────────────────────────────────────────────────────────────────────────────
# Service
# ─────────────────────────────────────────────────────────────────────────────
class AmbientService:

    def __init__(self):
        cfg = load_ambient_config()

        # Runtime state — all hot-swappable
        self.enabled        = cfg['enabled']
        self.mode           = cfg['mode']
        self.cycle_s        = cfg['cycle_s']
        self.ping_timeout_s = cfg['ping_timeout_s']
        self.segment_s      = cfg['segment_s']
        self.threshold      = cfg['threshold']
        self.speech_forward = cfg['speech_forward']

        # All sources (including disabled) — per-source enabled tracked here
        self.all_sources    = cfg['sources']
        self.source_enabled = {s['name']: s.get('enabled', True) for s in self.all_sources}

        self.offline     = OfflineTracker(self.cycle_s)
        self.config_lock = threading.Lock()

        # Attention mode state
        self.interrupt_event  = threading.Event()
        self.interrupt_source = [None]
        self.attention_queue  = collections.deque()
        self.queue_lock       = threading.Lock()
        self.locked_until     = 0.0

        # MQTT
        mqtt_cfg    = get_mqtt_config()
        self.broker = mqtt_cfg['broker']
        self.port   = mqtt_cfg['port']
        self.client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        self.client.username_pw_set(mqtt_cfg['user'], mqtt_cfg['password'])
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

        # Model
        print('[ambient] Loading AST model...')
        self.extractor = AutoFeatureExtractor.from_pretrained(MODEL_NAME)
        self.model     = ASTForAudioClassification.from_pretrained(MODEL_NAME)
        self.model.eval()
        print('[ambient] Model ready')

    # ── Config persistence ────────────────────────────────────────────────
    def _persist(self, updates):
        """Write ambient-level key/value pairs to config.json."""
        with self.config_lock:
            try:
                with open(CONFIG_FILE, 'r') as f:
                    cfg = json.load(f)
                if 'ambient' not in cfg:
                    cfg['ambient'] = {}
                cfg['ambient'].update(updates)
                with open(CONFIG_FILE, 'w') as f:
                    json.dump(cfg, f, indent=2)
            except Exception as e:
                print(f'[ambient] config write failed: {e}')

    def _persist_source(self, name, enabled):
        """Write enabled state for a node (nodes schema) or legacy source."""
        with self.config_lock:
            try:
                with open(CONFIG_FILE, 'r') as f:
                    cfg = json.load(f)
                node = cfg.get('nodes', {}).get(name)
                if node is not None and 'ambient_enabled' in node:
                    node['ambient_enabled'] = enabled
                else:
                    for s in cfg.get('ambient', {}).get('sources', []):
                        if s.get('name') == name:
                            s['enabled'] = enabled
                            break
                with open(CONFIG_FILE, 'w') as f:
                    json.dump(cfg, f, indent=2)
            except Exception as e:
                print(f'[ambient] source config write failed: {e}')

    # ── MQTT callbacks ────────────────────────────────────────────────────
    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code != 0:
            print(f'[ambient] MQTT connect failed: {reason_code}')
            return

        print(f'[ambient] MQTT connected to {self.broker}')

        # Subscribe to all control topics
        subs = [
            (TOPIC_ENABLED_SET,    1),
            (TOPIC_MODE_SET,       1),
            (TOPIC_THRESHOLD_SET,  1),
            (TOPIC_CYCLE_S_SET,    1),
            (TOPIC_SPEECH_FWD_SET, 1),
        ]
        # Per-stream enable commands
        for source in self.all_sources:
            subs.append((f'voicebm/ambient/{source["room"]}/enabled/set', 1))
        # Per-node focus commands (attention button primitive)
        for source in self.all_sources:
            subs.append((f'voicebm/ambient/{source["room"]}/focus/set', 1))
        # Frigate motion
        for source in self.all_sources:
            cam = source.get('frigate_camera', '')
            if cam:
                subs.append((f'frigate/{cam}/motion', 0))
                print(f'[ambient] motion: frigate/{cam}/motion')

        client.subscribe(subs)

        # Publish discovery
        publish_discovery(client, self.all_sources)

        # Passive context discovery (soft hook)
        if HOOKS_LOADED:
            ambient_hooks.publish_context_discovery(client, self.all_sources)

        # Publish current state from config (source of truth on startup)
        client.publish(TOPIC_ENABLED,   'ON' if self.enabled else 'OFF',          retain=True)
        client.publish(TOPIC_MODE,      self.mode,                                 retain=True)
        client.publish(TOPIC_THRESHOLD, str(self.threshold),                       retain=True)
        client.publish(TOPIC_CYCLE_S,   str(self.cycle_s),                         retain=True)
        client.publish(TOPIC_SPEECH_FWD,'ON' if self.speech_forward else 'OFF',    retain=True)

        # Per-stream enabled states
        for source in self.all_sources:
            room    = source['room']
            enabled = self.source_enabled.get(source['name'], True)
            client.publish(f'voicebm/ambient/{room}/enabled',
                           'ON' if enabled else 'OFF', retain=True)

        # Clear stale output state
        for source in self.all_sources:
            room = source['room']
            client.publish(f'voicebm/ambient/{room}/state',    'none', retain=True)
            client.publish(f'voicebm/ambient/{room}/category', 'none', retain=True)
        client.publish(TOPIC_ACTIVE_SRC, 'none', retain=True)

    def _on_message(self, client, userdata, msg):
        topic   = msg.topic
        payload = msg.payload.decode('utf-8', errors='replace').strip()

        # ── Master enable ─────────────────────────────────────────────────
        if topic == TOPIC_ENABLED_SET:
            self.enabled = (payload == 'ON')
            client.publish(TOPIC_ENABLED, payload, retain=True)
            self._persist({'enabled': self.enabled})
            print(f'[ambient] enabled -> {self.enabled}')
            return

        # ── Mode ──────────────────────────────────────────────────────────
        if topic == TOPIC_MODE_SET:
            if payload in VALID_MODES:
                self.mode = payload
                client.publish(TOPIC_MODE, payload, retain=True)
                self._persist({'mode': payload})
                print(f'[ambient] mode -> {payload}')
                self.interrupt_event.clear()
                self.interrupt_source[0] = None
                with self.queue_lock:
                    self.attention_queue.clear()
                self.locked_until = 0.0
            return

        # ── Threshold ─────────────────────────────────────────────────────
        if topic == TOPIC_THRESHOLD_SET:
            try:
                val = round(float(payload), 4)
                if 0.0 <= val <= 1.0:
                    self.threshold = val
                    client.publish(TOPIC_THRESHOLD, str(val), retain=True)
                    self._persist({'threshold': val})
                    print(f'[ambient] threshold -> {val}')
            except ValueError:
                pass
            return

        # ── Cycle time ────────────────────────────────────────────────────
        if topic == TOPIC_CYCLE_S_SET:
            try:
                val = int(float(payload))
                if 10 <= val <= 600:
                    self.cycle_s = val
                    self.offline.cooldown_s = val * 2
                    client.publish(TOPIC_CYCLE_S, str(val), retain=True)
                    self._persist({'cycle_s': val})
                    print(f'[ambient] cycle_s -> {val}')
            except ValueError:
                pass
            return

        # ── Speech forward ────────────────────────────────────────────────
        if topic == TOPIC_SPEECH_FWD_SET:
            self.speech_forward = (payload == 'ON')
            client.publish(TOPIC_SPEECH_FWD, payload, retain=True)
            self._persist({'speech_forward': self.speech_forward})
            print(f'[ambient] speech_forward -> {self.speech_forward}')
            return

        # ── Per-stream enable ─────────────────────────────────────────────
        for source in self.all_sources:
            room = source['room']
            if topic == f'voicebm/ambient/{room}/enabled/set':
                enabled = (payload == 'ON')
                self.source_enabled[source['name']] = enabled
                client.publish(f'voicebm/ambient/{room}/enabled',
                               payload, retain=True)
                self._persist_source(source['name'], enabled)
                print(f'[ambient] stream {source["name"]} -> {"enabled" if enabled else "disabled"}')
                return

        # ── Per-node focus (attention button primitive) ───────────────────
        for source in self.all_sources:
            if topic == f'voicebm/ambient/{source["room"]}/focus/set':
                self._focus(source)
                return

        # ── Frigate motion — attention mode only ──────────────────────────
        if payload != 'ON' or self.mode != 'attention' or not self.enabled:
            return

        for source in self.all_sources:
            cam = source.get('frigate_camera', '')
            if not cam or topic != f'frigate/{cam}/motion':
                continue
            if not self.source_enabled.get(source['name'], True):
                return
            if self.offline.is_offline(source['name']):
                return

            now = time.time()
            if now < self.locked_until:
                with self.queue_lock:
                    queued_names = [s['name'] for s in self.attention_queue]
                    if source['name'] not in queued_names:
                        self.attention_queue.append(source)
                        print(f'[ambient] queued (locked): {source["name"]}')
            else:
                print(f'[ambient] attention: {source["name"]}')
                self.interrupt_source[0] = source
                self.interrupt_event.set()
            return

    # ── Helpers ───────────────────────────────────────────────────────────
    def _focus(self, source):
        """
        Focus primitive: deliberately direct attention to one node.

        Same interrupt + lockout + queue mechanism the Frigate motion
        consumer rides — exposed as a per-node MQTT command so the trigger
        POLICY belongs to the integrator (HA automations, scripts, the consuming LLM),
        not to VoiceBM. The Frigate motion path is just one consumer of
        this mechanism.

        Honored in attention and trigger modes. Ignored in rotate mode
        (rotate means rotate), when ambient is disabled, when the node is
        disabled, or when the node is in offline cooldown.
        """
        name = source['name']
        if not self.enabled:
            print(f'[ambient] focus {name} ignored — ambient disabled')
            return
        if self.mode == 'rotate':
            print(f'[ambient] focus {name} ignored — rotate mode')
            return
        if not self.source_enabled.get(name, True):
            print(f'[ambient] focus {name} ignored — node disabled')
            return
        if self.offline.is_offline(name):
            print(f'[ambient] focus {name} ignored — node offline (cooldown)')
            return

        now = time.time()
        if self.mode == 'attention' and now < self.locked_until:
            with self.queue_lock:
                if name not in [s['name'] for s in self.attention_queue]:
                    self.attention_queue.append(source)
                    print(f'[ambient] focus queued (locked): {name}')
        else:
            if self.mode == 'attention':
                # Queue + interrupt: the queue guarantees pickup even if the
                # interrupt event is cleared at the top of the next loop
                # iteration (e.g. focus pressed during the pad sleep).
                with self.queue_lock:
                    if name not in [s['name'] for s in self.attention_queue]:
                        self.attention_queue.append(source)
            print(f'[ambient] focus: {name}')
            self.interrupt_source[0] = source
            self.interrupt_event.set()

    def _set_lockout(self):
        self.locked_until = time.time() + self.cycle_s

    def _active_sources(self):
        """Return sources that are currently enabled."""
        return [s for s in self.all_sources if self.source_enabled.get(s['name'], True)]

    def _maybe_forward_speech(self, source, scores, wav_path):
        """
        If speech_forward is ON and top result is speech, copy WAV to the
        passive recordings directory for this stream's room (if it exists).
        Passive embedder picks it up on its next cycle.
        Room label must match the passive recordings directory name.
        """
        if not self.speech_forward:
            return
        if not scores:
            return
        category = CATEGORY_MAP.get(scores[0]['name'], 'ambient')
        if category != 'speech':
            return
        passive_dir = os.path.join(PASSIVE_REC_BASE, source['room'])
        if not os.path.exists(passive_dir):
            return
        dst = os.path.join(passive_dir, f'ambient_{int(time.time() * 1000)}.wav')
        try:
            shutil.copy2(wav_path, dst)
            print(f'  [{source["name"]}] speech forwarded -> {os.path.basename(dst)}')
        except Exception as e:
            print(f'  [{source["name"]}] speech forward failed: {e}')

    def _publish_result(self, source, scores, wav_path):
        if not scores:
            return
        state    = scores[0]['name']
        top_prob = scores[0]['prob']
        category = CATEGORY_MAP.get(state, 'ambient')
        room     = source['room']

        self.client.publish(f'voicebm/ambient/{room}/state',    'none', retain=True)
        self.client.publish(f'voicebm/ambient/{room}/category', 'none', retain=True)

        if top_prob >= self.threshold:
            payload = {
                'state': state, 'category': category, 'prob': top_prob,
                'source': source['name'], 'room': room,
                'ts': time.strftime('%Y-%m-%dT%H:%M:%SZ'),
            }
            self.client.publish(f'voicebm/ambient/{room}/state',    state,                      retain=True)
            self.client.publish(f'voicebm/ambient/{room}/scores',   json.dumps(scores),         retain=True)
            self.client.publish(f'voicebm/ambient/{room}/category', category,                   retain=True)
            self.client.publish(f'voicebm/ambient/{room}/event',    json.dumps(payload),        retain=True)
            if category == 'speech':
                self.client.publish(f'voicebm/ambient/{room}/speech', 'detected', retain=False)
                if HOOKS_LOADED:
                    ambient_hooks.run_passive_context(self.client, source, state, top_prob, wav_path)
            print(f'  [{source["name"]}] {state} ({top_prob:.4f}) -> {category} — published')
            self._maybe_forward_speech(source, scores, wav_path)
        else:
            print(f'  [{source["name"]}] {state} ({top_prob:.4f}) -> below threshold')

    def _process_source(self, source, interruptible=True):
        """Ping, capture, infer, publish one stream."""
        name    = source['name']
        room    = source['room']
        tmp_wav = f'/tmp/voicebm_ambient_{room}.wav'

        print(f'[{time.strftime("%H:%M:%S")}] pinging {name}...')
        if not ping_stream(source['rtsp_url'], timeout=self.ping_timeout_s):
            print(f'  [{name}] offline — skipping')
            self.offline.mark_offline(name)
            return True

        self.offline.mark_online(name)
        self.client.publish(TOPIC_ACTIVE_SRC, name, retain=True)
        print(f'[{time.strftime("%H:%M:%S")}] capturing {name}'
              f'{" (locked)" if not interruptible else ""}...')

        interrupt = self.interrupt_event if interruptible else None
        ok, interrupted = capture_segment(source['rtsp_url'], tmp_wav, self.segment_s, interrupt,
                                          source.get('audio_filter', ''))

        if interrupted:
            print(f'  [{name}] interrupted')
            return False

        if not ok or not os.path.exists(tmp_wav):
            print(f'  [{name}] capture failed — marking offline')
            self.offline.mark_offline(name)
            return True

        scores = run_inference(self.extractor, self.model, tmp_wav)
        self._publish_result(source, scores, tmp_wav)
        return True

    # ── Main loop ─────────────────────────────────────────────────────────
    def run(self):
        self._stop = threading.Event()

        def _sigterm(signum, frame):
            print('[ambient] SIGTERM — shutting down')
            self._stop.set()
            self.interrupt_event.set()

        signal.signal(signal.SIGTERM, _sigterm)
        signal.signal(signal.SIGINT,  _sigterm)

        self.client.connect(self.broker, self.port, 60)
        self.client.loop_start()
        time.sleep(1)

        idx = 0
        print(f'[ambient] mode={self.mode} | cycle={self.cycle_s}s | threshold={self.threshold}')

        try:
            while not self._stop.is_set():
                # ── Master pause ──────────────────────────────────────────
                if not self.enabled:
                    self.client.publish(TOPIC_ACTIVE_SRC, 'paused', retain=True)
                    time.sleep(5)
                    continue

                active = self._active_sources()
                if not active:
                    print('[ambient] no enabled streams — sleeping')
                    time.sleep(10)
                    continue

                cycle_start = time.time()
                n           = len(active)
                mode        = self.mode

                # ── ROTATE ────────────────────────────────────────────────
                if mode == 'rotate':
                    source = active[idx % n]
                    idx   += 1
                    if not self.offline.is_offline(source['name']):
                        self._process_source(source, interruptible=False)
                    else:
                        print(f'  [{source["name"]}] cooldown — skipping')

                # ── TRIGGER ───────────────────────────────────────────────
                elif mode == 'trigger':
                    print(f'[{time.strftime("%H:%M:%S")}] trigger — waiting...')
                    fired = self.interrupt_event.wait(timeout=self.cycle_s)
                    if fired:
                        source = self.interrupt_source[0]
                        self.interrupt_event.clear()
                        self.interrupt_source[0] = None
                        if source and not self.offline.is_offline(source['name']):
                            self._process_source(source, interruptible=False)
                    continue

                # ── ATTENTION ─────────────────────────────────────────────
                elif mode == 'attention':
                    self.interrupt_event.clear()
                    self.interrupt_source[0] = None

                    with self.queue_lock:
                        queued = self.attention_queue.popleft() if self.attention_queue else None

                    if queued:
                        if not self.offline.is_offline(queued['name']):
                            print(f'[{time.strftime("%H:%M:%S")}] queue -> {queued["name"]}')
                            self._set_lockout()
                            self._process_source(queued, interruptible=False)
                        else:
                            print(f'  [{queued["name"]}] queued but offline — skipping')
                    else:
                        source = active[idx % n]
                        idx   += 1

                        if self.offline.is_offline(source['name']):
                            print(f'  [{source["name"]}] cooldown — skipping')
                        else:
                            completed = self._process_source(source, interruptible=True)
                            if not completed:
                                attn = self.interrupt_source[0]
                                self.interrupt_event.clear()
                                self.interrupt_source[0] = None
                                if attn and not self.offline.is_offline(attn['name']):
                                    print(f'[{time.strftime("%H:%M:%S")}] -> attention locked: {attn["name"]}')
                                    self._set_lockout()
                                    self._process_source(attn, interruptible=False)
                                    # Dedup: focus queues + interrupts; if the
                                    # interrupt path served it, drop the queue copy.
                                    with self.queue_lock:
                                        self.attention_queue = collections.deque(
                                            s for s in self.attention_queue
                                            if s['name'] != attn['name'])

                # ── Pad cycle ─────────────────────────────────────────────
                elapsed = time.time() - cycle_start
                sleep_s = max(0, self.cycle_s - elapsed)
                print(f'  cycle {elapsed:.1f}s | sleep {sleep_s:.1f}s')
                if sleep_s > 0:
                    time.sleep(sleep_s)

        except KeyboardInterrupt:
            print('\n[ambient] shutting down')
        finally:
            self.client.publish(TOPIC_ACTIVE_SRC, 'none', retain=True)
            self.client.loop_stop()
            self.client.disconnect()


def main():
    print('=' * 60)
    print('VoiceBM Ambient Edition — pre-alpha')
    print('=' * 60)
    AmbientService().run()


if __name__ == '__main__':
    main()
