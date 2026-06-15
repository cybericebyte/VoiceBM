# VoiceBM 2.0 — Source Reference (single document)

This document folds every agnostic VoiceBM 2.0 Python script into one place, plus an example `config.json`, so it can be read whole to understand how the system works. All paths use the generic `/home/user/voicebm` base. The example config uses documentation IP ranges and placeholder credentials only — no real paths, hosts, or secrets.

**How it fits together:** every service reads its settings from `config.json` through `voicebm_config.py`. The **active** side answers "who is speaking right now?" per utterance; the **passive** side scores ambient audio per node continuously. Both embed with the same Sherpa worker and both write to and match against the same gallery — that shared gallery is the bridge between them. The **global** layer publishes the system-wide control surface and per-person devices. **Emote** (emotion) and **Ambient** (environmental sound) are optional add-ons.

## Contents


**Configuration**

1. [`voicebm_config.py`](#1-voicebm-configpy)

**Active pipeline — live identity, per utterance**

2. [`voicebm_stt_service.py`](#2-voicebm-stt-servicepy)

**Passive pipeline — continuous, per node**

3. [`publish_identity_node.py`](#3-publish-identity-nodepy)
4. [`vad_filter.py`](#4-vad-filterpy)
5. [`voice_clustering.py`](#5-voice-clusteringpy)
6. [`cluster_publisher.py`](#6-cluster-publisherpy)

**Global — system-wide control, discovery, commands**

7. [`voicebm_global_publisher.py`](#7-voicebm-global-publisherpy)
8. [`enrollment_watcher.py`](#8-enrollment-watcherpy)
9. [`mqtt_commands.py`](#9-mqtt-commandspy)

**Workers — per-call inference (subprocess)**

10. [`sherpa_embed.py`](#10-sherpa-embedpy)
11. [`ser_worker.py`](#11-ser-workerpy)

**Emote add-on — Speech Emotion Recognition (active side)**

12. [`voicebm_emote.py`](#12-voicebm-emotepy)

**Ambient add-on — Audio Event Detection (passive side)**

13. [`voicebm_ambient.py`](#13-voicebm-ambientpy)
14. [`voicebm_ambient_hooks.py`](#14-voicebm-ambient-hookspy)
15. [`setup_ambient.py`](#15-setup-ambientpy)

**Thing Engine — post-enrollment identity management**

16. [`thing_engine.py`](#16-thing-enginepy)
17. [`thing_discovery.py`](#17-thing-discoverypy)

**Node management**

18. [`node_engine.py`](#18-node-enginepy)
19. [`setup_node.py`](#19-setup-nodepy)

**Audio server & maintenance**

20. [`audio_server.py`](#20-audio-serverpy)
21. [`retention.py`](#21-retentionpy)
22. [`cleanup_recordings.py`](#22-cleanup-recordingspy)

**Dashboard (debug UI)**

23. [`voicebm_dashboard.py`](#23-voicebm-dashboardpy)

- [Example `config.json`](#example-configjson)


---


# Configuration


## 1. `voicebm_config.py` <a id="1-voicebm-configpy"></a>

_VoiceBM Configuration Module_

```python
# FILE: voicebm_config.py.template
# TYPE: script
################################################################################

#!/usr/bin/env python3
"""
VoiceBM Configuration Module
Centralized configuration loading from config.json
"""

import json
import os
from pathlib import Path


def get_mqtt_config():
    """
    Load MQTT configuration from config.json
    
    Returns:
        dict: MQTT configuration with keys: broker, port, user, password
    """
    config_file = Path("/home/user/voicebm/config.json")
    
    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
            return config['mqtt']
    except FileNotFoundError:
        print(f"Warning: Config file not found at {config_file}")
        return {
            'broker': 'localhost',
            'port': 1883,
            'user': 'mqtt-user',
            'password': ''
        }
    except Exception as e:
        print(f"Warning: Failed to load MQTT config: {e}")
        return {
            'broker': 'localhost',
            'port': 1883,
            'user': 'mqtt-user',
            'password': ''
        }


def get_audio_server_config():
    """
    Load audio server configuration from config.json
    
    Returns:
        dict: Audio server configuration with keys: host, port, base_url
    """
    config_file = Path("/home/user/voicebm/config.json")
    
    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
            return config['audio_server']
    except:
        return {
            'host': 'localhost',
            'port': 9090,
            'base_url': 'http://localhost:9090'
        }


def get_hosts_config():
    """
    Load host addresses from config.json
    
    Returns:
        dict: Host configuration with keys like home_assistant, orin_agx
    """
    config_file = Path("/home/user/voicebm/config.json")
    
    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
            return config.get('hosts', {})
    except:
        return {}


def get_paths_config():
    """
    Load path configuration from config.json
    
    Returns:
        dict: Path configuration
    """
    config_file = Path("/home/user/voicebm/config.json")
    
    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
            return config.get('paths', {})
    except:
        return {
            'voicebm_base': '/home/user/voicebm',
            'enroll_dir': '/home/user/voicebm/enroll',
            'recordings_dir': '/home/user/voicebm/recordings',
            'embeddings_dir': '/home/user/voicebm/embeddings',
            'meta_dir': '/home/user/voicebm/meta',
            'out_dir': '/home/user/voicebm/out',
            'pending_active_dir': '/home/user/voicebm/pending_active',
            'sherpa_bin': '/home/user/.local/bin/sherpa_embed.py',
            'sherpa_model': '/home/user/sherpa_models/nemo_en_titanet_small.onnx'
        }


def get_thresholds_config():
    """
    Load threshold configuration from config.json
    
    Returns:
        dict: Threshold configuration with keys: passive, active
    """
    config_file = Path("/home/user/voicebm/config.json")
    
    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
            return config.get('thresholds', {'passive': 0.22, 'active': 0.50})
    except:
        return {'passive': 0.22, 'active': 0.50}


def get_room_config(room_name):
    """
    Load configuration for a specific room
    
    Args:
        room_name: Name of the room (e.g., 'living', 'bedroom')
    
    Returns:
        dict: Room configuration with keys: rtsp_url, recorder_enabled
    """
    config_file = Path("/home/user/voicebm/config.json")
    
    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
            rooms = config.get('rooms', {})
            return rooms.get(room_name, {})
    except:
        return {}


# ============================================================================
# VOICEBM TUNABLES (v2.0)
# ============================================================================
# General "voicebm" section in config.json holds engine tunables that are not
# MQTT/paths/thresholds/rooms. Defaults below are the safe shipping values.

# Default gallery cap: oldest sample drops off once a person exceeds this many
# enrolled embeddings. Sits in the architect's 50-100 range. This is the drift
# control for auto-enrollment loops: voice naturally adapts as old samples age out.
DEFAULT_GALLERY_MAX = 75

# Default active-pipeline lead trim (milliseconds). 0 = OFF (no trim).
# Set this to roughly the length of the wake-word chime so the chime is stripped
# from the audio BEFORE embedding on the active pipeline. Stored WAV is untouched;
# only the embedding input is trimmed.
DEFAULT_ACTIVE_LEAD_TRIM_MS = 0


def get_voicebm_config():
    """
    Load the general 'voicebm' tunables section from config.json.

    Returns:
        dict: voicebm section (may be empty if not present)
    """
    config_file = Path("/home/user/voicebm/config.json")

    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
            return config.get('voicebm', {})
    except:
        return {}


def get_gallery_max():
    """
    Configurable maximum number of embeddings retained per person gallery.

    Read from config.json -> voicebm.gallery_max. Falls back to
    DEFAULT_GALLERY_MAX if unset or invalid.

    Returns:
        int: gallery cap (>= 1)
    """
    try:
        value = int(get_voicebm_config().get('gallery_max', DEFAULT_GALLERY_MAX))
        if value < 1:
            return DEFAULT_GALLERY_MAX
        return value
    except:
        return DEFAULT_GALLERY_MAX


def get_active_lead_trim_ms():
    """
    Configurable lead-trim in milliseconds for the ACTIVE pipeline.

    Read from config.json -> voicebm.active_lead_trim_ms. Falls back to
    DEFAULT_ACTIVE_LEAD_TRIM_MS (0 = off) if unset or invalid.

    Returns:
        int: milliseconds to strip from the front of active audio before
             embedding (0 = no trim)
    """
    try:
        value = int(get_voicebm_config().get('active_lead_trim_ms', DEFAULT_ACTIVE_LEAD_TRIM_MS))
        if value < 0:
            return 0
        return value
    except:
        return DEFAULT_ACTIVE_LEAD_TRIM_MS


def enforce_gallery_cap(metadata, person_dir, gallery_max=None):
    """
    Enforce the per-person gallery rollover cap (B-05/B-06).

    SHARED UTILITY - called identically by every enrollment path
    (active pending enroll, passive cluster label). One rule, one place.

    Given a person's metadata dict (already containing the freshly-appended
    sample) and that person's enrollment directory, this trims the gallery
    down to gallery_max samples by dropping the OLDEST samples first. For each
    dropped sample it deletes the on-disk embedding (.txt) and recording (.wav)
    referenced by that sample, then returns the updated metadata.

    Sample age is determined by 'enrolled_at' (ISO8601). Samples without an
    'enrolled_at' are treated as oldest (dropped first) so malformed legacy
    entries age out rather than pin the gallery.

    Args:
        metadata: dict with a 'samples' list (each: embedding, recording,
                  enrolled_at, ...). Modified in place and returned.
        person_dir: pathlib.Path to /enroll/{person_id}
        gallery_max: optional override; defaults to get_gallery_max()

    Returns:
        dict: the updated metadata (samples trimmed, total_samples refreshed)
    """
    from pathlib import Path as _Path

    if gallery_max is None:
        gallery_max = get_gallery_max()

    person_dir = _Path(person_dir)
    samples = metadata.get('samples', [])

    if len(samples) <= gallery_max:
        # Nothing to trim; keep total_samples honest and return.
        metadata['total_samples'] = len(samples)
        return metadata

    # Oldest-first ordering. Missing enrolled_at sorts as "" => oldest.
    samples_sorted = sorted(samples, key=lambda s: s.get('enrolled_at', ''))

    drop_count = len(samples_sorted) - gallery_max
    to_drop = samples_sorted[:drop_count]
    to_keep = samples_sorted[drop_count:]

    for sample in to_drop:
        for rel_key in ('embedding', 'recording'):
            rel = sample.get(rel_key)
            if not rel:
                continue
            try:
                fpath = person_dir / rel
                if fpath.exists():
                    fpath.unlink()
            except Exception as e:
                print(f"[gallery_cap] Failed to delete {rel_key} for "
                      f"{sample.get('event_id', '?')}: {e}")
        print(f"[gallery_cap] Rolled off oldest sample: "
              f"{sample.get('event_id', '?')} "
              f"(enrolled_at={sample.get('enrolled_at', 'unknown')})")

    metadata['samples'] = to_keep
    metadata['total_samples'] = len(to_keep)
    print(f"[gallery_cap] Trimmed gallery to {len(to_keep)}/{gallery_max} samples")

    return metadata


def update_voicebm_config_key(key, value):
    """
    Write a single key into the 'voicebm' section of config.json (v2.0 tunables).

    Used by the HA number entities (Gallery Max, Active Lead Trim) so a slider
    change persists across restarts. Reads-modifies-writes the whole file to
    preserve every other setting. Returns True on success.

    Args:
        key: e.g. 'gallery_max' or 'active_lead_trim_ms'
        value: int value to store
    """
    config_file = Path("/home/user/voicebm/config.json")
    try:
        if config_file.exists():
            with open(config_file, 'r') as f:
                config = json.load(f)
        else:
            config = {}
        vb = config.get('voicebm', {})
        vb[key] = value
        config['voicebm'] = vb
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)
        return True
    except Exception as e:
        print(f"Failed to update voicebm.{key} in config.json: {e}")
        return False


if __name__ == "__main__":
    # Test configuration loading
    print("Testing VoiceBM configuration loading...")
    print(f"MQTT Config: {get_mqtt_config()}")
    print(f"Audio Server Config: {get_audio_server_config()}")
    print(f"Thresholds: {get_thresholds_config()}")
    print(f"Gallery Max: {get_gallery_max()}")
    print(f"Active Lead Trim (ms): {get_active_lead_trim_ms()}")



################################################################################
```


# Active pipeline — live identity, per utterance


## 2. `voicebm_stt_service.py` <a id="2-voicebm-stt-servicepy"></a>

_Voice Biometrics MQTT Service - Processes STT analysis requests from Wyoming container_

```python
#!/usr/bin/env python3
"""
Voice Biometrics MQTT Service - Processes STT analysis requests from Wyoming container
Runs on HOST with access to the Sherpa-ONNX conda environment

ACTIVE PIPELINE SCRIPT - Uses slider-controlled threshold (MATCH_T_ACTIVE)
The passive pipeline (publish_identity_living.py) uses MATCH_T_PASSIVE = 0.22.
This script responds to the HA slider for adjustable STT injection threshold.

Features:
- Responds to voice analysis requests from Docker handler.py
- Tracks injection toggle state and includes in response
- Maintains pending buffer (5) for unidentified voices
- Handles enrollment/rejection of pending voices

CRITICAL FIX APPLIED:
- Unknown speakers (speaker_id=None) now map to virtual "user" identity
- "user" blocklist switch now actually blocks unknowns (removed skeleton key)
"""

import os
import json
import time
import shutil
import subprocess
import tempfile
import datetime
from pathlib import Path
import numpy as np
import paho.mqtt.client as mqtt

# Configuration
# MQTT Configuration (centralized)
import sys
sys.path.insert(0, '/home/user/voicebm')
from voicebm_config import get_mqtt_config, update_voicebm_config_key

def get_current_lead_trim_ms():
    """Live CURRENT lead trim (ms) — reads voicebm.current_lead_trim_ms from
    config.json on every call so the HA slider takes effect immediately.
    (Replaces voicebm_config.get_active_lead_trim_ms, which read the legacy
    misnamed key — the trim governs the CURRENT pipeline, never the biopsy.)"""
    try:
        with open("/home/user/voicebm/config.json") as _f:
            return int(json.load(_f).get("voicebm", {}).get("current_lead_trim_ms", 0))
    except Exception:
        return 0

# Emote Edition — optional plug-in
# If voicebm_emote.py is not installed, both functions become no-ops.
# Removing the module file is sufficient to disable the feature entirely.
try:
    from voicebm_emote import run_emote, publish_emote_discovery
    print("[emote] Emote Edition loaded")
except ImportError:
    def run_emote(audio_path, client): pass
    def publish_emote_discovery(client): pass
    print("[emote] Emote Edition not installed — skipping")

mqtt_config = get_mqtt_config()
BROKER = mqtt_config['broker']
PORT = mqtt_config['port']
USER = mqtt_config['user']
PASS = mqtt_config['password']

# UPDATED PATH FOR WRAPPER SCRIPT (under /home/user/voicebm/bin/)
SHERPA_SCRIPT = "/home/user/voicebm/bin/embed_stt.sh"
SHERPA_MODEL = "/home/user/sherpa_models/nemo_en_titanet_small.onnx"

# ACTIVE pipeline lead-trim (ms). 0 = OFF. Strips wake-word chime from the
# front of the audio BEFORE embedding so the chime never contaminates a match
# or a pending enrollment. Stored WAV is never modified.
# Re-read live in create_embedding so the HA slider takes effect without restart.
CURRENT_LEAD_TRIM_MS = get_current_lead_trim_ms()

# GALLERY ROLLOVER CAP:
# Max embedding samples retained per person. When a new enrollment would push
# a person over this count, the OLDEST sample(s) are pruned (oldest by
# enrolled_at). Slider-controlled, stored in thresholds.json as GALLERY_MAX.
# 0 or missing = unlimited (no pruning).
DEFAULT_GALLERY_MAX = 0
ENROLL_DIR = "/home/user/voicebm/enroll"
THRESHOLD_FILE = "/home/user/voicebm/out/thresholds.json"

# THRESHOLD SPLIT:
# - This script uses MATCH_T_ACTIVE (slider-controlled, default 0.50)
# - Passive pipeline uses MATCH_T_PASSIVE = 0.22 (fixed)
DEFAULT_THRESHOLD_ACTIVE = 0.50

REQUEST_TOPIC = "voicebm/stt/analyze_request"
RESPONSE_TOPIC = "voicebm/stt/analyze_response"

# Pending enrollment configuration
PENDING_DIR = Path("/home/user/voicebm/pending_active")
PENDING_RECORDINGS = PENDING_DIR / "recordings"
PENDING_EMBEDDINGS = PENDING_DIR / "embeddings"
PENDING_JSON = PENDING_DIR / "pending.json"
PENDING_BUFFER_SIZE = 5
PENDING_EXPIRE_HOURS = 1

# MQTT Topics
PENDING_TOPIC = "voicebm/pending_active"
PENDING_ENROLL_TOPIC = "voicebm/pending_active/enroll"
PENDING_REJECT_TOPIC = "voicebm/pending_active/reject"
PENDING_CLEAR_TOPIC = "voicebm/pending_active/clear"
INJECT_STATE_TOPIC = "voicebm/inject_identity"

# Dashboard state files (for Flask/OpenWebUI multi-platform sync)
META_DIR = Path("/home/user/voicebm/meta")
SETTINGS_FILE = META_DIR / "settings.json"
ACTIVE_STATE_FILE = META_DIR / "active_state.json"

# Global state
inject_identity_enabled = True
blocked_speakers = set()  # In-memory set of blocked person_ids, populated from MQTT

# Global state for pending enrollment name
pending_person_name = ""

# Track last published person for state clearing (prevents stuck sensors in HA)
last_published_person = None

# Track request_ids that have been processed as biopsy
# Used so full audio knows whether the biopsy already published active identity
# (and falls back to publishing active identity itself if no biopsy ran)
biopsy_seen_ids = set()


def is_speaker_blocked(speaker_id):
    """
    Check if a speaker is on the blocklist.
    
    Uses in-memory set populated from MQTT subscriptions.
    NO file reads - fast and simple.
    
    Args:
        speaker_id: The person_id to check
    
    Returns:
        bool: True if blocked, False otherwise
    """
    if not speaker_id:
        return False
    
    is_blocked = speaker_id in blocked_speakers
    print(f"  [BLOCKLIST] {speaker_id} blocked={is_blocked} (in-memory check)")
    return is_blocked


def handle_blocklist_state(client, userdata, msg):
    """
    Handle blocklist state updates from MQTT.
    Topic pattern: voicebm/blocklist/{person_id}
    Payload: 'ON' or 'OFF'
    """
    global blocked_speakers
    
    try:
        parts = msg.topic.split('/')
        if len(parts) >= 3:
            person_id = parts[2]
            state = msg.payload.decode('utf-8')
            
            if state == "ON":
                blocked_speakers.add(person_id)
                print(f"[BLOCKLIST] Added to blocklist: {person_id}")
            else:
                blocked_speakers.discard(person_id)
                print(f"[BLOCKLIST] Removed from blocklist: {person_id}")
            
            print(f"[BLOCKLIST] Current blocked speakers: {blocked_speakers}")
    except Exception as e:
        print(f"[BLOCKLIST] Error handling state update: {e}")


# ============================================================================
# DASHBOARD STATE FILE WRITERS (Multi-platform sync via filesystem)
# ============================================================================

def write_settings_file():
    """
    Write settings.json for dashboard.
    Syncs injection state and threshold to filesystem for Flask/OpenWebUI access.
    """
    try:
        META_DIR.mkdir(parents=True, exist_ok=True)
        
        # Read current threshold from thresholds.json
        threshold = DEFAULT_THRESHOLD_ACTIVE
        try:
            if os.path.exists(THRESHOLD_FILE):
                with open(THRESHOLD_FILE, 'r') as f:
                    thr = json.load(f)
                    threshold = float(thr.get("MATCH_T_ACTIVE", DEFAULT_THRESHOLD_ACTIVE))
        except:
            pass
        
        settings = {
            "inject_identity": inject_identity_enabled,
            "active_threshold": threshold,
            "last_updated": time.strftime('%Y-%m-%d %H:%M:%S')
        }
        
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(settings, f, indent=2)
            
    except Exception as e:
        print(f"Warning: Could not write settings.json: {e}")


def write_active_state_file(speaker_id, display_name, confidence, decision):
    """
    Write active_state.json for dashboard.
    Syncs current speaker identity to filesystem for Flask/OpenWebUI access.
    """
    try:
        META_DIR.mkdir(parents=True, exist_ok=True)
        
        active_state = {
            "speaker_id": speaker_id,
            "display_name": display_name or "user",
            "confidence": round(confidence, 4),
            "decision": decision,
            "timestamp": time.time(),
            "ts_iso": datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
        }
        
        with open(ACTIVE_STATE_FILE, 'w') as f:
            json.dump(active_state, f, indent=2)
            
    except Exception as e:
        print(f"Warning: Could not write active_state.json: {e}")


def setup_pending_dirs():
    """Create pending enrollment directories."""
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    PENDING_RECORDINGS.mkdir(exist_ok=True)
    PENDING_EMBEDDINGS.mkdir(exist_ok=True)
    
    if not PENDING_JSON.exists():
        save_pending_buffer([])


def load_pending_buffer():
    """Load pending enrollment buffer from JSON."""
    try:
        if PENDING_JSON.exists():
            with open(PENDING_JSON, 'r') as f:
                return json.load(f)
    except Exception as e:
        print(f"Failed to load pending buffer: {e}")
    return []


def save_pending_buffer(buffer):
    """Save pending enrollment buffer to JSON."""
    try:
        with open(PENDING_JSON, 'w') as f:
            json.dump(buffer, f, indent=2)
    except Exception as e:
        print(f"Failed to save pending buffer: {e}")


def cleanup_expired_pending():
    """Remove expired entries from pending buffer."""
    buffer = load_pending_buffer()
    if not buffer:
        return buffer
    
    now_ts = time.time()
    expire_seconds = PENDING_EXPIRE_HOURS * 3600
    
    valid = []
    for entry in buffer:
        entry_ts = entry.get('timestamp', 0)
        if now_ts - entry_ts < expire_seconds:
            valid.append(entry)
        else:
            try:
                wav_path = PENDING_RECORDINGS / f"{entry['id']}.wav"
                emb_path = PENDING_EMBEDDINGS / f"{entry['id']}.txt"
                if wav_path.exists():
                    wav_path.unlink()
                if emb_path.exists():
                    emb_path.unlink()
                print(f"Expired pending entry removed: {entry['id']}")
            except Exception as e:
                print(f"Failed to cleanup expired {entry['id']}: {e}")
    
    if len(valid) != len(buffer):
        save_pending_buffer(valid)
    
    return valid


def add_to_pending_buffer(audio_path, embedding, request_id):
    """Add unidentified voice to pending enrollment buffer."""
    buffer = cleanup_expired_pending()
    
    pending_id = f"active_{int(time.time() * 1000)}"
    
    try:
        wav_dst = PENDING_RECORDINGS / f"{pending_id}.wav"
        emb_dst = PENDING_EMBEDDINGS / f"{pending_id}.txt"
        
        if os.path.exists(audio_path):
            shutil.copy2(audio_path, wav_dst)
        else:
            print(f"Source audio not found: {audio_path}")
            return None
        
        np.savetxt(emb_dst, embedding)
        
        entry = {
            "id": pending_id,
            "request_id": request_id,
            "timestamp": time.time(),
            "ts_iso": datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            "audio_url": f"http://127.0.0.1:9090/pending/{pending_id}.wav",
            "source": "active_node",
        }
        
        buffer.append(entry)
        
        while len(buffer) > PENDING_BUFFER_SIZE:
            removed = buffer.pop(0)
            try:
                old_wav = PENDING_RECORDINGS / f"{removed['id']}.wav"
                old_emb = PENDING_EMBEDDINGS / f"{removed['id']}.txt"
                if old_wav.exists():
                    old_wav.unlink()
                if old_emb.exists():
                    old_emb.unlink()
                print(f"Buffer overflow, removed oldest: {removed['id']}")
            except Exception as e:
                print(f"Failed to remove overflow {removed['id']}: {e}")
        
        save_pending_buffer(buffer)
        print(f"Added to pending buffer: {pending_id} (buffer size: {len(buffer)})")
        
        return entry
        
    except Exception as e:
        print(f"Failed to add to pending buffer: {e}")
        return None


def publish_pending_status(client):
    """
    Publish current pending buffer status to MQTT.

    IMPORTANT CHANGE vs Claude's original:
    - 'current' entry is now the *newest* pending entry (buffer[-1]),
      not the oldest (buffer[0]).
    """
    buffer = load_pending_buffer()
    
    payload = {
        "count": len(buffer),
        "max_size": PENDING_BUFFER_SIZE,
        "expire_hours": PENDING_EXPIRE_HOURS,
        "entries": buffer,
    }
    
    client.publish(PENDING_TOPIC, json.dumps(payload), qos=1, retain=True)
    
    # Surface the NEWEST pending entry as "current"
    if buffer:
        current = buffer[-1]
        client.publish(
            "voicebm/pending_active/current_id",
            current.get("id", ""),
            qos=1,
            retain=True,
        )
        client.publish(
            "voicebm/pending_active/audio_url",
            current.get("audio_url", ""),
            qos=1,
            retain=True,
        )
    else:
        client.publish("voicebm/pending_active/current_id", "none", qos=1, retain=True)
        client.publish("voicebm/pending_active/audio_url", "", qos=1, retain=True)
    
    print(f"Published pending status: {len(buffer)} entries")


def load_gallery():
    """Load enrolled speakers and compute centroids."""
    people = {}
    enroll_path = Path(ENROLL_DIR)
    
    if not enroll_path.exists():
        print(f"Warning: Enrollment directory not found at /home/user/voicebm/enroll")
        return {}
    
    try:
        for person_dir in enroll_path.iterdir():
            if not person_dir.is_dir():
                continue
            
            person_id = person_dir.name
            embeddings_dir = person_dir / "embeddings"
            metadata_file = person_dir / "metadata.json"
            
            if metadata_file.exists():
                try:
                    with open(metadata_file, "r") as f:
                        metadata = json.load(f)
                        display_name = metadata.get(
                            "display_name", person_id.replace("_", " ").title()
                        )
                except:
                    display_name = person_id.replace("_", " ").title()
            else:
                display_name = person_id.replace("_", " ").title()
            
            if not embeddings_dir.exists():
                continue
            
            vectors = []
            for emb_file in embeddings_dir.glob("*.txt"):
                try:
                    v = np.loadtxt(emb_file)
                    if v is not None and len(v) > 0:
                        vectors.append(v)
                except Exception as e:
                    print(f"  Failed to load {emb_file.name}: {e}")
            
            if vectors:
                people[(person_id, display_name)] = vectors
    
    except Exception as e:
        print(f"Error loading gallery: {e}")
        return {}
    
    cents = {}
    for (sid, name), vecs in people.items():
        cents[(sid, name)] = np.mean(vecs, axis=0)
    
    print(f"Loaded {len(cents)} enrolled speakers")
    return cents


def make_lead_trimmed_wav(wav_path, trim_ms):
    """
    Write a copy of wav_path with the first trim_ms milliseconds removed.

    Uses the stdlib wave module (no extra dependencies). Returns the path to a
    new temp WAV the caller is responsible for deleting. If trimming is not
    possible (trim_ms <= 0, or the clip is shorter than the trim), returns None
    so the caller falls back to the original untrimmed audio.

    The source WAV on disk is never modified.
    """
    if trim_ms <= 0:
        return None

    import wave

    try:
        with wave.open(wav_path, 'rb') as wf:
            n_channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            framerate = wf.getframerate()
            n_frames = wf.getnframes()

            trim_frames = int(framerate * (trim_ms / 1000.0))

            # If the clip is shorter than (or equal to) the trim, do not trim;
            # embedding silence/nothing is worse than embedding the whole clip.
            if trim_frames <= 0 or trim_frames >= n_frames:
                print(f"  [TRIM] Skipped: trim {trim_ms}ms >= clip length "
                      f"({n_frames} frames @ {framerate}Hz)")
                return None

            wf.setpos(trim_frames)
            remaining = wf.readframes(n_frames - trim_frames)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            trimmed_path = tmp.name

        with wave.open(trimmed_path, 'wb') as out:
            out.setnchannels(n_channels)
            out.setsampwidth(sampwidth)
            out.setframerate(framerate)
            out.writeframes(remaining)

        print(f"  [TRIM] Stripped {trim_ms}ms ({trim_frames} frames) "
              f"from lead before embedding")
        return trimmed_path

    except Exception as e:
        print(f"  [TRIM] Failed to trim lead ({e}); using untrimmed audio")
        return None


def get_gallery_max():
    """Read GALLERY_MAX from thresholds.json. 0/missing = unlimited."""
    try:
        if os.path.exists(THRESHOLD_FILE):
            with open(THRESHOLD_FILE, "r") as f:
                return int(json.load(f).get("GALLERY_MAX", DEFAULT_GALLERY_MAX))
    except Exception:
        pass
    return DEFAULT_GALLERY_MAX


def enforce_gallery_cap(person_dir, metadata):
    """
    Trim a person's gallery to GALLERY_MAX samples, dropping the OLDEST first.

    Operates on metadata['samples'] (each entry has 'enrolled_at', 'embedding',
    and optional 'recording' relative paths). Deletes the pruned embedding .txt
    and .wav files from disk, updates metadata in place, and returns it.

    No-op when GALLERY_MAX <= 0 (unlimited) or sample count is within the cap.
    Pure filesystem + metadata; does NOT touch the live gallery centroids (the
    caller reloads the gallery after enrollment).
    """
    cap = get_gallery_max()
    samples = metadata.get("samples", [])
    if cap <= 0 or len(samples) <= cap:
        return metadata

    # Oldest first. Entries without enrolled_at sort to the front (treated oldest).
    ordered = sorted(samples, key=lambda s: s.get("enrolled_at", ""))
    drop_count = len(ordered) - cap
    to_drop = ordered[:drop_count]
    keep = ordered[drop_count:]

    for s in to_drop:
        for rel_key in ("embedding", "recording"):
            rel = s.get(rel_key)
            if not rel:
                continue
            fpath = Path(person_dir) / rel
            try:
                if fpath.exists():
                    fpath.unlink()
                    print(f"  [gallery_cap] Pruned {rel_key}: {fpath.name}")
            except Exception as e:
                print(f"  [gallery_cap] Failed to prune {fpath}: {e}")

    metadata["samples"] = keep
    metadata["total_samples"] = len(keep)
    print(f"  [gallery_cap] Trimmed gallery to {len(keep)}/{cap} samples")
    return metadata


def create_embedding(wav_path):
    """Create embedding using Sherpa-ONNX via bash wrapper.

    PURE EMBEDDING — no audio surgery in here. Trimming is the CURRENT
    pipeline's concern and happens at the call site. The biopsy is embedded
    exactly as the handler delivered it (its lead was already handled by
    handler.py); the full utterance arrives here already trimmed.
    """
    try:
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
            embedding_path = tmp.name
        
        result = subprocess.run(
            [SHERPA_SCRIPT, wav_path, embedding_path],
            capture_output=True,
            text=True,
            timeout=30,
        )
        
        if result.returncode != 0:
            print(f"Sherpa embedding failed: {result.stderr}")
            # embed_stt.sh routes the worker's stderr to stdout (2>&1) —
            # the actual python error lives HERE, not in stderr.
            if result.stdout:
                print(f"  [worker output] {result.stdout}")
            return None
        
        embedding = np.loadtxt(embedding_path)
        os.unlink(embedding_path)
        
        return embedding
        
    except Exception as e:
        print(f"Embedding creation failed: {e}")
        return None


def cosine_similarity(a, b):
    """Calculate cosine similarity."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


# ============================================================================
# PER-PERSON THRESHOLD OVERRIDE SUPPORT
# ============================================================================

# Cache for per-person thresholds (updated via MQTT subscription)
person_thresholds = {}


def get_person_threshold(person_id, global_threshold):
    """
    Get threshold for a specific person.
    
    Returns per-person threshold if set, otherwise returns global threshold.
    
    Args:
        person_id: Person identifier
        global_threshold: Fallback global threshold
    
    Returns:
        Threshold value to use for this person
    """
    if person_id in person_thresholds:
        custom = person_thresholds[person_id]
        print(f"  Using custom threshold for {person_id}: {custom:.2f}")
        return custom
    return global_threshold


def verify_person_threshold(speaker_id, confidence, global_threshold):
    """
    Verify that identified speaker meets their custom threshold (if set).
    
    If person has custom threshold and confidence doesn't meet it,
    returns None (treat as unknown).
    
    Args:
        speaker_id: Identified speaker ID
        confidence: Confidence score from identification
        global_threshold: Global threshold used for initial identification
    
    Returns:
        speaker_id if threshold met, None if custom threshold not met
    """
    if speaker_id is None:
        return None
    
    # Check if person has custom threshold
    if speaker_id in person_thresholds:
        custom_threshold = person_thresholds[speaker_id]
        if confidence < custom_threshold:
            print(f"  Custom threshold check FAILED: {confidence:.4f} < {custom_threshold:.2f} for {speaker_id}")
            return None  # Reject match - doesn't meet person's custom threshold
    
    return speaker_id


def identify_speaker(embedding, gallery, threshold):
    """Identify speaker by comparing embedding against gallery."""
    if embedding is None or not gallery:
        return None, None, 0.0
    
    best_sid = None
    best_name = None
    best_sim = -1.0
    
    all_matches = []
    
    for (person_id, display_name), centroid in gallery.items():
        sim = cosine_similarity(embedding, centroid)
        all_matches.append((person_id, display_name, sim))
        if sim > best_sim:
            best_sim = sim
            best_sid = person_id
            best_name = display_name
    
    all_matches.sort(key=lambda x: x[2], reverse=True)
    
    print("  Match candidates:")
    for pid, pname, sim in all_matches[:5]:
        marker = "[BEST]" if pid == best_sid else "      "
        above_threshold = "PASS" if sim >= threshold else "FAIL"
        print(f"    {marker} {above_threshold} {pname:20s} ({pid:15s}) = {sim:.4f}")
    
    if best_sim >= threshold:
        print(f"  [MATCH] Identified: {best_name} ({best_sid}) confidence={best_sim:.4f}")
        return best_sid, best_name, best_sim
    else:
        print(f"  No match (best={best_sim:.4f} < threshold={threshold})")
        return None, None, best_sim


def publish_discovery(client):
    """Publish MQTT Discovery for pending enrollment controls under VoiceBM device."""
    discovery_prefix = "homeassistant"
    
    device = {
        "identifiers": ["voicebm"],
        "name": "Voice Biometrics",
        "manufacturer": "David M. Dryver Sr.",
        "model": "Home Assistant Voice Biometrics",
        "sw_version": "2.0"
    }
    
    # Pending Active Voices count sensor
    pending_count_config = {
        "name": "Pending Active Voices",
        "unique_id": "voicebm_pending_active_count",
        "state_topic": PENDING_TOPIC,
        "value_template": "{{ value_json.count }}",
        "json_attributes_topic": PENDING_TOPIC,
        "icon": "mdi:account-question",
        "device": device,
    }
    
    client.publish(
        f"{discovery_prefix}/sensor/voicebm_pending_active_count/config",
        json.dumps(pending_count_config),
        qos=1,
        retain=True,
    )
    
    # Pending Active Audio URL sensor
    pending_audio_config = {
        "name": "Pending Active Audio URL",
        "unique_id": "voicebm_pending_active_audio_url",
        "state_topic": "voicebm/pending_active/audio_url",
        "icon": "mdi:volume-high",
        "device": device,
    }
    
    client.publish(
        f"{discovery_prefix}/sensor/voicebm_pending_active_audio_url/config",
        json.dumps(pending_audio_config),
        qos=1,
        retain=True,
    )
    
    # Pending Active ID sensor
    pending_id_config = {
        "name": "Pending Active ID",
        "unique_id": "voicebm_pending_active_id",
        "state_topic": "voicebm/pending_active/current_id",
        "icon": "mdi:identifier",
        "device": device,
    }
    
    client.publish(
        f"{discovery_prefix}/sensor/voicebm_pending_active_id/config",
        json.dumps(pending_id_config),
        qos=1,
        retain=True,
    )
    
    # Text input for person name to enroll pending voice as
    pending_name_config = {
        "name": "Pending Person Name",
        "unique_id": "voicebm_pending_person_name",
        "command_topic": "voicebm/pending_active/person_name/set",
        "state_topic": "voicebm/pending_active/person_name",
        "icon": "mdi:account-edit",
        "device": device,
    }
    
    client.publish(
        f"{discovery_prefix}/text/voicebm_pending_person_name/config",
        json.dumps(pending_name_config),
        qos=1,
        retain=True,
    )
    
    # Initialize pending person name
    client.publish("voicebm/pending_active/person_name", "", qos=1, retain=True)
    
    # Enroll Pending button
    enroll_btn_config = {
        "name": "Enroll Pending Voice",
        "unique_id": "voicebm_pending_enroll_btn",
        "command_topic": "voicebm/pending_active/enroll_btn",
        "payload_press": "PRESS",
        "icon": "mdi:account-plus",
        "device": device,
    }
    
    client.publish(
        f"{discovery_prefix}/button/voicebm_pending_enroll_btn/config",
        json.dumps(enroll_btn_config),
        qos=1,
        retain=True,
    )
    
    # Reject Pending button
    reject_btn_config = {
        "name": "Reject Pending Voice",
        "unique_id": "voicebm_pending_reject_btn",
        "command_topic": "voicebm/pending_active/reject_btn",
        "payload_press": "PRESS",
        "icon": "mdi:account-remove",
        "device": device,
    }
    
    client.publish(
        f"{discovery_prefix}/button/voicebm_pending_reject_btn/config",
        json.dumps(reject_btn_config),
        qos=1,
        retain=True,
    )
    
    # Play Pending Audio button
    play_btn_config = {
        "name": "Play Pending Audio",
        "unique_id": "voicebm_pending_play_btn",
        "command_topic": "voicebm/pending_active/play_btn",
        "payload_press": "PRESS",
        "icon": "mdi:play-circle",
        "device": device,
    }
    
    client.publish(
        f"{discovery_prefix}/button/voicebm_pending_play_btn/config",
        json.dumps(play_btn_config),
        qos=1,
        retain=True,
    )
    
    # Clear All Pending button
    clear_btn_config = {
        "name": "Clear All Pending",
        "unique_id": "voicebm_pending_clear_btn",
        "command_topic": "voicebm/pending_active/clear",
        "payload_press": "PRESS",
        "icon": "mdi:delete-sweep",
        "device": device,
    }
    
    client.publish(
        f"{discovery_prefix}/button/voicebm_pending_clear_btn/config",
        json.dumps(clear_btn_config),
        qos=1,
        retain=True,
    )
    
    # Active Identity Entities (8) - Show STT analysis results
    # These mirror what passive nodes publish but for the active STT pipeline
    
    # 1. Active Speaker (display name) — plain string, sourced from biopsy path
    active_speaker_config = {
        "name": "Active Speaker",
        "unique_id": "voicebm_active_speaker",
        "state_topic": "voicebm/active_speaker",
        "icon": "mdi:account-voice",
        "device": device,
    }
    client.publish(
        f"{discovery_prefix}/sensor/voicebm_active_speaker/config",
        json.dumps(active_speaker_config),
        qos=1,
        retain=True,
    )
    client.publish("voicebm/active_speaker", "none", qos=1)

    # Reset voicebm/active/identity so stale retained user state does not leak
    # into HA while it transitions from old discovery config to new plain-string topics
    reset_identity_data = {
        "speaker_id": "none",
        "display_name": "none",
        "confidence": 0.0,
        "decision": "none",
        "score": 0.0
    }
    client.publish("voicebm/active/identity", json.dumps(reset_identity_data), qos=1, retain=True)

    # 2. Active Speaker ID — plain string, sourced from biopsy path
    active_speaker_id_config = {
        "name": "Active Speaker ID",
        "unique_id": "voicebm_active_speaker_id",
        "state_topic": "voicebm/active_speaker_id",
        "icon": "mdi:identifier",
        "device": device,
    }
    client.publish(
        f"{discovery_prefix}/sensor/voicebm_active_speaker_id/config",
        json.dumps(active_speaker_id_config),
        qos=1,
        retain=True,
    )
    client.publish("voicebm/active_speaker_id", "none", qos=1)

    # Current Speaker ID — plain string, companion to voicebm/current_speaker
    current_speaker_id_config = {
        "name": "Current Speaker ID",
        "unique_id": "voicebm_current_speaker_id",
        "state_topic": "voicebm/current_speaker_id",
        "icon": "mdi:identifier",
        "device": device,
    }
    client.publish(
        f"{discovery_prefix}/sensor/voicebm_current_speaker_id/config",
        json.dumps(current_speaker_id_config),
        qos=1,
        retain=True,
    )
    client.publish("voicebm/current_speaker_id", "none", qos=1, retain=True)
    
    # 3. Active Confidence
    active_confidence_config = {
        "name": "Active Voice Confidence",
        "unique_id": "voicebm_active_confidence",
        "state_topic": "voicebm/active/identity",
        "value_template": "{{ (value_json.confidence * 100) | round(1) }}",
        "unit_of_measurement": "%",
        "icon": "mdi:percent",
        "device": device,
    }
    client.publish(
        f"{discovery_prefix}/sensor/voicebm_active_confidence/config",
        json.dumps(active_confidence_config),
        qos=1,
        retain=True,
    )
    
    # 4. Active Decision
    active_decision_config = {
        "name": "Active Voice Decision",
        "unique_id": "voicebm_active_decision",
        "state_topic": "voicebm/active/identity",
        "value_template": "{{ value_json.decision }}",
        "icon": "mdi:check-decagram",
        "device": device,
    }
    client.publish(
        f"{discovery_prefix}/sensor/voicebm_active_decision/config",
        json.dumps(active_decision_config),
        qos=1,
        retain=True,
    )
    
    # 5. Active Score
    active_score_config = {
        "name": "Active Voice Score",
        "unique_id": "voicebm_active_score",
        "state_topic": "voicebm/active/identity",
        "value_template": "{{ value_json.score | round(2) if value_json.score else 0.0 }}",
        "unit_of_measurement": "score",
        "icon": "mdi:chart-line",
        "device": device,
    }
    client.publish(
        f"{discovery_prefix}/sensor/voicebm_active_score/config",
        json.dumps(active_score_config),
        qos=1,
        retain=True,
    )
    
    # 6. Active Voice Accepted (binary sensor - Detected/Unknown)
    active_accepted_config = {
        "name": "Active Voice Accepted",
        "unique_id": "voicebm_active_accepted",
        "state_topic": "voicebm/active/identity",
        "value_template": "{{ 'Detected' if value_json.decision == 'accepted' else 'Unknown' }}",
        "icon": "mdi:check-circle",
        "device": device,
    }
    client.publish(
        f"{discovery_prefix}/sensor/voicebm_active_accepted/config",
        json.dumps(active_accepted_config),
        qos=1,
        retain=True,
    )
    
    # 7. Active Unprocessed Samples (placeholder - set to 0 for now)
    active_unprocessed_config = {
        "name": "Active Unprocessed Samples",
        "unique_id": "voicebm_active_unprocessed",
        "state_topic": "voicebm/active/unprocessed_samples",
        "icon": "mdi:file-question",
        "device": device,
    }
    client.publish(
        f"{discovery_prefix}/sensor/voicebm_active_unprocessed/config",
        json.dumps(active_unprocessed_config),
        qos=1,
        retain=True,
    )
    # Initialize to 0
    client.publish("voicebm/active/unprocessed_samples", "0", qos=1, retain=True)
    
    # 8. Active Current Event ID
    active_event_id_config = {
        "name": "Active Current Event ID",
        "unique_id": "voicebm_active_event_id",
        "state_topic": "voicebm/active/current_event_id",
        "icon": "mdi:file-document",
        "device": device,
    }
    client.publish(
        f"{discovery_prefix}/sensor/voicebm_active_event_id/config",
        json.dumps(active_event_id_config),
        qos=1,
        retain=True,
    )
    
    # Active Match Threshold Number Input (adjustable STT security threshold)
    active_threshold_config = {
        "name": "Active Match Threshold",
        "unique_id": "voicebm_active_threshold",
        "command_topic": "voicebm/active/threshold/set",
        "state_topic": "voicebm/active/threshold",
        "min": 0.01,
        "max": 1.00,
        "step": 0.01,
        "mode": "slider",
        "icon": "mdi:tune-vertical",
        "device": device,
    }
    client.publish(
        f"{discovery_prefix}/number/voicebm_active_threshold/config",
        json.dumps(active_threshold_config),
        qos=1,
        retain=True,
    )
    
    # Initialize active threshold from thresholds.json
    try:
        with open(THRESHOLD_FILE, 'r') as f:
            thr = json.load(f)
            active_threshold_value = float(thr.get("MATCH_T_ACTIVE", DEFAULT_THRESHOLD_ACTIVE))
    except:
        active_threshold_value = DEFAULT_THRESHOLD_ACTIVE
    
    client.publish("voicebm/active/threshold", str(active_threshold_value), qos=1, retain=True)
    print(f"  Initialized active threshold: {active_threshold_value}")
    # Current Lead Trim Number Input - ms stripped from front of the CURRENT (full utterance) artifact
    # audio before embedding, to drop the wake-word chime. 0 = OFF.
    # NOTE: config key + topics say "active" — that naming is LEGACY and WRONG.
    # This trim governs the CURRENT pipeline only (full utterance / enrollment
    # artifact). The biopsy (ACTIVE) is never trimmed. Key/topic names kept to
    # avoid orphaning HA retained state; display name tells the truth.
    lead_trim_config = {
        "name": "Current Lead Trim",
        "unique_id": "voicebm_active_lead_trim",
        "command_topic": "voicebm/active/lead_trim/set",
        "state_topic": "voicebm/active/lead_trim",
        "min": 0,
        "max": 2000,
        "step": 50,
        "mode": "slider",
        "unit_of_measurement": "ms",
        "icon": "mdi:content-cut",
        "device": device,
    }
    client.publish(
        f"{discovery_prefix}/number/voicebm_active_lead_trim/config",
        json.dumps(lead_trim_config),
        qos=1,
        retain=True,
    )
    client.publish("voicebm/active/lead_trim", str(get_current_lead_trim_ms()), qos=1, retain=True)
    print(f"  Initialized CURRENT lead trim: {get_current_lead_trim_ms()} ms (voicebm.current_lead_trim_ms)")

    # Gallery Max Number Input (rollover cap: max samples per person, 0=unlimited)
    gallery_max_config = {
        "name": "Gallery Max",
        "unique_id": "voicebm_gallery_max",
        "command_topic": "voicebm/gallery_max/set",
        "state_topic": "voicebm/gallery_max",
        "min": 0,
        "max": 200,
        "step": 1,
        "mode": "box",
        "unit_of_measurement": "samples",
        "icon": "mdi:image-multiple",
        "device": device,
    }
    client.publish(
        f"{discovery_prefix}/number/voicebm_gallery_max/config",
        json.dumps(gallery_max_config),
        qos=1,
        retain=True,
    )
    client.publish("voicebm/gallery_max", str(get_gallery_max()), qos=1, retain=True)
    print(f"  Initialized gallery max: {get_gallery_max()}")
    
    # Aggregate Blocklist sensor (B-04)
    blocklist_state_config = {
        "name": "Blocklist State",
        "unique_id": "voicebm_blocklist_state",
        "state_topic": "voicebm/blocklist_state",
        "value_template": "{{ value_json.values() | select('equalto', true) | list | count }}",
        "json_attributes_topic": "voicebm/blocklist_state",
        "unit_of_measurement": "blocked",
        "icon": "mdi:account-cancel",
        "device": device,
    }
    client.publish(
        f"{discovery_prefix}/sensor/voicebm_blocklist_state/config",
        json.dumps(blocklist_state_config),
        qos=1,
        retain=True,
    )

    
    print("Published MQTT Discovery for pending enrollment controls + Active Identity entities + Active Threshold")


def handle_pending_enroll(client, userdata, msg):
    """Handle enrollment command for pending active voice."""
    try:
        data = json.loads(msg.payload.decode("utf-8"))
        pending_id = data.get("id")
        person_id = data.get("person_id", "").strip().lower().replace(" ", "_")
        display_name = data.get("display_name", "").strip()
        
        if not pending_id or not person_id or not display_name:
            print("Enroll command missing required fields")
            return
        
        print(f"Enrolling pending {pending_id} as {display_name} ({person_id})")
        
        buffer = load_pending_buffer()
        entry = None
        for e in buffer:
            if e["id"] == pending_id:
                entry = e
                break
        
        if not entry:
            print(f"Pending entry not found: {pending_id}")
            return
        
        wav_src = PENDING_RECORDINGS / f"{pending_id}.wav"
        emb_src = PENDING_EMBEDDINGS / f"{pending_id}.txt"
        
        if not wav_src.exists() or not emb_src.exists():
            print(f"Pending files not found for {pending_id}")
            return
        
        person_dir = Path(ENROLL_DIR) / person_id
        embeddings_dir = person_dir / "embeddings"
        recordings_dir = person_dir / "recordings"
        
        person_dir.mkdir(parents=True, exist_ok=True)
        embeddings_dir.mkdir(exist_ok=True)
        recordings_dir.mkdir(exist_ok=True)
        
        metadata_file = person_dir / "metadata.json"
        if metadata_file.exists():
            with open(metadata_file, "r") as f:
                metadata = json.load(f)
                existing_samples = metadata.get("samples", [])
        else:
            metadata = {
                "person_id": person_id,
                "display_name": display_name,
                "created_at": datetime.datetime.utcnow()
                .replace(microsecond=0)
                .isoformat()
                + "Z",
            }
            existing_samples = []
        
        event_id = pending_id
        emb_dst = embeddings_dir / f"{event_id}.txt"
        rec_dst = recordings_dir / f"{event_id}.wav"
        
        expire_at = (
            datetime.datetime.utcfromtimestamp(time.time() + 3 * 24 * 3600)
            .replace(microsecond=0)
            .isoformat()
            + "Z"
        )
        
        try:
            shutil.move(str(emb_src), str(emb_dst))
            shutil.move(str(wav_src), str(rec_dst))
            print(f"Moved files to enrollment: {event_id}")
        except Exception as e:
            print(f"Failed to move files: {e}")
            return
        
        sample_entry = {
            "event_id": event_id,
            "embedding": f"embeddings/{event_id}.txt",
            "recording": f"recordings/{event_id}.wav",
            "enrolled_at": datetime.datetime.utcnow()
            .replace(microsecond=0)
            .isoformat()
            + "Z",
            "expire_at": expire_at,
            "retention_days": 3,
            "source": "active_node",
        }
        
        metadata["samples"] = existing_samples + [sample_entry]
        metadata["last_updated"] = (
            datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
        )
        metadata["total_samples"] = len(metadata["samples"])
        
        with open(metadata_file, "w") as f:
            json.dump(metadata, f, indent=2)
        
        buffer = [e for e in buffer if e["id"] != pending_id]
        save_pending_buffer(buffer)
        
        # Refresh gallery so new enrollment is immediately used
        userdata["gallery"] = load_gallery()
        
        publish_pending_status(client)
        
        response = {
            "success": True,
            "pending_id": pending_id,
            "person_id": person_id,
            "display_name": display_name,
            "total_samples": metadata["total_samples"],
        }
        client.publish(f"voicebm/pending_active/enroll/response", json.dumps(response), qos=1)
        
        print(f"Successfully enrolled {pending_id} as {display_name}")
        
    except Exception as e:
        print(f"Error handling enroll command: {e}")
        import traceback

        traceback.print_exc()


def handle_pending_reject(client, userdata, msg):
    """Handle rejection command for pending active voice."""
    try:
        data = json.loads(msg.payload.decode("utf-8"))
        pending_id = data.get("id")
        
        if not pending_id:
            print("Reject command missing id")
            return
        
        print(f"Rejecting pending: {pending_id}")
        
        try:
            wav_path = PENDING_RECORDINGS / f"{pending_id}.wav"
            emb_path = PENDING_EMBEDDINGS / f"{pending_id}.txt"
            if wav_path.exists():
                wav_path.unlink()
            if emb_path.exists():
                emb_path.unlink()
        except Exception as e:
            print(f"Failed to delete files for {pending_id}: {e}")
        
        buffer = load_pending_buffer()
        buffer = [e for e in buffer if e["id"] != pending_id]
        save_pending_buffer(buffer)
        
        publish_pending_status(client)
        
        response = {"success": True, "rejected_id": pending_id}
        client.publish(f"voicebm/pending_active/reject/response", json.dumps(response), qos=1)
        
        print(f"Successfully rejected {pending_id}")
        
    except Exception as e:
        print(f"Error handling reject command: {e}")


def handle_pending_clear(client, userdata, msg):
    """Clear all pending entries."""
    try:
        print("Clearing all pending entries")
        
        buffer = load_pending_buffer()
        
        for entry in buffer:
            try:
                wav_path = PENDING_RECORDINGS / f"{entry['id']}.wav"
                emb_path = PENDING_EMBEDDINGS / f"{entry['id']}.txt"
                if wav_path.exists():
                    wav_path.unlink()
                if emb_path.exists():
                    emb_path.unlink()
            except Exception as e:
                print(f"Failed to delete {entry['id']}: {e}")
        
        save_pending_buffer([])
        publish_pending_status(client)
        
        print(f"Cleared {len(buffer)} pending entries")
        
    except Exception as e:
        print(f"Error handling clear command: {e}")


def handle_person_name_set(client, userdata, msg):
    """Handle person name text input for pending enrollment."""
    global pending_person_name
    
    try:
        pending_person_name = msg.payload.decode("utf-8").strip()
        
        client.publish(
            "voicebm/pending_active/person_name",
            pending_person_name,
            qos=1,
            retain=True,
        )
        
        print(f"Pending person name set to: '{pending_person_name}'")
        
    except Exception as e:
        print(f"Error handling person name set: {e}")


def handle_enroll_button(client, userdata, msg):
    """
    Handle enroll button press.

    CHANGE: uses the NEWEST pending entry (buffer[-1]) to match
    what we surface as 'current' in publish_pending_status().
    """
    global pending_person_name
    
    try:
        buffer = load_pending_buffer()
        
        if not buffer:
            print("Enroll button pressed but no pending entries")
            return
        
        if not pending_person_name:
            print("Enroll button pressed but no person name set")
            return
        
        # Use newest pending entry
        current = buffer[-1]
        pending_id = current["id"]
        
        person_id = pending_person_name.lower().replace(" ", "_")
        display_name = pending_person_name.title()
        
        print(f"Enrolling pending {pending_id} as {display_name} ({person_id})")
        
        enroll_data = {
            "id": pending_id,
            "person_id": person_id,
            "display_name": display_name,
        }
        
        class MockMsg:
            def __init__(self, payload):
                self.payload = payload
        
        mock_msg = MockMsg(json.dumps(enroll_data).encode("utf-8"))
        handle_pending_enroll(client, userdata, mock_msg)
        
        pending_person_name = ""
        client.publish(
            "voicebm/pending_active/person_name", "", qos=1, retain=True
        )
        
    except Exception as e:
        print(f"Error handling enroll button: {e}")
        import traceback

        traceback.print_exc()


def handle_reject_button(client, userdata, msg):
    """
    Handle reject button press.

    CHANGE: rejects the NEWEST pending entry (buffer[-1]),
    to stay consistent with what HA is showing as 'current'.
    """
    try:
        buffer = load_pending_buffer()
        
        if not buffer:
            print("Reject button pressed but no pending entries")
            return
        
        current = buffer[-1]
        pending_id = current["id"]
        
        print(f"Rejecting pending {pending_id}")
        
        reject_data = {"id": pending_id}
        
        class MockMsg:
            def __init__(self, payload):
                self.payload = payload
        
        mock_msg = MockMsg(json.dumps(reject_data).encode("utf-8"))
        handle_pending_reject(client, userdata, mock_msg)
        
    except Exception as e:
        print(f"Error handling reject button: {e}")


def handle_play_button(client, userdata, msg):
    """
    Handle play button press.

    CHANGE: plays the NEWEST pending entry (buffer[-1]),
    again matching the surfaced 'current'.
    """
    try:
        buffer = load_pending_buffer()
        
        if not buffer:
            print("Play button pressed but no pending entries")
            return
        
        current = buffer[-1]
        audio_url = current.get("audio_url", "")
        
        if audio_url:
            client.publish(
                "voicebm/pending_active/play_trigger", audio_url, qos=1
            )
            print(f"Play triggered: {audio_url}")
        else:
            print("No audio URL for pending entry")
        
    except Exception as e:
        print(f"Error handling play button: {e}")


def handle_analysis_request(client, userdata, msg):
    """Process voice biometrics analysis request."""
    global inject_identity_enabled, last_published_person, biopsy_seen_ids
    
    try:
        request = json.loads(msg.payload.decode("utf-8"))
        request_id = request.get("request_id")
        audio_path = request.get("audio_path")
        
        print(f"\nAnalysis request: {request_id}")
        print(f"  Audio: {audio_path}")
        
        if not audio_path or not os.path.exists(audio_path):
            print("  Audio file not found")
            return

        # Determine whether this is a biopsy (early identity) or full audio (current speaker)
        # Biopsy filename always contains '_biopsy' (set by handler.py)
        # Full audio that arrives with no prior biopsy (short utterance) falls back to
        # publishing active identity so the primitives don't go stale
        is_biopsy = "_biopsy" in os.path.basename(audio_path)
        is_full_audio = not is_biopsy
        
        if is_biopsy:
            biopsy_seen_ids.add(request_id)
            if len(biopsy_seen_ids) > 50:
                biopsy_seen_ids.clear()
        
        # Publish active identity on biopsy, OR on full audio when no biopsy ran (short utterance)
        should_publish_active = is_biopsy or (is_full_audio and request_id not in biopsy_seen_ids)
        
        # Clear current_speaker at utterance start - new enrollment sample incoming
        # Active identity sensors are NOT cleared here; biopsy populates them
        client.publish("voicebm/current_speaker", "none", qos=1, retain=True)
        
        # Clear previous person's binary sensor BEFORE identifying new speaker
        # This ensures OFF->ON state change even if same person speaks twice
        # Prevents stuck sensors in Home Assistant automations
        if should_publish_active:
            if last_published_person:
                print(f"  Clearing previous sensor: {last_published_person}/voice")
                client.publish(f"{last_published_person}/voice", "OFF", qos=1, retain=True)
                time.sleep(0.05)  # 50ms for HA to register OFF state
        
        # Load ACTIVE threshold (slider-controlled)
        try:
            with open(THRESHOLD_FILE, "r") as f:
                thr = json.load(f)
                threshold = float(thr.get("MATCH_T_ACTIVE", DEFAULT_THRESHOLD_ACTIVE))
                print(
                    f"  Using STT threshold: {threshold:.2f} "
                    f"(from thresholds.json MATCH_T_ACTIVE)"
                )
        except Exception as e:
            threshold = DEFAULT_THRESHOLD_ACTIVE
            print(
                f"  Using STT threshold: {threshold:.2f} "
                f"(default, file read failed: {e})"
            )
        
        # ── TWO JOBS, TWO TREATMENTS ──────────────────────────────────────
        # ACTIVE (biopsy): identity triage. Embed the slice exactly as the
        # handler delivered it, answer the gate, then DESTROY the sample.
        # A biopsy is lab waste once the chart is written — never stored,
        # never enrolled, never enters pending_active.
        #
        # CURRENT (full utterance): the considered record. Trim the wake
        # (live adjustable — HA slider / voicebm.current_lead_trim_ms), full
        # embed of the trimmed clip, full match. The TRIMMED clip is the only
        # enrollment-grade tissue; it alone enters pending_active. If trimming
        # leaves nothing, the finding is 'user' — the biopsy already took
        # everything there was to see.
        trimmed_tmp = None
        too_short = False
        embedding = None

        if is_biopsy:
            embedding = create_embedding(audio_path)
            if embedding is None:
                print("  Failed to create embedding")
                return
        else:
            trim_ms = get_current_lead_trim_ms()
            if trim_ms > 0:
                trimmed_tmp = make_lead_trimmed_wav(audio_path, trim_ms)
                too_short = trimmed_tmp is None
            embed_source = trimmed_tmp if trimmed_tmp else audio_path
            if too_short:
                print("  [TRIM] Nothing left after wake trim — current speaker = user")
            else:
                embedding = create_embedding(embed_source)
                if embedding is None:
                    print("  Failed to create embedding")
                    return
        
        gallery = userdata["gallery"]
        if embedding is not None:
            speaker_id, display_name, confidence = identify_speaker(
                embedding, gallery, threshold
            )
            
            # Verify speaker meets their custom threshold (if set)
            # If custom threshold is higher and not met, treat as unknown
            speaker_id = verify_person_threshold(speaker_id, confidence, threshold)
            
            # If speaker_id was cleared by custom threshold check, reset display_name
            if speaker_id is None and display_name is not None:
                print(f"  Match rejected: {display_name} did not meet custom threshold")
                display_name = None
        else:
            # Nothing to match against — the trap is the handling
            speaker_id, display_name, confidence = None, None, 0.0
        
        # Pending buffer is the ENROLLMENT bucket — full utterances only,
        # and only the trimmed (clean) artifact. Biopsies never enter.
        entry = None
        pending_wav_for_emote = None
        if is_full_audio and not too_short:
            print(f"  Adding to pending buffer: {display_name or 'user'} (available for enrollment/training)")
            entry = add_to_pending_buffer(embed_source, embedding, request_id)
            if entry:
                publish_pending_status(client)
                # Emote (full utterance, post-trim) — carried for after identity work
                pending_wav_for_emote = str(PENDING_RECORDINGS / f"{entry['id']}.wav")

        # =================================================================
        # CRITICAL FIX: Map unknowns to virtual "user" identity for blocklist check
        # =================================================================
        # For unknowns: speaker_id = None
        # Map to "user" so the blocklist check can actually block them
        effective_id = speaker_id if speaker_id else "user"
        is_blocked = is_speaker_blocked(effective_id)
        
        response = {
            "request_id": request_id,
            "speaker_id": speaker_id,
            "display_name": display_name,
            "confidence": confidence,
            "inject_enabled": inject_identity_enabled,
            "is_blocked": is_blocked,
            "timestamp": time.time(),
        }
        
        if is_blocked:
            print(
                f"  [BLOCKED] Speaker {display_name or 'user'} ({speaker_id or 'user'}) "
                f"is on blocklist - STT will silent fail"
            )
        
        response_topic = f"voicebm/stt/analyze_response/{request_id}"
        client.publish(response_topic, json.dumps(response), qos=1)
        print(f"  Published response to {response_topic}")
        
        if should_publish_active:
            # Publish Active Identity data for HA sensors (8 entities)
            decision = "accepted" if speaker_id else "unknown"
            active_identity_data = {
                "speaker_id": speaker_id,
                "display_name": display_name or "user",
                "confidence": confidence,
                "decision": decision,
                "score": confidence  # Score = confidence for active pipeline
            }
            client.publish("voicebm/active/identity", json.dumps(active_identity_data), qos=1, retain=True)
            client.publish("voicebm/active/current_event_id", request_id, qos=1, retain=True)
            
            # Publish binary sensor state for detected person
            # This creates OFF->ON transition even for consecutive utterances from same person
            if speaker_id:
                client.publish(f"{speaker_id}/voice", "ON", qos=1, retain=True)
                last_published_person = speaker_id  # Store for next clearing cycle
                print(f"  Published binary sensor: {speaker_id}/voice = ON")
            
            # Write active state to filesystem for dashboard (Flask/OpenWebUI multi-platform sync)
            write_active_state_file(speaker_id, display_name, confidence, decision)
            
            # Publish confidence + source + gallery_size as attributes for per-person binary sensor
            # IMPORTANT: Include gallery_size to keep it synced with enrollment_watcher
            if speaker_id:  # Only for identified users, not unknowns
                # Count embeddings in enrollment gallery
                from pathlib import Path
                enroll_dir = Path("/home/user/voicebm/enroll") / speaker_id / "embeddings"
                gallery_size = len(list(enroll_dir.glob('*.txt'))) if enroll_dir.exists() else 0
                
                # Merge all attributes together
                attributes = {
                    "confidence": round(confidence, 4),
                    "source": "active",
                    "gallery_size": gallery_size,
                    "last_updated": time.strftime('%Y-%m-%d %H:%M:%S')
                }
                client.publish(f"{speaker_id}/voice/attributes", json.dumps(attributes), qos=1, retain=True)
            


            print(f"  Published Active Identity: {display_name} ({decision}, {confidence:.2%})")
        
        if is_full_audio:
            # Full audio path: publish current_speaker and current_speaker_id (enrollment-grade sample)
            client.publish("voicebm/current_speaker", display_name or "user", qos=1, retain=True)
            client.publish("voicebm/current_speaker_id", speaker_id or "user", qos=1, retain=True)
            print(f"  Published Current Speaker: {display_name or 'user'} / {speaker_id or 'user'}")

        # Emote Edition — runs last, after all identity work is published.
        # Full audio only. Blocks here but identity is already done.
        # If voicebm_emote.py is not installed this is a no-op (see soft import above).
        if pending_wav_for_emote:
            run_emote(pending_wav_for_emote, client)
        
        # ── Lab waste disposal ────────────────────────────────────────────
        # The biopsy never outlives its report: measured, charted, destroyed.
        if is_biopsy:
            try:
                os.unlink(audio_path)
                print("  [BIOPSY] Sample destroyed (report filed)")
            except OSError:
                pass
        # The trimmed temp was copied into pending — the temp itself goes.
        if trimmed_tmp:
            try:
                os.unlink(trimmed_tmp)
            except OSError:
                pass
        
    except Exception as e:
        print(f"  Error processing request: {e}")
        import traceback

        traceback.print_exc()


def handle_active_threshold_set(client, userdata, msg):
    """Handle active threshold slider changes and update thresholds.json."""
    try:
        new_threshold = float(msg.payload.decode("utf-8"))
        
        # Validate range
        if not (0.01 <= new_threshold <= 1.00):
            print(f"Invalid active threshold value: {new_threshold}")
            return
        
        print(f"Active threshold changed to: {new_threshold:.2f}")
        
        # Update thresholds.json MATCH_T_ACTIVE
        try:
            if os.path.exists(THRESHOLD_FILE):
                with open(THRESHOLD_FILE, 'r') as f:
                    thresholds = json.load(f)
            else:
                thresholds = {}
            
            thresholds['MATCH_T_ACTIVE'] = new_threshold
            
            os.makedirs(os.path.dirname(THRESHOLD_FILE), exist_ok=True)
            with open(THRESHOLD_FILE, 'w') as f:
                json.dump(thresholds, f, indent=2)
            
            print(f"  Updated thresholds.json: MATCH_T_ACTIVE = {new_threshold:.2f}")
            
            # Echo back to state topic
            client.publish("voicebm/active/threshold", str(new_threshold), qos=1, retain=True)
            
            # Write settings to filesystem for dashboard
            write_settings_file()
            
        except Exception as e:
            print(f"Failed to update thresholds.json: {e}")
    
    except Exception as e:
        print(f"Error handling active threshold change: {e}")


def handle_person_threshold_set(client, userdata, msg):
    """Handle per-person threshold override changes."""
    global person_thresholds
    
    try:
        # Extract person_id from topic: {person_id}/threshold_override/set
        topic_parts = msg.topic.split('/')
        if len(topic_parts) < 3:
            print(f"Invalid threshold override topic: {msg.topic}")
            return
        
        person_id = topic_parts[0]
        new_threshold = float(msg.payload.decode("utf-8"))
        
        # Validate range
        if not (0.10 <= new_threshold <= 0.90):
            print(f"Invalid threshold value for {person_id}: {new_threshold}")
            return
        
        # Update cache
        person_thresholds[person_id] = new_threshold
        print(f"Custom threshold for {person_id}: {new_threshold:.2f}")
        
        # Echo back to state topic
        client.publish(f"{person_id}/threshold_override", str(new_threshold), qos=1, retain=True)
        
    except ValueError:
        print(f"Invalid threshold value received: {msg.payload}")
    except Exception as e:
        print(f"Error handling person threshold change: {e}")


def handle_lead_trim_set(client, userdata, msg):
    """Handle Current Lead Trim slider changes; persist to config.json."""
    try:
        new_trim = int(float(msg.payload.decode("utf-8")))
        if not (0 <= new_trim <= 2000):
            print(f"Invalid lead trim value: {new_trim}")
            return
        print(f"Active lead trim changed to: {new_trim} ms")
        if update_voicebm_config_key("current_lead_trim_ms", new_trim):
            print(f"  Updated config.json: voicebm.current_lead_trim_ms = {new_trim}")
            client.publish("voicebm/active/lead_trim", str(new_trim), qos=1, retain=True)
    except ValueError:
        print(f"Invalid lead trim value received: {msg.payload}")
    except Exception as e:
        print(f"Error handling lead trim change: {e}")


def handle_gallery_max_set(client, userdata, msg):
    """Handle Gallery Max changes and update thresholds.json GALLERY_MAX."""
    try:
        new_max = int(float(msg.payload.decode("utf-8")))

        # Validate range
        if not (0 <= new_max <= 200):
            print(f"Invalid gallery max value: {new_max}")
            return

        print(f"Gallery max changed to: {new_max}")

        # Update thresholds.json GALLERY_MAX
        try:
            if os.path.exists(THRESHOLD_FILE):
                with open(THRESHOLD_FILE, "r") as f:
                    thresholds = json.load(f)
            else:
                thresholds = {}

            thresholds["GALLERY_MAX"] = new_max

            os.makedirs(os.path.dirname(THRESHOLD_FILE), exist_ok=True)
            with open(THRESHOLD_FILE, "w") as f:
                json.dump(thresholds, f, indent=2)

            print(f"  Updated thresholds.json: GALLERY_MAX = {new_max}")

            # Echo back to state topic
            client.publish("voicebm/gallery_max", str(new_max), qos=1, retain=True)

        except Exception as e:
            print(f"Failed to update thresholds.json: {e}")

    except Exception as e:
        print(f"Error handling gallery max change: {e}")


def on_connect(client, userdata, flags, reason_code, properties):
    global inject_identity_enabled
    
    if reason_code == 0:
        print(f"Connected to MQTT broker at 127.0.0.1:1883")
        
        client.subscribe(REQUEST_TOPIC, qos=1)
        print(f"Subscribed to voicebm/stt/analyze_request")
        
        client.subscribe(INJECT_STATE_TOPIC, qos=1)
        print(f"Subscribed to voicebm/inject_identity")
        
        client.subscribe("voicebm/blocklist/+", qos=1)
        print("Subscribed to voicebm/blocklist/+ (blocklist states)")
        
        client.subscribe(PENDING_ENROLL_TOPIC, qos=1)
        client.subscribe(PENDING_REJECT_TOPIC, qos=1)
        client.subscribe(PENDING_CLEAR_TOPIC, qos=1)
        print("Subscribed to pending command topics")
        
        client.subscribe("voicebm/pending_active/person_name/set", qos=1)
        client.subscribe("voicebm/pending_active/enroll_btn", qos=1)
        client.subscribe("voicebm/pending_active/reject_btn", qos=1)
        client.subscribe("voicebm/pending_active/play_btn", qos=1)
        print("Subscribed to pending UI control topics")
        
        client.subscribe("voicebm/active/threshold/set", qos=1)
        client.subscribe("voicebm/active/lead_trim/set", qos=1)
        client.subscribe("voicebm/gallery_max/set", qos=1)
        print("Subscribed to active threshold control")
        
        # Subscribe to per-person threshold overrides
        client.subscribe("+/threshold_override/set", qos=1)
        print("Subscribed to per-person threshold overrides (+/threshold_override/set)")
        
        publish_discovery(client)
        publish_pending_status(client)
        publish_emote_discovery(client)
        
    else:
        print(f"Failed to connect, reason code: {reason_code}")


def on_message(client, userdata, msg):
    global inject_identity_enabled, pending_person_name
    
    topic = msg.topic
    
    if topic.startswith("voicebm/blocklist/") and not topic.endswith("/set"):
        handle_blocklist_state(client, userdata, msg)
    elif topic == REQUEST_TOPIC:
        handle_analysis_request(client, userdata, msg)
    elif topic == INJECT_STATE_TOPIC:
        try:
            state = msg.payload.decode("utf-8")
            new_enabled = state == "ON"
            if inject_identity_enabled != new_enabled:
                inject_identity_enabled = new_enabled
                print(f"Injection state updated: {state} (enabled={new_enabled})")
                # Write settings to filesystem for dashboard
                write_settings_file()
        except Exception as e:
            print(f"Failed to parse injection state: {e}")
    elif topic == PENDING_ENROLL_TOPIC:
        handle_pending_enroll(client, userdata, msg)
    elif topic == PENDING_REJECT_TOPIC:
        handle_pending_reject(client, userdata, msg)
    elif topic == PENDING_CLEAR_TOPIC:
        handle_pending_clear(client, userdata, msg)
    elif topic == "voicebm/pending_active/person_name/set":
        handle_person_name_set(client, userdata, msg)
    elif topic == "voicebm/pending_active/enroll_btn":
        handle_enroll_button(client, userdata, msg)
    elif topic == "voicebm/pending_active/reject_btn":
        handle_reject_button(client, userdata, msg)
    elif topic == "voicebm/pending_active/play_btn":
        handle_play_button(client, userdata, msg)
    elif topic == "voicebm/active/threshold/set":
        handle_active_threshold_set(client, userdata, msg)
    elif topic == "voicebm/active/lead_trim/set":
        handle_lead_trim_set(client, userdata, msg)
    elif topic == "voicebm/gallery_max/set":
        handle_gallery_max_set(client, userdata, msg)
    elif topic.endswith("/threshold_override/set"):
        handle_person_threshold_set(client, userdata, msg)


def main():
    global inject_identity_enabled
    
    print("=" * 60)
    print("Voice Biometrics MQTT Service (ACTIVE PIPELINE)")
    print("=" * 60)
    print(f"MQTT Broker: 127.0.0.1:1883")
    print(f"Request Topic: voicebm/stt/analyze_request")
    print(f"Response Topic: voicebm/stt/analyze_response")
    print(f"Pending Buffer Size: 5")
    print("=" * 60)
    
    setup_pending_dirs()
    
    # Write initial settings for dashboard
    print("\nInitializing dashboard state files...")
    write_settings_file()
    
    print("\nLoading enrollment gallery...")
    gallery = load_gallery()
    
    if not gallery:
        print("Warning: No enrolled speakers found!")
    
    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(USER, PASS)
    client.user_data_set({"gallery": gallery})
    client.on_connect = on_connect
    client.on_message = on_message
    
    try:
        client.connect(BROKER, PORT, 60)
    except Exception as e:
        print(f"MQTT connection failed: {e}")
        return
    
    print("\nVoice biometrics service ready")
    print("Press Ctrl+C to exit\n")
    
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print("\n\nShutting down...")
        client.disconnect()
        print("Service stopped")


if __name__ == "__main__":
    main()
```


# Passive pipeline — continuous, per node


## 3. `publish_identity_node.py` <a id="3-publish-identity-nodepy"></a>

_Voice Biometric Identity Publisher with HA MQTT Discovery (2.0, node-parameterized)_

```python
#!/usr/bin/env python3
"""Voice Biometric Identity Publisher with HA MQTT Discovery (2.0, node-parameterized)

Usage: publish_identity_node.py <node_id>

One script serves every passive node. The node_id drives all topics, paths,
unique_ids, and tracking files — byte-identical to the retired per-room
copies, so no HA entities orphan and no processed-state is lost.
Display: device name uses friendly_name from config.json -> nodes;
entity names keep the established "{Room} Speaker" style.

STARTUP BEHAVIOR:
- ALWAYS publishes discovery configs (so HA knows about entities)
- Only publishes INITIAL STATE on first-ever run
- On subsequent restarts, HA's retained state is respected
- This prevents restarts from resetting user-configured states

Tracking file: /home/user/voicebm/meta/discovery_initialized_{node}
- If file exists: skip initial state publishing
- If file missing: publish initial states, create file
"""

import os
import json
import time
import numpy as np
import paho.mqtt.client as mqtt
from pathlib import Path

# MQTT Configuration (centralized)
import sys
sys.path.insert(0, '/home/user/voicebm')
from voicebm_config import get_mqtt_config

if len(sys.argv) < 2:
    print("Usage: publish_identity_node.py <node_id>")
    sys.exit(1)

ROOM = sys.argv[1]

mqtt_config = get_mqtt_config()
BROKER = mqtt_config['broker']
PORT = mqtt_config['port']
USER = mqtt_config['user']
PASS = mqtt_config['password']

CONFIG_FILE = "/home/user/voicebm/config.json"


def _node_meta():
    """friendly_name + audio base_url from config.json (with fallbacks)."""
    friendly = ROOM.replace('_', ' ').title()
    base_url = "http://127.0.0.1:9090"
    try:
        with open(CONFIG_FILE, 'r') as f:
            cfg = json.load(f)
        node = cfg.get('nodes', {}).get(ROOM, {})
        friendly = node.get('friendly_name', friendly)
        base_url = cfg.get('audio_server', {}).get('base_url', base_url)
    except Exception:
        pass
    return friendly, base_url.rstrip('/')


FRIENDLY, AUDIO_BASE_URL = _node_meta()
NICE = ROOM.replace('_', ' ').title()   # entity display style, e.g. "Living"

LOGS_FILE = "/home/user/voicebm/meta/logs.jsonl"  # JSONL event log
EMB_DIR = f"/home/user/voicebm/embeddings/{ROOM}"
ENROLL_DIR = "/home/user/voicebm/enroll"
THR = "/home/user/voicebm/out/thresholds.json"
TOPIC = f"voicebm/{ROOM}/identity"
PERSON_ID_TOPIC = f"voicebm/{ROOM}/person_id"
CURRENT_EVENT_TOPIC = f"voicebm/{ROOM}/current_event"
PROCESSED_FILE = f"/home/user/voicebm/meta/processed_publisher_{ROOM}.txt"
META_LAB = "/home/user/voicebm/meta/labeled"

# Tracking file for first-run detection (per-room)
DISCOVERY_INITIALIZED_FILE = f"/home/user/voicebm/meta/discovery_initialized_{ROOM}"

def jload(p, d=None):
    try:
        with open(p, "r") as f:
            return json.load(f)
    except:
        return d

def get_processed_ids():
    """Get set of event IDs that have been processed (labeled or rejected)"""
    processed = set()

    # Check labeled folder
    if os.path.exists(META_LAB):
        for fname in os.listdir(META_LAB):
            if fname.endswith('.json'):
                processed.add(fname[:-5])

    # Check processed tracking file
    if os.path.exists(PROCESSED_FILE):
        with open(PROCESSED_FILE, 'r') as f:
            processed.update(line.strip() for line in f if line.strip())

    return processed

def mark_processed(eid):
    """Mark an event as processed"""
    os.makedirs(os.path.dirname(PROCESSED_FILE), exist_ok=True)
    with open(PROCESSED_FILE, 'a') as f:
        f.write(f"{eid}\n")

def get_oldest_unprocessed_event():
    """Read OLDEST unprocessed event from JSONL log for this room"""
    if not os.path.exists(LOGS_FILE):
        return None

    processed = get_processed_ids()

    with open(LOGS_FILE, 'r') as f:
        for line in f:
            if not line.strip():
                continue

            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Filter by room (node_id field in logs)
            if event.get('node_id') != ROOM:
                continue

            wav_path = event.get('wav', '')
            eid = os.path.basename(wav_path).replace('.wav', '')

            if eid in processed:
                continue

            if not os.path.exists(wav_path):
                print(f"! Skipping {eid}: WAV file missing")
                mark_processed(eid)
                continue
            emb_path = event.get('emb', '')
            if not os.path.exists(emb_path):
                print(f"! Skipping {eid}: Embedding file missing")
                mark_processed(eid)
                continue

            return event
    return None

def load_vec(ref):
    try:
        path = os.path.join(EMB_DIR, ref)
        return np.loadtxt(path)
    except:
        return None

def load_gallery():
    """Load enrolled speakers from /enroll/ directory structure."""
    people = {}
    enroll_path = Path(ENROLL_DIR)

    if not enroll_path.exists():
        print(f"Warning: Enrollment directory not found at {ENROLL_DIR}")
        return {}

    try:
        for person_dir in enroll_path.iterdir():
            if not person_dir.is_dir():
                continue

            person_id = person_dir.name
            embeddings_dir = person_dir / "embeddings"
            metadata_file = person_dir / "metadata.json"

            if metadata_file.exists():
                try:
                    with open(metadata_file, 'r') as f:
                        metadata = json.load(f)
                        display_name = metadata.get('display_name', person_id.replace('_', ' ').title())
                except:
                    display_name = person_dir.name.replace('_', ' ').title()
            else:
                display_name = person_id.replace('_', ' ').title()

            if not embeddings_dir.exists():
                continue

            vectors = []
            for emb_file in embeddings_dir.glob("*.txt"):
                try:
                    v = np.loadtxt(emb_file)
                    if v is not None and len(v) > 0:
                        vectors.append(v)
                except Exception as e:
                    print(f"  ! Failed to load {emb_file.name}: {e}")

            if vectors:
                people[(person_id, display_name)] = vectors
                print(f"  Loaded {len(vectors)} embeddings for {display_name} ({person_id})")

    except Exception as e:
        print(f"Error loading gallery: {e}")
        import traceback
        traceback.print_exc()

    cents = {}
    for (sid, name), vecs in people.items():
        cents[(sid, name)] = np.mean(vecs, axis=0)

    print(f"Loaded {len(cents)} enrolled speakers from {ENROLL_DIR}")
    return cents

def cos(a, b):
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))

def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print(f"Connected to MQTT broker at {BROKER}:{PORT}")
        client.subscribe(f"{PERSON_ID_TOPIC}/set", qos=1)
    else:
        print(f"Failed to connect, reason code: {reason_code}")

stored_person_id = ""

def on_message(client, userdata, msg):
    global stored_person_id
    if msg.topic == f"{PERSON_ID_TOPIC}/set":
        stored_person_id = msg.payload.decode("utf-8")
        client.publish(PERSON_ID_TOPIC, stored_person_id, qos=1, retain=True)
        print(f"Person ID set to: {stored_person_id}")

def on_publish(client, userdata, mid, reason_code, properties):
    pass

def is_first_run():
    """Check if this is the first time discovery has been published."""
    return not os.path.exists(DISCOVERY_INITIALIZED_FILE)

def mark_initialized():
    """Mark that discovery has been initialized."""
    os.makedirs(os.path.dirname(DISCOVERY_INITIALIZED_FILE), exist_ok=True)
    with open(DISCOVERY_INITIALIZED_FILE, 'w') as f:
        f.write(time.strftime('%Y-%m-%d %H:%M:%S'))
    print("  Marked discovery as initialized")

def publish_discovery(client):
    """Publish Home Assistant MQTT Discovery configs."""
    discovery_prefix = "homeassistant"
    first_run = is_first_run()

    if first_run:
        print("First run detected - will publish initial states")
    else:
        print("Subsequent run - respecting HA state (discovery only)")

    device = {
        "identifiers": [f"voicebm_{ROOM}"],
        "name": f"Voice Biometrics {FRIENDLY}",
        "manufacturer": "David M. Dryver Sr.",
        "model": "Home Assistant Voice Biometrics",
        "sw_version": "2.0"
    }

    configs = {
        "speaker": {
            "name": f"{NICE} Speaker",
            "unique_id": f"voicebm_{ROOM}_speaker",
            "state_topic": TOPIC,
            "value_template": "{{ value_json.display_name if value_json.display_name else 'Unknown' }}",
            "json_attributes_topic": TOPIC,
            "icon": "mdi:account-voice",
            "device": device
        },
        "confidence": {
            "name": f"{NICE} Voice Confidence",
            "unique_id": f"voicebm_{ROOM}_confidence",
            "state_topic": TOPIC,
            "value_template": "{{ (value_json.confidence * 100) | round(1) }}",
            "unit_of_measurement": "%",
            "icon": "mdi:percent",
            "device": device
        },
        "decision": {
            "name": f"{NICE} Voice Decision",
            "unique_id": f"voicebm_{ROOM}_decision",
            "state_topic": TOPIC,
            "value_template": "{{ value_json.decision }}",
            "icon": "mdi:check-decagram",
            "device": device
        },
        "speaker_id": {
            "name": f"{NICE} Speaker ID",
            "unique_id": f"voicebm_{ROOM}_speaker_id",
            "state_topic": TOPIC,
            "value_template": "{{ value_json.speaker_id if value_json.speaker_id else 'none' }}",
            "icon": "mdi:identifier",
            "device": device
        },
        "event_id": {
            "name": f"{NICE} Current Event ID",
            "unique_id": f"voicebm_{ROOM}_event_id",
            "state_topic": CURRENT_EVENT_TOPIC,
            "icon": "mdi:file-document",
            "device": device
        },
        "audio_url": {
            "name": f"{NICE} Audio URL",
            "unique_id": f"voicebm_{ROOM}_audio_url",
            "state_topic": f"voicebm/{ROOM}/audio_url",
            "icon": "mdi:volume-high",
            "device": device
        },
        "score": {
            "name": f"{NICE} Voice Score",
            "unique_id": f"voicebm_{ROOM}_score",
            "state_topic": f"voicebm/{ROOM}/score",
            "icon": "mdi:counter",
            "device": device
        }
    }

    for key, config in configs.items():
        client.publish(f"{discovery_prefix}/sensor/voicebm_{ROOM}_{key}/config", json.dumps(config), qos=1, retain=True)

    # Binary sensor for Voice Accepted
    accepted_config = {
        "name": f"{NICE} Voice Accepted",
        "unique_id": f"voicebm_{ROOM}_accepted",
        "state_topic": f"voicebm/{ROOM}/accepted",
        "payload_on": "ON",
        "payload_off": "OFF",
        "device_class": "sound",
        "icon": "mdi:check-circle",
        "device": device
    }
    client.publish(f"{discovery_prefix}/binary_sensor/voicebm_{ROOM}_accepted/config", json.dumps(accepted_config), qos=1, retain=True)

    text_config = {
        "name": f"{NICE} Person ID Input",
        "unique_id": f"voicebm_{ROOM}_person_id",
        "command_topic": f"{PERSON_ID_TOPIC}/set",
        "state_topic": PERSON_ID_TOPIC,
        "icon": "mdi:account-edit",
        "device": device
    }
    client.publish(f"{discovery_prefix}/text/voicebm_{ROOM}_person_id/config", json.dumps(text_config), qos=1, retain=True)

    buttons = {
        "play": {"name": f"{NICE} Play Audio", "icon": "mdi:play-circle", "topic": "play_audio"},
        "label": {"name": f"{NICE} Label Speaker", "icon": "mdi:check-circle", "topic": "label_trigger"},
        "reject": {"name": f"{NICE} Reject Speaker", "icon": "mdi:close-circle", "topic": "reject_trigger"}
    }

    for key, btn in buttons.items():
        btn_config = {
            "name": btn["name"],
            "unique_id": f"voicebm_{ROOM}_{key}_button",
            "command_topic": f"voicebm/{ROOM}/{btn['topic']}",
            "payload_press": "PRESS",
            "icon": btn["icon"],
            "device": device
        }
        client.publish(f"{discovery_prefix}/button/voicebm_{ROOM}_{key}/config", json.dumps(btn_config), qos=1, retain=True)

    current_speaker_config = {
        "name": f"{NICE} Current Speaker",
        "unique_id": f"voicebm_{ROOM}_current_speaker",
        "state_topic": f"voicebm/{ROOM}/current_speaker",
        "icon": "mdi:account-voice",
        "device": device
    }
    client.publish(f"{discovery_prefix}/sensor/voicebm_{ROOM}_current_speaker/config", json.dumps(current_speaker_config), qos=1, retain=True)

    if first_run:
        client.publish(f"voicebm/{ROOM}/current_speaker", "none", qos=1, retain=True)
        print("  Initial state: current_speaker = none")

    # NOTE: ID Injection is GLOBAL (voicebm/inject_identity) - not per-room
    # Global publisher handles this switch

    threshold_config = {
        "name": f"{NICE} Match Threshold",
        "unique_id": f"voicebm_{ROOM}_threshold",
        "command_topic": f"voicebm/{ROOM}/threshold/set",
        "state_topic": f"voicebm/{ROOM}/threshold",
        "min": 0.01,
        "max": 1.00,
        "step": 0.01,
        "mode": "slider",
        "icon": "mdi:tune",
        "device": device
    }
    client.publish(f"{discovery_prefix}/number/voicebm_{ROOM}_threshold/config", json.dumps(threshold_config), qos=1, retain=True)

    if first_run:
        try:
            with open(THR, 'r') as f:
                thr = json.load(f)
                threshold_value = float(thr.get("MATCH_T", 0.22))
        except:
            threshold_value = 0.22

        client.publish(f"voicebm/{ROOM}/threshold", str(threshold_value), qos=1, retain=True)
        print(f"  Initial state: threshold = {threshold_value}")

        mark_initialized()

    print("Published Home Assistant MQTT Discovery configs")

current_event_id = None
advance_to_next = False

def main():
    global current_event_id, stored_person_id, advance_to_next

    c = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    c.username_pw_set(USER, PASS)
    c.on_connect = on_connect
    c.on_publish = on_publish
    c.on_message = on_message

    try:
        c.connect(BROKER, PORT, 60)
    except Exception as e:
        print(f"Connection failed: {e}")
        return

    c.loop_start()
    publish_discovery(c)

    c.subscribe(f"voicebm/{ROOM}/label_trigger", qos=1)
    c.subscribe(f"voicebm/{ROOM}/reject_trigger", qos=1)

    def handle_buttons(client, userdata, msg):
        global current_event_id, stored_person_id, advance_to_next
        if msg.topic.endswith("/label_trigger") and current_event_id and stored_person_id:
            label_cmd = {"id": current_event_id, "person_id": stored_person_id}
            c.publish(f"voicebm/{ROOM}/label", json.dumps(label_cmd), qos=1)
            print(f"+ ENROLL: {current_event_id} -> {stored_person_id}")
            mark_processed(current_event_id)
            advance_to_next = True
        elif msg.topic.endswith("/reject_trigger") and current_event_id:
            reject_cmd = {"id": current_event_id}
            c.publish(f"voicebm/{ROOM}/reject", json.dumps(reject_cmd), qos=1)
            print(f"x REJECT: {current_event_id}")
            mark_processed(current_event_id)
            advance_to_next = True
        else:
            print(f"! Button pressed but conditions not met: event={current_event_id}, person={stored_person_id}")

    c.message_callback_add(f"voicebm/{ROOM}/label_trigger", handle_buttons)
    c.message_callback_add(f"voicebm/{ROOM}/reject_trigger", handle_buttons)

    # NOTE: ID Injection is GLOBAL - passive nodes don't control it
    c.subscribe(f"voicebm/{ROOM}/threshold/set", qos=1)

    def handle_threshold_update(client, userdata, msg):
        try:
            new_threshold = float(msg.payload.decode('utf-8'))
            print(f"Threshold update: {new_threshold:.2f}")

            thr_path = "/home/user/voicebm/out/thresholds.json"

            try:
                with open(thr_path, 'r') as f:
                    thresholds = json.load(f)
            except:
                thresholds = {}

            thresholds['MATCH_T'] = new_threshold
            thresholds['last_updated'] = time.strftime('%Y-%m-%d %H:%M:%S')

            with open(thr_path, 'w') as f:
                json.dump(thresholds, f, indent=2)

            client.publish(f"voicebm/{ROOM}/threshold", str(new_threshold), qos=1, retain=True)

            print(f"  Match threshold updated: {new_threshold:.2f}")

        except Exception as e:
            print(f"  Error handling threshold update: {e}")

    c.message_callback_add(f"voicebm/{ROOM}/threshold/set", handle_threshold_update)

    print(f"[{ROOM}] Monitoring {LOGS_FILE} for oldest unprocessed voice events...")

    while True:
        try:
            if advance_to_next or current_event_id is None:
                event = get_oldest_unprocessed_event()
                advance_to_next = False

                if not event:
                    if current_event_id is not None:
                        print("No more unprocessed files")
                        current_event_id = None
                    time.sleep(2)
                    continue

                wav_path = event.get("wav", "")
                emb_path = event.get("emb", "")
                event_ts = event.get("ts_iso")

                wav = os.path.basename(wav_path) if wav_path else ""
                emb = os.path.basename(emb_path) if emb_path else ""

                new_event_id = wav.replace(".wav", "") if wav else None

                if new_event_id and new_event_id != current_event_id:
                    current_event_id = new_event_id
                    c.publish(CURRENT_EVENT_TOPIC, current_event_id, qos=1, retain=True)
                    audio_url = f"{AUDIO_BASE_URL}/{ROOM}/{wav}"
                    c.publish(f"voicebm/{ROOM}/audio_url", audio_url, qos=1, retain=True)

                    thr = jload(THR, {"MATCH_T": 0.22})
                    MATCH_T = float(thr.get("MATCH_T", 0.22))

                    v = load_vec(emb) if emb else None

                    sid = None
                    name = None
                    conf = 0.0
                    decision = "unknown"

                    cents = load_gallery()
                    if v is not None and cents:
                        best_sid = None
                        best_name = None
                        best_sim = -1.0
                        for (psid, pname), cent in cents.items():
                            sim = cos(v, cent)
                            if sim > best_sim:
                                best_sim = sim
                                best_sid = psid
                                best_name = pname

                        conf = best_sim
                        if best_sim >= MATCH_T:
                            sid = best_sid
                            name = best_name
                            decision = "accepted"

                    stored_person_id = sid

                    payload = {
                        "room": ROOM,
                        "speaker_id": sid,
                        "display_name": name,
                        "confidence": round(conf, 4),
                        "decision": decision,
                        "wav": wav,
                        "ts": event_ts
                    }

                    result = c.publish(TOPIC, json.dumps(payload), qos=1, retain=True)
                    if result.rc == mqtt.MQTT_ERR_SUCCESS:
                        print(f"Published: {current_event_id} - {name or 'Unknown'} ({sid or 'none'}), confidence={conf:.4f}")
                    else:
                        print(f"Publish failed with code: {result.rc}")

            time.sleep(1)

        except KeyboardInterrupt:
            print("\nShutting down...")
            break
        except Exception as e:
            print(f"Error in main loop: {e}")
            time.sleep(1)

    c.loop_stop()
    c.disconnect()

if __name__ == "__main__":
    main()
```


## 4. `vad_filter.py` <a id="4-vad-filterpy"></a>

_VAD Filter Service - Removes silence/noise files before embedding (2.0)_

```python
#!/usr/bin/env python3
"""VAD Filter Service - Removes silence/noise files before embedding (2.0)

- Watches ALL node directories under recordings/
- Processes any .wav without corresponding .txt in embeddings/
- One global service handles all passive nodes

2.0: VAD thresholds live in config.json -> vad and are tunable live via
HA number entities (global Voice Biometrics device). Changes persist back
to config.json. MQTT is a soft dependency — if the broker is unreachable,
filtering continues with config values.

config.json -> vad:
  speech_threshold    (default 0.6)  - VAD confidence, higher = stricter
  min_speech_ratio    (default 0.50) - fraction of file that must be speech
  min_speech_duration (default 0.8)  - seconds of speech required
"""

import os
import sys
import time
import json
import wave
import torch
import logging
import threading
from pathlib import Path

sys.path.insert(0, '/home/user/voicebm')
from voicebm_config import get_mqtt_config

# Configuration
RECORDINGS_BASE = Path("/home/user/voicebm/recordings")
EMBEDDINGS_BASE = Path("/home/user/voicebm/embeddings")
LOG_FILE = Path("/home/user/voicebm/meta/vad_filter.log")
STATS_FILE = Path("/home/user/voicebm/meta/vad_stats.json")
CONFIG_FILE = "/home/user/voicebm/config.json"

# VAD threshold defaults (overridden by config.json -> vad)
DEFAULTS = {
    "speech_threshold":    0.6,
    "min_speech_ratio":    0.50,
    "min_speech_duration": 0.8,
}

# Safety settings
MIN_FILE_AGE_SECONDS = 10    # Don't process files younger than this (ffmpeg still writing)
MIN_FILE_SIZE_BYTES = 1000   # Skip files smaller than this (corrupt/incomplete)

DISCOVERY_PREFIX = "homeassistant"

# Live thresholds — read from config at start, updated via MQTT
_thr_lock = threading.Lock()
THR = dict(DEFAULTS)

# Slider ranges per key: (min, max, step)
RANGES = {
    "speech_threshold":    (0.10, 0.95, 0.05),
    "min_speech_ratio":    (0.05, 0.95, 0.05),
    "min_speech_duration": (0.10, 3.00, 0.10),
}

# Setup logging
os.makedirs(LOG_FILE.parent, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)


def load_thresholds():
    """Read vad section from config.json into THR (with defaults)."""
    try:
        with open(CONFIG_FILE, 'r') as f:
            cfg = json.load(f)
        vad = cfg.get('vad', {})
    except Exception as e:
        logging.warning(f"Could not read config.json vad section: {e} — using defaults")
        vad = {}
    with _thr_lock:
        for k, d in DEFAULTS.items():
            THR[k] = float(vad.get(k, d))


def persist_threshold(key, value):
    """Write one vad threshold back to config.json."""
    try:
        with open(CONFIG_FILE, 'r') as f:
            cfg = json.load(f)
        cfg.setdefault('vad', {})[key] = value
        with open(CONFIG_FILE, 'w') as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        logging.error(f"config write failed for vad.{key}: {e}")


# ── MQTT (soft dependency — controls only) ──────────────────────────────────
def start_mqtt():
    """Connect, publish discovery + current state, subscribe to set topics.
    Returns the client, or None if MQTT is unavailable."""
    try:
        import paho.mqtt.client as mqtt

        mc = get_mqtt_config()

        def on_connect(client, userdata, flags, reason_code, properties):
            if reason_code != 0:
                logging.warning(f"VAD MQTT connect failed: {reason_code}")
                return
            logging.info("VAD MQTT connected")

            device = {
                "identifiers": ["voicebm"],
                "name": "Voice Biometrics",
                "manufacturer": "David M. Dryver Sr.",
                "model": "Home Assistant Voice Biometrics",
                "sw_version": "2.0",
            }
            nice = {
                "speech_threshold":    "VAD Speech Threshold",
                "min_speech_ratio":    "VAD Min Speech Ratio",
                "min_speech_duration": "VAD Min Speech Duration",
            }
            for key, (lo, hi, step) in RANGES.items():
                config = {
                    "name": nice[key],
                    "unique_id": f"voicebm_vad_{key}",
                    "command_topic": f"voicebm/vad/{key}/set",
                    "state_topic": f"voicebm/vad/{key}",
                    "min": lo, "max": hi, "step": step,
                    "mode": "slider",
                    "icon": "mdi:tune-variant",
                    "device": device,
                }
                client.publish(f"{DISCOVERY_PREFIX}/number/voicebm_vad_{key}/config",
                               json.dumps(config), qos=1, retain=True)
                # config.json is the source of truth for these — publish current
                with _thr_lock:
                    client.publish(f"voicebm/vad/{key}", str(THR[key]), qos=1, retain=True)
                client.subscribe(f"voicebm/vad/{key}/set", qos=1)

        def on_message(client, userdata, msg):
            for key in RANGES:
                if msg.topic == f"voicebm/vad/{key}/set":
                    try:
                        value = float(msg.payload.decode('utf-8'))
                    except ValueError:
                        logging.warning(f"vad.{key}: non-numeric payload ignored")
                        return
                    lo, hi, _ = RANGES[key]
                    value = max(lo, min(hi, value))
                    with _thr_lock:
                        THR[key] = value
                    persist_threshold(key, value)
                    client.publish(f"voicebm/vad/{key}", str(value), qos=1, retain=True)
                    logging.info(f"vad.{key} -> {value}")
                    return

        client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        client.username_pw_set(mc['user'], mc['password'])
        client.on_connect = on_connect
        client.on_message = on_message
        client.connect(mc['broker'], mc['port'], 60)
        client.loop_start()
        return client

    except Exception as e:
        logging.warning(f"VAD MQTT unavailable ({e}) — running with config values only")
        return None


# Load Silero VAD model
logging.info("Loading Silero VAD model...")
model = None
get_speech_timestamps = None
read_audio = None

try:
    model, utils = torch.hub.load(
        repo_or_dir='snakers4/silero-vad',
        model='silero_vad',
        force_reload=False,
        onnx=True
    )
    (get_speech_timestamps, _, read_audio, _, _) = utils
    logging.info("Silero VAD model loaded successfully")
except Exception as e:
    logging.error(f"Failed to load Silero VAD: {e}")
    sys.exit(1)


def get_file_age_seconds(wav_path):
    """Get age of file in seconds"""
    try:
        mtime = wav_path.stat().st_mtime
        return time.time() - mtime
    except:
        return 0


def is_valid_wav(wav_path):
    """
    Check if WAV file can be opened and has valid audio data.
    Returns: (valid: bool, duration: float, error_msg: str or None)
    """
    try:
        with wave.open(str(wav_path), 'rb') as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            channels = wf.getnchannels()

            if rate <= 0 or frames <= 0 or channels <= 0:
                return False, 0.0, "invalid WAV header"

            duration = frames / float(rate)

            if duration < 0.1:  # Less than 100ms is useless
                return False, duration, "too short"

            return True, duration, None
    except wave.Error as e:
        return False, 0.0, f"WAV error: {e}"
    except Exception as e:
        return False, 0.0, f"read error: {e}"


def has_sufficient_speech(wav_path):
    """
    Check if audio file contains sufficient speech.
    Returns: (keep_file: bool, speech_duration: float, total_duration: float)
    """
    try:
        with _thr_lock:
            speech_threshold    = THR["speech_threshold"]
            min_speech_ratio    = THR["min_speech_ratio"]
            min_speech_duration = THR["min_speech_duration"]

        # Read audio (Silero expects 16kHz)
        wav = read_audio(str(wav_path), sampling_rate=16000)
        total_duration = len(wav) / 16000.0

        # Get speech timestamps
        speech_timestamps = get_speech_timestamps(
            wav,
            model,
            threshold=speech_threshold,
            sampling_rate=16000,
            return_seconds=True
        )

        if not speech_timestamps:
            return False, 0.0, total_duration

        # Calculate total speech duration
        speech_duration = sum(
            segment['end'] - segment['start']
            for segment in speech_timestamps
        )

        # Apply thresholds
        speech_ratio = speech_duration / total_duration if total_duration > 0 else 0

        keep = (speech_duration >= min_speech_duration and
                speech_ratio >= min_speech_ratio)

        return keep, speech_duration, total_duration

    except Exception as e:
        # VAD failed to process - file is likely corrupt
        # Return False to DELETE it, not keep it
        logging.warning(f"VAD processing failed on {wav_path.name}: {e} - marking for deletion")
        return False, 0.0, 0.0


def get_all_rooms():
    """Get list of all node directories under recordings/"""
    if not RECORDINGS_BASE.exists():
        return []

    rooms = []
    for item in RECORDINGS_BASE.iterdir():
        if item.is_dir():
            rooms.append(item.name)

    return sorted(rooms)


def process_room_recordings(room):
    """Process all unprocessed recordings for a specific node"""
    rec_dir = RECORDINGS_BASE / room
    emb_dir = EMBEDDINGS_BASE / room

    if not rec_dir.exists():
        return {"kept": 0, "deleted": 0, "errors": 0, "skipped": 0}

    # Ensure embeddings directory exists
    emb_dir.mkdir(parents=True, exist_ok=True)

    stats = {"kept": 0, "deleted": 0, "errors": 0, "skipped": 0}

    # Get all WAV files without TXT companions
    for wav_file in sorted(rec_dir.glob("*.wav")):
        basename = wav_file.stem
        txt_file = emb_dir / f"{basename}.txt"

        # Skip if already embedded
        if txt_file.exists():
            continue

        # Skip files that are too young (still being written by ffmpeg)
        file_age = get_file_age_seconds(wav_file)
        if file_age < MIN_FILE_AGE_SECONDS:
            stats["skipped"] += 1
            continue

        # Check file size
        try:
            file_size = wav_file.stat().st_size
        except:
            file_size = 0

        # Delete files that are too small (corrupt/incomplete)
        if file_size < MIN_FILE_SIZE_BYTES:
            try:
                wav_file.unlink()
                logging.info(f"DELETE [{room}] {wav_file.name} [corrupt: {file_size} bytes]")
                stats["deleted"] += 1
            except Exception as e:
                logging.error(f"Failed to delete corrupt {wav_file.name}: {e}")
                stats["errors"] += 1
            continue

        # Validate WAV file structure before VAD
        valid, duration, error_msg = is_valid_wav(wav_file)
        if not valid:
            try:
                wav_file.unlink()
                logging.info(f"DELETE [{room}] {wav_file.name} [invalid: {error_msg}]")
                stats["deleted"] += 1
            except Exception as e:
                logging.error(f"Failed to delete invalid {wav_file.name}: {e}")
                stats["errors"] += 1
            continue

        # Run VAD check
        keep, speech_dur, total_dur = has_sufficient_speech(wav_file)
        speech_pct = (speech_dur / total_dur * 100) if total_dur > 0 else 0

        if keep:
            logging.info(
                f"KEEP   [{room}] {wav_file.name} "
                f"[speech: {speech_dur:.2f}s / {total_dur:.1f}s = {speech_pct:.0f}%]"
            )
            stats["kept"] += 1
        else:
            try:
                wav_file.unlink()
                if total_dur > 0:
                    logging.info(
                        f"DELETE [{room}] {wav_file.name} "
                        f"[speech: {speech_dur:.2f}s / {total_dur:.1f}s = {speech_pct:.0f}%]"
                    )
                else:
                    logging.info(f"DELETE [{room}] {wav_file.name} [unreadable/corrupt]")
                stats["deleted"] += 1
            except Exception as e:
                logging.error(f"Failed to delete {wav_file.name}: {e}")
                stats["errors"] += 1

    return stats


def save_stats(all_stats):
    """Save cumulative statistics"""
    try:
        if STATS_FILE.exists():
            with open(STATS_FILE, 'r') as f:
                cumulative = json.load(f)
        else:
            cumulative = {"kept": 0, "deleted": 0, "errors": 0, "skipped": 0, "started": None}

        if cumulative["started"] is None:
            cumulative["started"] = time.strftime('%Y-%m-%d %H:%M:%S')

        cumulative["kept"] += all_stats["kept"]
        cumulative["deleted"] += all_stats["deleted"]
        cumulative["errors"] += all_stats["errors"]
        cumulative["skipped"] = cumulative.get("skipped", 0) + all_stats.get("skipped", 0)
        cumulative["last_run"] = time.strftime('%Y-%m-%d %H:%M:%S')

        with open(STATS_FILE, 'w') as f:
            json.dump(cumulative, f, indent=2)
    except Exception as e:
        logging.error(f"Failed to save stats: {e}")


def main():
    """Main loop - watches ALL nodes"""
    load_thresholds()
    mqtt_client = start_mqtt()

    logging.info("=" * 60)
    logging.info("VAD Filter Service Started (MULTI-NODE, 2.0)")
    logging.info(f"Monitoring: {RECORDINGS_BASE}")
    with _thr_lock:
        logging.info(f"VAD Thresholds: min_speech={THR['min_speech_duration']}s, "
                     f"threshold={THR['speech_threshold']}, "
                     f"min_ratio={THR['min_speech_ratio']}")
    logging.info(f"Safety: min_age={MIN_FILE_AGE_SECONDS}s, min_size={MIN_FILE_SIZE_BYTES} bytes")
    logging.info(f"HA controls: {'active' if mqtt_client else 'unavailable'}")
    logging.info("=" * 60)

    cycle = 0

    while True:
        try:
            cycle += 1

            # Get all nodes
            rooms = get_all_rooms()

            if not rooms:
                logging.info("No node directories found, waiting...")
                time.sleep(5)
                continue

            # Process each node
            all_stats = {"kept": 0, "deleted": 0, "errors": 0, "skipped": 0}

            for room in rooms:
                room_stats = process_room_recordings(room)

                # Aggregate stats
                for key in all_stats:
                    all_stats[key] += room_stats[key]

            if all_stats["kept"] > 0 or all_stats["deleted"] > 0:
                logging.info(
                    f"Cycle {cycle}: kept={all_stats['kept']}, "
                    f"deleted={all_stats['deleted']}, skipped={all_stats['skipped']}, "
                    f"errors={all_stats['errors']} (across {len(rooms)} nodes)"
                )
                save_stats(all_stats)

            time.sleep(2)  # Poll every 2 seconds

        except KeyboardInterrupt:
            logging.info("VAD Filter Service stopped by user")
            break
        except Exception as e:
            logging.error(f"Main loop error: {e}", exc_info=True)
            time.sleep(5)


if __name__ == "__main__":
    main()
```


## 5. `voice_clustering.py` <a id="5-voice-clusteringpy"></a>

_Voice Clustering - Groups similar unprocessed voice embeddings for batch enrollment_

```python
#!/usr/bin/env python3
"""Voice Clustering - Groups similar unprocessed voice embeddings for batch enrollment"""

import os
import json
import numpy as np
from pathlib import Path
from collections import defaultdict
from typing import List, Dict, Tuple

# Configuration
LOGS_FILE = Path("/home/user/voicebm/meta/logs.jsonl")
EMB_DIR = Path("/home/user/voicebm/embeddings/living")
META_LAB = Path("/home/user/voicebm/meta/labeled")
PROCESSED_FILE = Path("/home/user/voicebm/meta/processed.txt")
CLUSTER_CACHE = Path("/home/user/voicebm/meta/clusters.json")

# Clustering parameters
SIMILARITY_THRESHOLD = 0.70  # Voices above this similarity are clustered together
MIN_CLUSTER_SIZE = 3         # Minimum samples to form a cluster
MAX_CLUSTER_SIZE = 50        # Maximum samples in one cluster (prevents overwhelming UI)


def get_processed_ids():
    """Get set of already processed event IDs"""
    processed = set()
    
    # Check labeled folder
    if META_LAB.exists():
        for f in META_LAB.glob("*.json"):
            processed.add(f.stem)
    
    # Check processed tracking file
    if PROCESSED_FILE.exists():
        with open(PROCESSED_FILE, 'r') as f:
            processed.update(line.strip() for line in f if line.strip())
    
    return processed


def load_embedding(emb_path: Path) -> np.ndarray:
    """Load embedding vector from file"""
    try:
        return np.loadtxt(emb_path)
    except Exception as e:
        print(f"Error loading {emb_path}: {e}")
        return None


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors"""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def get_enrolled_persons() -> Dict[str, Dict]:
    """
    Load enrolled persons and their embeddings.
    Returns dict of person_id -> {display_name, embeddings}
    """
    enroll_dir = Path("/home/user/voicebm/enroll")
    persons = {}
    
    if not enroll_dir.exists():
        return persons
    
    for person_dir in enroll_dir.iterdir():
        if not person_dir.is_dir():
            continue
        
        person_id = person_dir.name
        
        # Load metadata for display name
        metadata_file = person_dir / 'metadata.json'
        display_name = person_id
        if metadata_file.exists():
            try:
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
                    display_name = metadata.get('display_name', person_id)
            except:
                pass
        
        # Load embeddings (Sherpa format: .txt files in embeddings/ subdirectory)
        embeddings_dir = person_dir / 'embeddings'
        if not embeddings_dir.exists():
            continue
        
        embeddings = []
        for emb_file in embeddings_dir.glob('*.txt'):
            emb = load_embedding(emb_file)
            if emb is not None:
                embeddings.append(emb)
        
        if embeddings:
            persons[person_id] = {
                'display_name': display_name,
                'embeddings': embeddings
            }
    
    return persons


def find_likely_person_match(cluster_centroid: np.ndarray, enrolled_persons: Dict) -> Tuple[str, str, float]:
    """
    Compare cluster centroid against enrolled persons.
    
    Returns:
        (person_id, display_name, confidence) or (None, None, 0.0) if no good match
    """
    if not enrolled_persons:
        return None, None, 0.0
    
    best_match = None
    best_confidence = 0.0
    best_name = None
    
    for person_id, person_data in enrolled_persons.items():
        # Compute centroid of person's embeddings
        person_centroid = np.mean(person_data['embeddings'], axis=0)
        
        # Compare with cluster centroid
        similarity = cosine_similarity(cluster_centroid, person_centroid)
        
        if similarity > best_confidence:
            best_confidence = similarity
            best_match = person_id
            best_name = person_data['display_name']
    
    # Only return match if confidence is reasonable (>0.50)
    if best_confidence > 0.50:
        return best_match, best_name, best_confidence
    
    return None, None, 0.0


def get_unprocessed_samples() -> List[Dict]:
    """Get all unprocessed audio samples with their embeddings"""
    if not LOGS_FILE.exists():
        return []
    
    processed = get_processed_ids()
    samples = []
    
    with open(LOGS_FILE, 'r') as f:
        for line in f:
            if not line.strip():
                continue
            
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            
            wav_path = event.get('wav', '')
            emb_path = event.get('emb', '')
            
            if not wav_path or not emb_path:
                continue
            
            eid = Path(wav_path).stem
            
            # Skip if already processed
            if eid in processed:
                continue
            
            # Skip if files don't exist
            if not Path(wav_path).exists() or not Path(emb_path).exists():
                continue
            
            # Load embedding
            emb = load_embedding(Path(emb_path))
            if emb is None:
                continue
            
            samples.append({
                'id': eid,
                'wav': wav_path,
                'emb_path': emb_path,
                'embedding': emb,
                'timestamp': event.get('ts_iso', '')
            })
    
    return samples


def cluster_voices(samples: List[Dict]) -> List[List[Dict]]:
    """
    Cluster voice samples by similarity using simple threshold-based clustering.
    Similar to how Frigate groups similar faces.
    """
    if not samples:
        return []
    
    clusters = []
    remaining = samples.copy()
    
    while remaining:
        # Start new cluster with first remaining sample
        seed = remaining.pop(0)
        cluster = [seed]
        
        # Find all samples similar to this cluster
        to_remove = []
        for i, sample in enumerate(remaining):
            # Compare against cluster centroid
            cluster_embeddings = [s['embedding'] for s in cluster]
            centroid = np.mean(cluster_embeddings, axis=0)
            
            similarity = cosine_similarity(sample['embedding'], centroid)
            
            if similarity >= SIMILARITY_THRESHOLD:
                cluster.append(sample)
                to_remove.append(i)
                
                # Stop if cluster is getting too large
                if len(cluster) >= MAX_CLUSTER_SIZE:
                    break
        
        # Remove clustered samples from remaining
        for i in reversed(to_remove):
            remaining.pop(i)
        
        # Only keep clusters that meet minimum size
        if len(cluster) >= MIN_CLUSTER_SIZE:
            clusters.append(cluster)
    
    return clusters


def compute_cluster_stats(cluster: List[Dict]) -> Dict:
    """Compute statistics for a cluster"""
    embeddings = [s['embedding'] for s in cluster]
    centroid = np.mean(embeddings, axis=0)
    
    # Compute average similarity within cluster
    similarities = []
    for i, emb1 in enumerate(embeddings):
        for emb2 in embeddings[i+1:]:
            similarities.append(cosine_similarity(emb1, emb2))
    
    avg_similarity = np.mean(similarities) if similarities else 0.0
    
    # Get time range
    timestamps = [s['timestamp'] for s in cluster if s['timestamp']]
    time_range = {
        'start': min(timestamps) if timestamps else None,
        'end': max(timestamps) if timestamps else None
    }
    
    return {
        'count': len(cluster),
        'avg_similarity': float(avg_similarity),
        'time_range': time_range
    }


def generate_clusters(force_refresh: bool = False) -> List[Dict]:
    """
    Generate voice clusters for batch enrollment.
    Returns list of clusters with metadata.
    """
    # Check cache if not forcing refresh
    if not force_refresh and CLUSTER_CACHE.exists():
        try:
            cache_age = (Path.cwd().stat().st_mtime - CLUSTER_CACHE.stat().st_mtime)
            if cache_age < 300:  # Cache valid for 5 minutes
                with open(CLUSTER_CACHE, 'r') as f:
                    return json.load(f)
        except:
            pass
    
    print("Loading unprocessed samples...")
    samples = get_unprocessed_samples()
    print(f"Found {len(samples)} unprocessed samples")
    
    if not samples:
        return []
    
    print("Clustering voices by similarity...")
    clusters = cluster_voices(samples)
    print(f"Generated {len(clusters)} clusters")
    
    # Load enrolled persons for matching
    print("Loading enrolled persons for matching...")
    enrolled_persons = get_enrolled_persons()
    print(f"Found {len(enrolled_persons)} enrolled persons")
    
    # Convert clusters to serializable format
    cluster_data = []
    for i, cluster in enumerate(clusters):
        # Compute cluster centroid for person matching
        cluster_embeddings = [s['embedding'] for s in cluster]
        centroid = np.mean(cluster_embeddings, axis=0)
        
        # Find likely person match
        person_id, display_name, confidence = find_likely_person_match(centroid, enrolled_persons)
        
        # Remove embeddings from sample data (too large for JSON)
        # BUT keep emb_path for enrollment
        samples_data = [
            {
                'id': s['id'],
                'wav': s['wav'],
                'emb_path': s['emb_path'],  # CRITICAL: Needed for enrollment
                'timestamp': s['timestamp']
            }
            for s in cluster
        ]
        
        stats = compute_cluster_stats(cluster)
        
        cluster_data.append({
            'cluster_id': i,
            'samples': samples_data,
            'stats': stats,
            'likely_match': {
                'person_id': person_id,
                'display_name': display_name,
                'confidence': float(confidence) if confidence else 0.0
            } if person_id else None
        })
    
    # Cache results
    CLUSTER_CACHE.parent.mkdir(exist_ok=True)
    with open(CLUSTER_CACHE, 'w') as f:
        json.dump(cluster_data, f, indent=2)
    
    return cluster_data


def get_cluster_by_id(cluster_id: int) -> Dict:
    """Get specific cluster by ID"""
    clusters = generate_clusters()
    for cluster in clusters:
        if cluster['cluster_id'] == cluster_id:
            return cluster
    return None


if __name__ == "__main__":
    # Test clustering
    print("Generating voice clusters...")
    clusters = generate_clusters(force_refresh=True)
    
    print(f"\nFound {len(clusters)} clusters:")
    for c in clusters:
        print(f"  Cluster {c['cluster_id']}: "
              f"{c['stats']['count']} samples, "
              f"avg similarity: {c['stats']['avg_similarity']:.3f}")
```


## 6. `cluster_publisher.py` <a id="6-cluster-publisherpy"></a>

_Cluster Publisher - Publishes voice cluster data to MQTT for Home Assistant automations._

```python
#!/usr/bin/env python3
"""
Cluster Publisher - Publishes voice cluster data to MQTT for Home Assistant automations.

MQTT DISCOVERY PATTERN:
Follows the EXACT same pattern as enrollment_watcher.py person device creation.
- Publishes discovery configs with retain=True
- HA auto-creates sensors
- State updates published to state topics

Workflow:
1. Clustering service groups similar unprocessed voices
2. This publisher sends cluster metadata to HA via MQTT
3. HA automations make enrollment decisions
4. When enrollment happens, enrollment_watcher.py handles device creation
"""

import os
import sys
import json
import time
import datetime
import paho.mqtt.client as mqtt
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import clustering logic
try:
    import voice_clustering
except ImportError:
    print("Error: voice_clustering.py not found in same directory")
    sys.exit(1)

# MQTT Configuration
# MQTT Configuration (centralized)
import sys
sys.path.insert(0, '/home/user/voicebm')
from voicebm_config import get_mqtt_config

mqtt_config = get_mqtt_config()
BROKER = mqtt_config['broker']
PORT = mqtt_config['port']
USER = mqtt_config['user']
PASS = mqtt_config['password']

# Topics
ROOM = "living"
CLUSTERS_TOPIC = f"voicebm/{ROOM}/clusters"
CLUSTER_DETAIL_TOPIC = f"voicebm/{ROOM}/cluster"
ENROLL_COMMAND_TOPIC = f"voicebm/{ROOM}/enroll_cluster"
REJECT_COMMAND_TOPIC = f"voicebm/{ROOM}/reject_cluster"

# State
last_cluster_count = 0
mqtt_client = None


def publish_discovery(client):
    """
    Publish Home Assistant MQTT Discovery configs for clustering sensors.
    
    PATTERN: Matches enrollment_watcher.py person device creation EXACTLY.
    - Discovery configs published with retain=True
    - State updates published separately to state topics
    """
    discovery_prefix = "homeassistant"
    
    # Device info (matches Voice Biometrics Living Room device)
    device = {
        "identifiers": ["voicebm_living"],
        "name": "Voice Biometrics Living Room",
        "manufacturer": "David M. Dryver Sr.",
        "model": "Home Assistant Voice Biometrics"
    }
    
    # Sensor: Pending cluster count
    cluster_count_config = {
        "name": "Living Room Pending Clusters",
        "unique_id": "voicebm_living_pending_clusters",
        "state_topic": CLUSTERS_TOPIC,
        "value_template": "{{ value_json.count }}",
        "json_attributes_topic": CLUSTERS_TOPIC,
        "icon": "mdi:account-multiple",
        "device": device
    }
    
    client.publish(
        f"{discovery_prefix}/sensor/voicebm_living_pending_clusters/config",
        json.dumps(cluster_count_config),
        qos=1,
        retain=True
    )
    
    # Sensor: Total unprocessed samples
    samples_config = {
        "name": "Living Room Unprocessed Samples",
        "unique_id": "voicebm_living_unprocessed_samples",
        "state_topic": CLUSTERS_TOPIC,
        "value_template": "{{ value_json.total_samples }}",
        "icon": "mdi:voice",
        "device": device
    }
    
    client.publish(
        f"{discovery_prefix}/sensor/voicebm_living_unprocessed_samples/config",
        json.dumps(samples_config),
        qos=1,
        retain=True
    )
    
    print("âœ“ Published MQTT Discovery configs for cluster sensors")


def publish_cluster_summary(client, clusters):
    """
    Publish summary of all pending clusters to state topic.
    
    This updates the STATE for sensors created by publish_discovery().
    """
    if not clusters:
        summary = {
            "count": 0,
            "total_samples": 0,
            "clusters": []
        }
    else:
        summary = {
            "count": len(clusters),
            "total_samples": sum(c['stats']['count'] for c in clusters),
            "clusters": [
                {
                    "cluster_id": c['cluster_id'],
                    "sample_count": c['stats']['count'],
                    "avg_similarity": round(c['stats']['avg_similarity'], 3),
                    "time_range": c['stats']['time_range']
                }
                for c in clusters
            ]
        }
    
    result = client.publish(
        CLUSTERS_TOPIC,
        json.dumps(summary),
        qos=1,
        retain=True
    )
    
    return result.rc == mqtt.MQTT_ERR_SUCCESS


def publish_cluster_details(client, cluster):
    """
    Publish detailed info for a specific cluster WITH AUDIO URLS.
    
    ENHANCEMENT: Removes 10-sample limit, adds audio URLs for Frigate-style review.
    """
    detail = {
        "cluster_id": cluster['cluster_id'],
        "sample_count": cluster['stats']['count'],
        "avg_similarity": round(cluster['stats']['avg_similarity'], 3),
        "time_range": cluster['stats']['time_range'],
        "samples": [
            {
                "id": s['id'],
                "timestamp": s['timestamp'],
                "wav_url": f"http://127.0.0.1:9090/living/{s['id']}.wav",
                "wav_filename": f"{s['id']}.wav"
            }
            for s in cluster['samples']  # ALL samples, no 10-sample limit
        ],
        # Playlist array for "play all" workflows
        "audio_urls": [
            f"http://127.0.0.1:9090/living/{s['id']}.wav"
            for s in cluster['samples']
        ]
    }
    
    topic = f"{CLUSTER_DETAIL_TOPIC}/{cluster['cluster_id']}"
    result = client.publish(
        topic,
        json.dumps(detail),
        qos=1,
        retain=True
    )
    
    return result.rc == mqtt.MQTT_ERR_SUCCESS


def handle_enroll_command(client, userdata, msg):
    """Handle enrollment command from HA automation"""
    try:
        data = json.loads(msg.payload.decode('utf-8'))
        cluster_id = data.get('cluster_id')
        person_id = data.get('person_id')
        display_name = data.get('display_name')
        
        if not person_id or not display_name:
            print(f"âœ— Invalid enroll command: missing person_id or display_name")
            return
        
        print(f"\nâ†’ Enrollment command received:")
        print(f"  Cluster: {cluster_id}")
        print(f"  Person: {display_name} ({person_id})")
        
        cluster = voice_clustering.get_cluster_by_id(cluster_id)
        if not cluster:
            print(f"âœ— Cluster {cluster_id} not found")
            return
        
        samples = cluster['samples']
        
        enroll_dir = Path(f"/home/user/voicebm/enroll/{person_id}")
        embeddings_dir = enroll_dir / "embeddings"
        recordings_dir = enroll_dir / "recordings"
        
        enroll_dir.mkdir(parents=True, exist_ok=True)
        embeddings_dir.mkdir(exist_ok=True)
        recordings_dir.mkdir(exist_ok=True)
        
        metadata_file = enroll_dir / 'metadata.json'
        if metadata_file.exists():
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)
                existing_samples = metadata.get('samples', [])
        else:
            metadata = {
                'person_id': person_id,
                'display_name': display_name,
                'created_at': time.strftime('%Y-%m-%d %H:%M:%S')
            }
            existing_samples = []
        
        emb_src_dir = Path("/home/user/voicebm/embeddings/living")
        rec_src_dir = Path("/home/user/voicebm/recordings/living")
        
        import shutil
        enrolled_samples = []
        enrolled_ids = []
        
        ts_enroll = int(time.time())
        expire_at_iso = datetime.datetime.utcfromtimestamp(
            ts_enroll + 3*24*3600
        ).replace(microsecond=0).isoformat() + "Z"
        
        for sample in samples:
            event_id = sample['id']
            emb_src = emb_src_dir / f"{event_id}.txt"
            rec_src = rec_src_dir / f"{event_id}.wav"
            
            emb_dst = embeddings_dir / f"{event_id}.txt"
            rec_dst = recordings_dir / f"{event_id}.wav"
            
            if emb_src.exists() and not emb_dst.exists():
                try:
                    shutil.move(str(emb_src), str(emb_dst))
                    print(f"  âœ“ Moved embedding: {event_id}.txt")
                except Exception as e:
                    print(f"  âœ— Failed to move embedding: {e}")
                    continue
            elif emb_dst.exists():
                print(f"  âš  Embedding already exists: {event_id}.txt")
            else:
                print(f"  âœ— Embedding NOT FOUND at: {emb_src}")
                continue
            
            wav_moved = False
            if rec_src.exists():
                if not rec_dst.exists():
                    try:
                        shutil.move(str(rec_src), str(rec_dst))
                        print(f"  âœ“ Moved recording: {event_id}.wav")
                        wav_moved = True
                    except Exception as e:
                        print(f"  âœ— Failed to move recording: {e}")
                else:
                    print(f"  âš  Recording already exists: {event_id}.wav")
                    wav_moved = True
            else:
                print(f"  âœ— Recording NOT FOUND at: {rec_src}")
            
            sample_entry = {
                'event_id': event_id,
                'embedding': f"embeddings/{event_id}.txt",
                'recording': f"recordings/{event_id}.wav" if wav_moved else None,
                'enrolled_at': time.strftime('%Y-%m-%d %H:%M:%S'),
                'expire_at': expire_at_iso,
                'retention_days': 3
            }
            enrolled_samples.append(sample_entry)
            enrolled_ids.append(event_id)
        
        metadata['samples'] = existing_samples + enrolled_samples
        metadata['last_updated'] = time.strftime('%Y-%m-%d %H:%M:%S')
        metadata['total_samples'] = len(metadata['samples'])
        
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        processed_file = Path("/home/user/voicebm/meta/processed.txt")
        processed_file.parent.mkdir(exist_ok=True)
        with open(processed_file, 'a') as f:
            for eid in enrolled_ids:
                f.write(f"{eid}\n")
        
        cache_file = Path("/home/user/voicebm/meta/clusters.json")
        cache_file.unlink(missing_ok=True)
        
        print(f"âœ“ Enrolled {len(enrolled_samples)} samples for {display_name}")
        print(f"  Total samples for {person_id}: {metadata['total_samples']}")
        
        response = {
            "success": True,
            "person_id": person_id,
            "enrolled_count": len(enrolled_samples),
            "total_samples": metadata['total_samples']
        }
        client.publish(
            f"{ENROLL_COMMAND_TOPIC}/response",
            json.dumps(response),
            qos=1
        )
        
    except Exception as e:
        print(f"âœ— Error handling enroll command: {e}")
        import traceback
        traceback.print_exc()
        response = {
            "success": False,
            "error": str(e)
        }
        client.publish(
            f"{ENROLL_COMMAND_TOPIC}/response",
            json.dumps(response),
            qos=1
        )


def handle_reject_command(client, userdata, msg):
    """Handle rejection command from HA automation"""
    try:
        data = json.loads(msg.payload.decode('utf-8'))
        cluster_id = data.get('cluster_id')
        
        print(f"\nâ†’ Rejection command received for cluster {cluster_id}")
        
        cluster = voice_clustering.get_cluster_by_id(cluster_id)
        if not cluster:
            print(f"âœ— Cluster {cluster_id} not found")
            return
        
        samples = cluster['samples']
        event_ids = [s['id'] for s in samples]
        
        processed_file = Path("/home/user/voicebm/meta/processed.txt")
        processed_file.parent.mkdir(exist_ok=True)
        with open(processed_file, 'a') as f:
            for eid in event_ids:
                f.write(f"{eid}\n")
        
        cache_file = Path("/home/user/voicebm/meta/clusters.json")
        cache_file.unlink(missing_ok=True)
        
        print(f"âœ“ Rejected {len(event_ids)} samples from cluster {cluster_id}")
        
        response = {
            "success": True,
            "rejected_count": len(event_ids)
        }
        client.publish(
            f"{REJECT_COMMAND_TOPIC}/response",
            json.dumps(response),
            qos=1
        )
        
    except Exception as e:
        print(f"âœ— Error handling reject command: {e}")
        response = {
            "success": False,
            "error": str(e)
        }
        client.publish(
            f"{REJECT_COMMAND_TOPIC}/response",
            json.dumps(response),
            qos=1
        )


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print(f"âœ“ Connected to MQTT broker at {BROKER}:{PORT}")
        
        client.subscribe(ENROLL_COMMAND_TOPIC, qos=1)
        client.subscribe(REJECT_COMMAND_TOPIC, qos=1)
        
        print(f"âœ“ Subscribed to command topics")
    else:
        print(f"âœ— Failed to connect, reason code: {reason_code}")


def on_message(client, userdata, msg):
    """Route messages to appropriate handlers"""
    if msg.topic == ENROLL_COMMAND_TOPIC:
        handle_enroll_command(client, userdata, msg)
    elif msg.topic == REJECT_COMMAND_TOPIC:
        handle_reject_command(client, userdata, msg)


def main():
    """Main cluster publisher loop"""
    global last_cluster_count, mqtt_client
    
    print("=" * 60)
    print("VoiceBM Cluster Publisher")
    print("=" * 60)
    print(f"Room: {ROOM}")
    print(f"MQTT Broker: {BROKER}:{PORT}")
    print("=" * 60)
    
    mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    mqtt_client.username_pw_set(USER, PASS)
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message
    
    try:
        mqtt_client.connect(BROKER, PORT, 60)
    except Exception as e:
        print(f"âœ— MQTT connection failed: {e}")
        return
    
    mqtt_client.loop_start()
    
    time.sleep(1)
    publish_discovery(mqtt_client)
    
    print("\nâœ“ Monitoring for voice clusters...")
    print("Press Ctrl+C to exit\n")
    
    cycle = 0
    
    try:
        while True:
            cycle += 1
            
            try:
                clusters = voice_clustering.generate_clusters(force_refresh=False)
                
                if len(clusters) != last_cluster_count:
                    print(f"\n[Cycle {cycle}] Cluster update:")
                    print(f"  Pending clusters: {len(clusters)}")
                    
                    if clusters:
                        total_samples = sum(c['stats']['count'] for c in clusters)
                        print(f"  Total samples: {total_samples}")
                        
                        for c in clusters:
                            print(f"    Cluster {c['cluster_id']}: {c['stats']['count']} samples, "
                                  f"similarity={c['stats']['avg_similarity']:.3f}")
                    
                    publish_cluster_summary(mqtt_client, clusters)
                    
                    for cluster in clusters:
                        publish_cluster_details(mqtt_client, cluster)
                    
                    last_cluster_count = len(clusters)
                
            except Exception as e:
                print(f"âœ— Error in publish cycle: {e}")
            
            time.sleep(10)
            
    except KeyboardInterrupt:
        print("\n\nShutting down...")
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
        print("âœ“ Cluster publisher stopped")


if __name__ == "__main__":
    main()
```


# Global — system-wide control, discovery, commands


## 7. `voicebm_global_publisher.py` <a id="7-voicebm-global-publisherpy"></a>

_Voice Biometrics MQTT Service - Processes STT analysis requests from Wyoming container_

```python
#!/usr/bin/env python3
"""
Voice Biometrics MQTT Service - Processes STT analysis requests from Wyoming container
Runs on HOST with access to the Sherpa-ONNX conda environment

ACTIVE PIPELINE SCRIPT - Uses slider-controlled threshold (MATCH_T_ACTIVE)
The passive pipeline (publish_identity_living.py) uses MATCH_T_PASSIVE = 0.22.
This script responds to the HA slider for adjustable STT injection threshold.

Features:
- Responds to voice analysis requests from Docker handler.py
- Tracks injection toggle state and includes in response
- Maintains pending buffer (5) for unidentified voices
- Handles enrollment/rejection of pending voices

CRITICAL FIX APPLIED:
- Unknown speakers (speaker_id=None) now map to virtual "user" identity
- "user" blocklist switch now actually blocks unknowns (removed skeleton key)
"""

import os
import json
import time
import shutil
import subprocess
import tempfile
import datetime
from pathlib import Path
import numpy as np
import paho.mqtt.client as mqtt

# Configuration
# MQTT Configuration (centralized)
import sys
sys.path.insert(0, '/home/user/voicebm')
from voicebm_config import get_mqtt_config, get_active_lead_trim_ms, update_voicebm_config_key

# Emote Edition — optional plug-in
# If voicebm_emote.py is not installed, both functions become no-ops.
# Removing the module file is sufficient to disable the feature entirely.
try:
    from voicebm_emote import run_emote, publish_emote_discovery
    print("[emote] Emote Edition loaded")
except ImportError:
    def run_emote(audio_path, client): pass
    def publish_emote_discovery(client): pass
    print("[emote] Emote Edition not installed — skipping")

mqtt_config = get_mqtt_config()
BROKER = mqtt_config['broker']
PORT = mqtt_config['port']
USER = mqtt_config['user']
PASS = mqtt_config['password']

# UPDATED PATH FOR WRAPPER SCRIPT (under /home/user/voicebm/bin/)
SHERPA_SCRIPT = "/home/user/voicebm/bin/embed_stt.sh"
SHERPA_MODEL = "/home/user/sherpa_models/nemo_en_titanet_small.onnx"

# ACTIVE pipeline lead-trim (ms). 0 = OFF. Strips wake-word chime from the
# front of the audio BEFORE embedding so the chime never contaminates a match
# or a pending enrollment. Stored WAV is never modified.
# Re-read live in create_embedding so the HA slider takes effect without restart.
ACTIVE_LEAD_TRIM_MS = get_active_lead_trim_ms()

# GALLERY ROLLOVER CAP:
# Max embedding samples retained per person. When a new enrollment would push
# a person over this count, the OLDEST sample(s) are pruned (oldest by
# enrolled_at). Slider-controlled, stored in thresholds.json as GALLERY_MAX.
# 0 or missing = unlimited (no pruning).
DEFAULT_GALLERY_MAX = 0
ENROLL_DIR = "/home/user/voicebm/enroll"
THRESHOLD_FILE = "/home/user/voicebm/out/thresholds.json"

# THRESHOLD SPLIT:
# - This script uses MATCH_T_ACTIVE (slider-controlled, default 0.50)
# - Passive pipeline uses MATCH_T_PASSIVE = 0.22 (fixed)
DEFAULT_THRESHOLD_ACTIVE = 0.50

REQUEST_TOPIC = "voicebm/stt/analyze_request"
RESPONSE_TOPIC = "voicebm/stt/analyze_response"

# Pending enrollment configuration
PENDING_DIR = Path("/home/user/voicebm/pending_active")
PENDING_RECORDINGS = PENDING_DIR / "recordings"
PENDING_EMBEDDINGS = PENDING_DIR / "embeddings"
PENDING_JSON = PENDING_DIR / "pending.json"
PENDING_BUFFER_SIZE = 5
PENDING_EXPIRE_HOURS = 1

# MQTT Topics
PENDING_TOPIC = "voicebm/pending_active"
PENDING_ENROLL_TOPIC = "voicebm/pending_active/enroll"
PENDING_REJECT_TOPIC = "voicebm/pending_active/reject"
PENDING_CLEAR_TOPIC = "voicebm/pending_active/clear"
INJECT_STATE_TOPIC = "voicebm/inject_identity"

# Dashboard state files (for Flask/OpenWebUI multi-platform sync)
META_DIR = Path("/home/user/voicebm/meta")
SETTINGS_FILE = META_DIR / "settings.json"
ACTIVE_STATE_FILE = META_DIR / "active_state.json"

# Global state
inject_identity_enabled = True
blocked_speakers = set()  # In-memory set of blocked person_ids, populated from MQTT

# Global state for pending enrollment name
pending_person_name = ""

# Track last published person for state clearing (prevents stuck sensors in HA)
last_published_person = None

# Track request_ids that have been processed as biopsy
# Used so full audio knows whether the biopsy already published active identity
# (and falls back to publishing active identity itself if no biopsy ran)
biopsy_seen_ids = set()


def is_speaker_blocked(speaker_id):
    """
    Check if a speaker is on the blocklist.
    
    Uses in-memory set populated from MQTT subscriptions.
    NO file reads - fast and simple.
    
    Args:
        speaker_id: The person_id to check
    
    Returns:
        bool: True if blocked, False otherwise
    """
    if not speaker_id:
        return False
    
    is_blocked = speaker_id in blocked_speakers
    print(f"  [BLOCKLIST] {speaker_id} blocked={is_blocked} (in-memory check)")
    return is_blocked


def handle_blocklist_state(client, userdata, msg):
    """
    Handle blocklist state updates from MQTT.
    Topic pattern: voicebm/blocklist/{person_id}
    Payload: 'ON' or 'OFF'
    """
    global blocked_speakers
    
    try:
        parts = msg.topic.split('/')
        if len(parts) >= 3:
            person_id = parts[2]
            state = msg.payload.decode('utf-8')
            
            if state == "ON":
                blocked_speakers.add(person_id)
                print(f"[BLOCKLIST] Added to blocklist: {person_id}")
            else:
                blocked_speakers.discard(person_id)
                print(f"[BLOCKLIST] Removed from blocklist: {person_id}")
            
            print(f"[BLOCKLIST] Current blocked speakers: {blocked_speakers}")
    except Exception as e:
        print(f"[BLOCKLIST] Error handling state update: {e}")


# ============================================================================
# DASHBOARD STATE FILE WRITERS (Multi-platform sync via filesystem)
# ============================================================================

def write_settings_file():
    """
    Write settings.json for dashboard.
    Syncs injection state and threshold to filesystem for Flask/OpenWebUI access.
    """
    try:
        META_DIR.mkdir(parents=True, exist_ok=True)
        
        # Read current threshold from thresholds.json
        threshold = DEFAULT_THRESHOLD_ACTIVE
        try:
            if os.path.exists(THRESHOLD_FILE):
                with open(THRESHOLD_FILE, 'r') as f:
                    thr = json.load(f)
                    threshold = float(thr.get("MATCH_T_ACTIVE", DEFAULT_THRESHOLD_ACTIVE))
        except:
            pass
        
        settings = {
            "inject_identity": inject_identity_enabled,
            "active_threshold": threshold,
            "last_updated": time.strftime('%Y-%m-%d %H:%M:%S')
        }
        
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(settings, f, indent=2)
            
    except Exception as e:
        print(f"Warning: Could not write settings.json: {e}")


def write_active_state_file(speaker_id, display_name, confidence, decision):
    """
    Write active_state.json for dashboard.
    Syncs current speaker identity to filesystem for Flask/OpenWebUI access.
    """
    try:
        META_DIR.mkdir(parents=True, exist_ok=True)
        
        active_state = {
            "speaker_id": speaker_id,
            "display_name": display_name or "user",
            "confidence": round(confidence, 4),
            "decision": decision,
            "timestamp": time.time(),
            "ts_iso": datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
        }
        
        with open(ACTIVE_STATE_FILE, 'w') as f:
            json.dump(active_state, f, indent=2)
            
    except Exception as e:
        print(f"Warning: Could not write active_state.json: {e}")


def setup_pending_dirs():
    """Create pending enrollment directories."""
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    PENDING_RECORDINGS.mkdir(exist_ok=True)
    PENDING_EMBEDDINGS.mkdir(exist_ok=True)
    
    if not PENDING_JSON.exists():
        save_pending_buffer([])


def load_pending_buffer():
    """Load pending enrollment buffer from JSON."""
    try:
        if PENDING_JSON.exists():
            with open(PENDING_JSON, 'r') as f:
                return json.load(f)
    except Exception as e:
        print(f"Failed to load pending buffer: {e}")
    return []


def save_pending_buffer(buffer):
    """Save pending enrollment buffer to JSON."""
    try:
        with open(PENDING_JSON, 'w') as f:
            json.dump(buffer, f, indent=2)
    except Exception as e:
        print(f"Failed to save pending buffer: {e}")


def cleanup_expired_pending():
    """Remove expired entries from pending buffer."""
    buffer = load_pending_buffer()
    if not buffer:
        return buffer
    
    now_ts = time.time()
    expire_seconds = PENDING_EXPIRE_HOURS * 3600
    
    valid = []
    for entry in buffer:
        entry_ts = entry.get('timestamp', 0)
        if now_ts - entry_ts < expire_seconds:
            valid.append(entry)
        else:
            try:
                wav_path = PENDING_RECORDINGS / f"{entry['id']}.wav"
                emb_path = PENDING_EMBEDDINGS / f"{entry['id']}.txt"
                if wav_path.exists():
                    wav_path.unlink()
                if emb_path.exists():
                    emb_path.unlink()
                print(f"Expired pending entry removed: {entry['id']}")
            except Exception as e:
                print(f"Failed to cleanup expired {entry['id']}: {e}")
    
    if len(valid) != len(buffer):
        save_pending_buffer(valid)
    
    return valid


def add_to_pending_buffer(audio_path, embedding, request_id):
    """Add unidentified voice to pending enrollment buffer."""
    buffer = cleanup_expired_pending()
    
    pending_id = f"active_{int(time.time() * 1000)}"
    
    try:
        wav_dst = PENDING_RECORDINGS / f"{pending_id}.wav"
        emb_dst = PENDING_EMBEDDINGS / f"{pending_id}.txt"
        
        if os.path.exists(audio_path):
            shutil.copy2(audio_path, wav_dst)
        else:
            print(f"Source audio not found: {audio_path}")
            return None
        
        np.savetxt(emb_dst, embedding)
        
        entry = {
            "id": pending_id,
            "request_id": request_id,
            "timestamp": time.time(),
            "ts_iso": datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            "audio_url": f"http://127.0.0.1:9090/pending/{pending_id}.wav",
            "source": "active_node",
        }
        
        buffer.append(entry)
        
        while len(buffer) > PENDING_BUFFER_SIZE:
            removed = buffer.pop(0)
            try:
                old_wav = PENDING_RECORDINGS / f"{removed['id']}.wav"
                old_emb = PENDING_EMBEDDINGS / f"{removed['id']}.txt"
                if old_wav.exists():
                    old_wav.unlink()
                if old_emb.exists():
                    old_emb.unlink()
                print(f"Buffer overflow, removed oldest: {removed['id']}")
            except Exception as e:
                print(f"Failed to remove overflow {removed['id']}: {e}")
        
        save_pending_buffer(buffer)
        print(f"Added to pending buffer: {pending_id} (buffer size: {len(buffer)})")
        
        return entry
        
    except Exception as e:
        print(f"Failed to add to pending buffer: {e}")
        return None


def publish_pending_status(client):
    """
    Publish current pending buffer status to MQTT.

    IMPORTANT CHANGE vs Claude's original:
    - 'current' entry is now the *newest* pending entry (buffer[-1]),
      not the oldest (buffer[0]).
    """
    buffer = load_pending_buffer()
    
    payload = {
        "count": len(buffer),
        "max_size": PENDING_BUFFER_SIZE,
        "expire_hours": PENDING_EXPIRE_HOURS,
        "entries": buffer,
    }
    
    client.publish(PENDING_TOPIC, json.dumps(payload), qos=1, retain=True)
    
    # Surface the NEWEST pending entry as "current"
    if buffer:
        current = buffer[-1]
        client.publish(
            "voicebm/pending_active/current_id",
            current.get("id", ""),
            qos=1,
            retain=True,
        )
        client.publish(
            "voicebm/pending_active/audio_url",
            current.get("audio_url", ""),
            qos=1,
            retain=True,
        )
    else:
        client.publish("voicebm/pending_active/current_id", "none", qos=1, retain=True)
        client.publish("voicebm/pending_active/audio_url", "", qos=1, retain=True)
    
    print(f"Published pending status: {len(buffer)} entries")


def load_gallery():
    """Load enrolled speakers and compute centroids."""
    people = {}
    enroll_path = Path(ENROLL_DIR)
    
    if not enroll_path.exists():
        print(f"Warning: Enrollment directory not found at /home/user/voicebm/enroll")
        return {}
    
    try:
        for person_dir in enroll_path.iterdir():
            if not person_dir.is_dir():
                continue
            
            person_id = person_dir.name
            embeddings_dir = person_dir / "embeddings"
            metadata_file = person_dir / "metadata.json"
            
            if metadata_file.exists():
                try:
                    with open(metadata_file, "r") as f:
                        metadata = json.load(f)
                        display_name = metadata.get(
                            "display_name", person_id.replace("_", " ").title()
                        )
                except:
                    display_name = person_id.replace("_", " ").title()
            else:
                display_name = person_id.replace("_", " ").title()
            
            if not embeddings_dir.exists():
                continue
            
            vectors = []
            for emb_file in embeddings_dir.glob("*.txt"):
                try:
                    v = np.loadtxt(emb_file)
                    if v is not None and len(v) > 0:
                        vectors.append(v)
                except Exception as e:
                    print(f"  Failed to load {emb_file.name}: {e}")
            
            if vectors:
                people[(person_id, display_name)] = vectors
    
    except Exception as e:
        print(f"Error loading gallery: {e}")
        return {}
    
    cents = {}
    for (sid, name), vecs in people.items():
        cents[(sid, name)] = np.mean(vecs, axis=0)
    
    print(f"Loaded {len(cents)} enrolled speakers")
    return cents


def make_lead_trimmed_wav(wav_path, trim_ms):
    """
    Write a copy of wav_path with the first trim_ms milliseconds removed.

    Uses the stdlib wave module (no extra dependencies). Returns the path to a
    new temp WAV the caller is responsible for deleting. If trimming is not
    possible (trim_ms <= 0, or the clip is shorter than the trim), returns None
    so the caller falls back to the original untrimmed audio.

    The source WAV on disk is never modified.
    """
    if trim_ms <= 0:
        return None

    import wave

    try:
        with wave.open(wav_path, 'rb') as wf:
            n_channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            framerate = wf.getframerate()
            n_frames = wf.getnframes()

            trim_frames = int(framerate * (trim_ms / 1000.0))

            # If the clip is shorter than (or equal to) the trim, do not trim;
            # embedding silence/nothing is worse than embedding the whole clip.
            if trim_frames <= 0 or trim_frames >= n_frames:
                print(f"  [TRIM] Skipped: trim {trim_ms}ms >= clip length "
                      f"({n_frames} frames @ {framerate}Hz)")
                return None

            wf.setpos(trim_frames)
            remaining = wf.readframes(n_frames - trim_frames)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            trimmed_path = tmp.name

        with wave.open(trimmed_path, 'wb') as out:
            out.setnchannels(n_channels)
            out.setsampwidth(sampwidth)
            out.setframerate(framerate)
            out.writeframes(remaining)

        print(f"  [TRIM] Stripped {trim_ms}ms ({trim_frames} frames) "
              f"from lead before embedding")
        return trimmed_path

    except Exception as e:
        print(f"  [TRIM] Failed to trim lead ({e}); using untrimmed audio")
        return None


def get_gallery_max():
    """Read GALLERY_MAX from thresholds.json. 0/missing = unlimited."""
    try:
        if os.path.exists(THRESHOLD_FILE):
            with open(THRESHOLD_FILE, "r") as f:
                return int(json.load(f).get("GALLERY_MAX", DEFAULT_GALLERY_MAX))
    except Exception:
        pass
    return DEFAULT_GALLERY_MAX


def enforce_gallery_cap(person_dir, metadata):
    """
    Trim a person's gallery to GALLERY_MAX samples, dropping the OLDEST first.

    Operates on metadata['samples'] (each entry has 'enrolled_at', 'embedding',
    and optional 'recording' relative paths). Deletes the pruned embedding .txt
    and .wav files from disk, updates metadata in place, and returns it.

    No-op when GALLERY_MAX <= 0 (unlimited) or sample count is within the cap.
    Pure filesystem + metadata; does NOT touch the live gallery centroids (the
    caller reloads the gallery after enrollment).
    """
    cap = get_gallery_max()
    samples = metadata.get("samples", [])
    if cap <= 0 or len(samples) <= cap:
        return metadata

    # Oldest first. Entries without enrolled_at sort to the front (treated oldest).
    ordered = sorted(samples, key=lambda s: s.get("enrolled_at", ""))
    drop_count = len(ordered) - cap
    to_drop = ordered[:drop_count]
    keep = ordered[drop_count:]

    for s in to_drop:
        for rel_key in ("embedding", "recording"):
            rel = s.get(rel_key)
            if not rel:
                continue
            fpath = Path(person_dir) / rel
            try:
                if fpath.exists():
                    fpath.unlink()
                    print(f"  [gallery_cap] Pruned {rel_key}: {fpath.name}")
            except Exception as e:
                print(f"  [gallery_cap] Failed to prune {fpath}: {e}")

    metadata["samples"] = keep
    metadata["total_samples"] = len(keep)
    print(f"  [gallery_cap] Trimmed gallery to {len(keep)}/{cap} samples")
    return metadata


def create_embedding(wav_path):
    """Create embedding using Sherpa-ONNX via bash wrapper.

    If the active lead-trim (ms) is > 0, the wake-word chime is stripped from
    the front of the audio before embedding. The original wav_path is never
    modified; a trimmed temp copy is embedded and then deleted. This single
    chokepoint covers BOTH identity matching and pending enrollment, since both
    consume the embedding returned here.
    """
    trimmed_path = make_lead_trimmed_wav(wav_path, 900)
    embed_input = trimmed_path if trimmed_path else wav_path

    try:
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
            embedding_path = tmp.name
        
        result = subprocess.run(
            [SHERPA_SCRIPT, embed_input, embedding_path],
            capture_output=True,
            text=True,
            timeout=30,
        )
        
        if result.returncode != 0:
            print(f"Sherpa embedding failed: {result.stderr}")
            return None
        
        embedding = np.loadtxt(embedding_path)
        os.unlink(embedding_path)
        
        return embedding
        
    except Exception as e:
        print(f"Embedding creation failed: {e}")
        return None
    finally:
        if trimmed_path:
            try:
                os.unlink(trimmed_path)
            except OSError:
                pass


def cosine_similarity(a, b):
    """Calculate cosine similarity."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


# ============================================================================
# PER-PERSON THRESHOLD OVERRIDE SUPPORT
# ============================================================================

# Cache for per-person thresholds (updated via MQTT subscription)
person_thresholds = {}


def get_person_threshold(person_id, global_threshold):
    """
    Get threshold for a specific person.
    
    Returns per-person threshold if set, otherwise returns global threshold.
    
    Args:
        person_id: Person identifier
        global_threshold: Fallback global threshold
    
    Returns:
        Threshold value to use for this person
    """
    if person_id in person_thresholds:
        custom = person_thresholds[person_id]
        print(f"  Using custom threshold for {person_id}: {custom:.2f}")
        return custom
    return global_threshold


def verify_person_threshold(speaker_id, confidence, global_threshold):
    """
    Verify that identified speaker meets their custom threshold (if set).
    
    If person has custom threshold and confidence doesn't meet it,
    returns None (treat as unknown).
    
    Args:
        speaker_id: Identified speaker ID
        confidence: Confidence score from identification
        global_threshold: Global threshold used for initial identification
    
    Returns:
        speaker_id if threshold met, None if custom threshold not met
    """
    if speaker_id is None:
        return None
    
    # Check if person has custom threshold
    if speaker_id in person_thresholds:
        custom_threshold = person_thresholds[speaker_id]
        if confidence < custom_threshold:
            print(f"  Custom threshold check FAILED: {confidence:.4f} < {custom_threshold:.2f} for {speaker_id}")
            return None  # Reject match - doesn't meet person's custom threshold
    
    return speaker_id


def identify_speaker(embedding, gallery, threshold):
    """Identify speaker by comparing embedding against gallery."""
    if embedding is None or not gallery:
        return None, None, 0.0
    
    best_sid = None
    best_name = None
    best_sim = -1.0
    
    all_matches = []
    
    for (person_id, display_name), centroid in gallery.items():
        sim = cosine_similarity(embedding, centroid)
        all_matches.append((person_id, display_name, sim))
        if sim > best_sim:
            best_sim = sim
            best_sid = person_id
            best_name = display_name
    
    all_matches.sort(key=lambda x: x[2], reverse=True)
    
    print("  Match candidates:")
    for pid, pname, sim in all_matches[:5]:
        marker = "[BEST]" if pid == best_sid else "      "
        above_threshold = "PASS" if sim >= threshold else "FAIL"
        print(f"    {marker} {above_threshold} {pname:20s} ({pid:15s}) = {sim:.4f}")
    
    if best_sim >= threshold:
        print(f"  [MATCH] Identified: {best_name} ({best_sid}) confidence={best_sim:.4f}")
        return best_sid, best_name, best_sim
    else:
        print(f"  No match (best={best_sim:.4f} < threshold={threshold})")
        return None, None, best_sim


def publish_discovery(client):
    """Publish MQTT Discovery for pending enrollment controls under VoiceBM device."""
    discovery_prefix = "homeassistant"
    
    device = {
        "identifiers": ["voicebm"],
        "name": "Voice Biometrics",
        "manufacturer": "David M. Dryver Sr.",
        "model": "Home Assistant Voice Biometrics",
        "sw_version": "2.0"
    }
    
    # Pending Active Voices count sensor
    pending_count_config = {
        "name": "Pending Active Voices",
        "unique_id": "voicebm_pending_active_count",
        "state_topic": PENDING_TOPIC,
        "value_template": "{{ value_json.count }}",
        "json_attributes_topic": PENDING_TOPIC,
        "icon": "mdi:account-question",
        "device": device,
    }
    
    client.publish(
        f"{discovery_prefix}/sensor/voicebm_pending_active_count/config",
        json.dumps(pending_count_config),
        qos=1,
        retain=True,
    )
    
    # Pending Active Audio URL sensor
    pending_audio_config = {
        "name": "Pending Active Audio URL",
        "unique_id": "voicebm_pending_active_audio_url",
        "state_topic": "voicebm/pending_active/audio_url",
        "icon": "mdi:volume-high",
        "device": device,
    }
    
    client.publish(
        f"{discovery_prefix}/sensor/voicebm_pending_active_audio_url/config",
        json.dumps(pending_audio_config),
        qos=1,
        retain=True,
    )
    
    # Pending Active ID sensor
    pending_id_config = {
        "name": "Pending Active ID",
        "unique_id": "voicebm_pending_active_id",
        "state_topic": "voicebm/pending_active/current_id",
        "icon": "mdi:identifier",
        "device": device,
    }
    
    client.publish(
        f"{discovery_prefix}/sensor/voicebm_pending_active_id/config",
        json.dumps(pending_id_config),
        qos=1,
        retain=True,
    )
    
    # Text input for person name to enroll pending voice as
    pending_name_config = {
        "name": "Pending Person Name",
        "unique_id": "voicebm_pending_person_name",
        "command_topic": "voicebm/pending_active/person_name/set",
        "state_topic": "voicebm/pending_active/person_name",
        "icon": "mdi:account-edit",
        "device": device,
    }
    
    client.publish(
        f"{discovery_prefix}/text/voicebm_pending_person_name/config",
        json.dumps(pending_name_config),
        qos=1,
        retain=True,
    )
    
    # Initialize pending person name
    client.publish("voicebm/pending_active/person_name", "", qos=1, retain=True)
    
    # Enroll Pending button
    enroll_btn_config = {
        "name": "Enroll Pending Voice",
        "unique_id": "voicebm_pending_enroll_btn",
        "command_topic": "voicebm/pending_active/enroll_btn",
        "payload_press": "PRESS",
        "icon": "mdi:account-plus",
        "device": device,
    }
    
    client.publish(
        f"{discovery_prefix}/button/voicebm_pending_enroll_btn/config",
        json.dumps(enroll_btn_config),
        qos=1,
        retain=True,
    )
    
    # Reject Pending button
    reject_btn_config = {
        "name": "Reject Pending Voice",
        "unique_id": "voicebm_pending_reject_btn",
        "command_topic": "voicebm/pending_active/reject_btn",
        "payload_press": "PRESS",
        "icon": "mdi:account-remove",
        "device": device,
    }
    
    client.publish(
        f"{discovery_prefix}/button/voicebm_pending_reject_btn/config",
        json.dumps(reject_btn_config),
        qos=1,
        retain=True,
    )
    
    # Play Pending Audio button
    play_btn_config = {
        "name": "Play Pending Audio",
        "unique_id": "voicebm_pending_play_btn",
        "command_topic": "voicebm/pending_active/play_btn",
        "payload_press": "PRESS",
        "icon": "mdi:play-circle",
        "device": device,
    }
    
    client.publish(
        f"{discovery_prefix}/button/voicebm_pending_play_btn/config",
        json.dumps(play_btn_config),
        qos=1,
        retain=True,
    )
    
    # Clear All Pending button
    clear_btn_config = {
        "name": "Clear All Pending",
        "unique_id": "voicebm_pending_clear_btn",
        "command_topic": "voicebm/pending_active/clear",
        "payload_press": "PRESS",
        "icon": "mdi:delete-sweep",
        "device": device,
    }
    
    client.publish(
        f"{discovery_prefix}/button/voicebm_pending_clear_btn/config",
        json.dumps(clear_btn_config),
        qos=1,
        retain=True,
    )
    
    # Active Identity Entities (8) - Show STT analysis results
    # These mirror what passive nodes publish but for the active STT pipeline
    
    # 1. Active Speaker (display name) — plain string, sourced from biopsy path
    active_speaker_config = {
        "name": "Active Speaker",
        "unique_id": "voicebm_active_speaker",
        "state_topic": "voicebm/active_speaker",
        "icon": "mdi:account-voice",
        "device": device,
    }
    client.publish(
        f"{discovery_prefix}/sensor/voicebm_active_speaker/config",
        json.dumps(active_speaker_config),
        qos=1,
        retain=True,
    )
    client.publish("voicebm/active_speaker", "none", qos=1, retain=True)

    # Reset voicebm/active/identity so stale retained user state does not leak
    # into HA while it transitions from old discovery config to new plain-string topics
    reset_identity_data = {
        "speaker_id": "none",
        "display_name": "none",
        "confidence": 0.0,
        "decision": "none",
        "score": 0.0
    }
    client.publish("voicebm/active/identity", json.dumps(reset_identity_data), qos=1, retain=True)

    # 2. Active Speaker ID — plain string, sourced from biopsy path
    active_speaker_id_config = {
        "name": "Active Speaker ID",
        "unique_id": "voicebm_active_speaker_id",
        "state_topic": "voicebm/active_speaker_id",
        "icon": "mdi:identifier",
        "device": device,
    }
    client.publish(
        f"{discovery_prefix}/sensor/voicebm_active_speaker_id/config",
        json.dumps(active_speaker_id_config),
        qos=1,
        retain=True,
    )
    client.publish("voicebm/active_speaker_id", "none", qos=1, retain=True)

    # Current Speaker ID — plain string, companion to voicebm/current_speaker
    current_speaker_id_config = {
        "name": "Current Speaker ID",
        "unique_id": "voicebm_current_speaker_id",
        "state_topic": "voicebm/current_speaker_id",
        "icon": "mdi:identifier",
        "device": device,
    }
    client.publish(
        f"{discovery_prefix}/sensor/voicebm_current_speaker_id/config",
        json.dumps(current_speaker_id_config),
        qos=1,
        retain=True,
    )
    client.publish("voicebm/current_speaker_id", "none", qos=1, retain=True)
    
    # 3. Active Confidence
    active_confidence_config = {
        "name": "Active Voice Confidence",
        "unique_id": "voicebm_active_confidence",
        "state_topic": "voicebm/active/identity",
        "value_template": "{{ (value_json.confidence * 100) | round(1) }}",
        "unit_of_measurement": "%",
        "icon": "mdi:percent",
        "device": device,
    }
    client.publish(
        f"{discovery_prefix}/sensor/voicebm_active_confidence/config",
        json.dumps(active_confidence_config),
        qos=1,
        retain=True,
    )
    
    # 4. Active Decision
    active_decision_config = {
        "name": "Active Voice Decision",
        "unique_id": "voicebm_active_decision",
        "state_topic": "voicebm/active/identity",
        "value_template": "{{ value_json.decision }}",
        "icon": "mdi:check-decagram",
        "device": device,
    }
    client.publish(
        f"{discovery_prefix}/sensor/voicebm_active_decision/config",
        json.dumps(active_decision_config),
        qos=1,
        retain=True,
    )
    
    # 5. Active Score
    active_score_config = {
        "name": "Active Voice Score",
        "unique_id": "voicebm_active_score",
        "state_topic": "voicebm/active/identity",
        "value_template": "{{ value_json.score | round(2) if value_json.score else 0.0 }}",
        "unit_of_measurement": "score",
        "icon": "mdi:chart-line",
        "device": device,
    }
    client.publish(
        f"{discovery_prefix}/sensor/voicebm_active_score/config",
        json.dumps(active_score_config),
        qos=1,
        retain=True,
    )
    
    # 6. Active Voice Accepted (binary sensor - Detected/Unknown)
    active_accepted_config = {
        "name": "Active Voice Accepted",
        "unique_id": "voicebm_active_accepted",
        "state_topic": "voicebm/active/identity",
        "value_template": "{{ 'Detected' if value_json.decision == 'accepted' else 'Unknown' }}",
        "icon": "mdi:check-circle",
        "device": device,
    }
    client.publish(
        f"{discovery_prefix}/sensor/voicebm_active_accepted/config",
        json.dumps(active_accepted_config),
        qos=1,
        retain=True,
    )
    
    # 7. Active Unprocessed Samples (placeholder - set to 0 for now)
    active_unprocessed_config = {
        "name": "Active Unprocessed Samples",
        "unique_id": "voicebm_active_unprocessed",
        "state_topic": "voicebm/active/unprocessed_samples",
        "icon": "mdi:file-question",
        "device": device,
    }
    client.publish(
        f"{discovery_prefix}/sensor/voicebm_active_unprocessed/config",
        json.dumps(active_unprocessed_config),
        qos=1,
        retain=True,
    )
    # Initialize to 0
    client.publish("voicebm/active/unprocessed_samples", "0", qos=1, retain=True)
    
    # 8. Active Current Event ID
    active_event_id_config = {
        "name": "Active Current Event ID",
        "unique_id": "voicebm_active_event_id",
        "state_topic": "voicebm/active/current_event_id",
        "icon": "mdi:file-document",
        "device": device,
    }
    client.publish(
        f"{discovery_prefix}/sensor/voicebm_active_event_id/config",
        json.dumps(active_event_id_config),
        qos=1,
        retain=True,
    )
    
    # Active Match Threshold Number Input (adjustable STT security threshold)
    active_threshold_config = {
        "name": "Active Match Threshold",
        "unique_id": "voicebm_active_threshold",
        "command_topic": "voicebm/active/threshold/set",
        "state_topic": "voicebm/active/threshold",
        "min": 0.01,
        "max": 1.00,
        "step": 0.01,
        "mode": "slider",
        "icon": "mdi:tune-vertical",
        "device": device,
    }
    client.publish(
        f"{discovery_prefix}/number/voicebm_active_threshold/config",
        json.dumps(active_threshold_config),
        qos=1,
        retain=True,
    )
    
    # Initialize active threshold from thresholds.json
    try:
        with open(THRESHOLD_FILE, 'r') as f:
            thr = json.load(f)
            active_threshold_value = float(thr.get("MATCH_T_ACTIVE", DEFAULT_THRESHOLD_ACTIVE))
    except:
        active_threshold_value = DEFAULT_THRESHOLD_ACTIVE
    
    client.publish("voicebm/active/threshold", str(active_threshold_value), qos=1, retain=True)
    print(f"  Initialized active threshold: {active_threshold_value}")
    # Active Lead Trim Number Input (F-02) - ms stripped from front of active
    # audio before embedding, to drop the wake-word chime. 0 = OFF.
    lead_trim_config = {
        "name": "Active Lead Trim",
        "unique_id": "voicebm_active_lead_trim",
        "command_topic": "voicebm/active/lead_trim/set",
        "state_topic": "voicebm/active/lead_trim",
        "min": 0,
        "max": 2000,
        "step": 50,
        "mode": "slider",
        "unit_of_measurement": "ms",
        "icon": "mdi:content-cut",
        "device": device,
    }
    client.publish(
        f"{discovery_prefix}/number/voicebm_active_lead_trim/config",
        json.dumps(lead_trim_config),
        qos=1,
        retain=True,
    )
    client.publish("voicebm/active/lead_trim", str(get_active_lead_trim_ms()), qos=1, retain=True)
    print(f"  Initialized active lead trim: {get_active_lead_trim_ms()} ms")

    # Gallery Max Number Input (rollover cap: max samples per person, 0=unlimited)
    gallery_max_config = {
        "name": "Gallery Max",
        "unique_id": "voicebm_gallery_max",
        "command_topic": "voicebm/gallery_max/set",
        "state_topic": "voicebm/gallery_max",
        "min": 0,
        "max": 200,
        "step": 1,
        "mode": "box",
        "unit_of_measurement": "samples",
        "icon": "mdi:image-multiple",
        "device": device,
    }
    client.publish(
        f"{discovery_prefix}/number/voicebm_gallery_max/config",
        json.dumps(gallery_max_config),
        qos=1,
        retain=True,
    )
    client.publish("voicebm/gallery_max", str(get_gallery_max()), qos=1, retain=True)
    print(f"  Initialized gallery max: {get_gallery_max()}")
    
    # Aggregate Blocklist sensor (B-04)
    blocklist_state_config = {
        "name": "Blocklist State",
        "unique_id": "voicebm_blocklist_state",
        "state_topic": "voicebm/blocklist_state",
        "value_template": "{{ value_json.values() | select('equalto', true) | list | count }}",
        "json_attributes_topic": "voicebm/blocklist_state",
        "unit_of_measurement": "blocked",
        "icon": "mdi:account-cancel",
        "device": device,
    }
    client.publish(
        f"{discovery_prefix}/sensor/voicebm_blocklist_state/config",
        json.dumps(blocklist_state_config),
        qos=1,
        retain=True,
    )

    
    print("Published MQTT Discovery for pending enrollment controls + Active Identity entities + Active Threshold")


def handle_pending_enroll(client, userdata, msg):
    """Handle enrollment command for pending active voice."""
    try:
        data = json.loads(msg.payload.decode("utf-8"))
        pending_id = data.get("id")
        person_id = data.get("person_id", "").strip().lower().replace(" ", "_")
        display_name = data.get("display_name", "").strip()
        
        if not pending_id or not person_id or not display_name:
            print("Enroll command missing required fields")
            return
        
        print(f"Enrolling pending {pending_id} as {display_name} ({person_id})")
        
        buffer = load_pending_buffer()
        entry = None
        for e in buffer:
            if e["id"] == pending_id:
                entry = e
                break
        
        if not entry:
            print(f"Pending entry not found: {pending_id}")
            return
        
        wav_src = PENDING_RECORDINGS / f"{pending_id}.wav"
        emb_src = PENDING_EMBEDDINGS / f"{pending_id}.txt"
        
        if not wav_src.exists() or not emb_src.exists():
            print(f"Pending files not found for {pending_id}")
            return
        
        person_dir = Path(ENROLL_DIR) / person_id
        embeddings_dir = person_dir / "embeddings"
        recordings_dir = person_dir / "recordings"
        
        person_dir.mkdir(parents=True, exist_ok=True)
        embeddings_dir.mkdir(exist_ok=True)
        recordings_dir.mkdir(exist_ok=True)
        
        metadata_file = person_dir / "metadata.json"
        if metadata_file.exists():
            with open(metadata_file, "r") as f:
                metadata = json.load(f)
                existing_samples = metadata.get("samples", [])
        else:
            metadata = {
                "person_id": person_id,
                "display_name": display_name,
                "created_at": datetime.datetime.utcnow()
                .replace(microsecond=0)
                .isoformat()
                + "Z",
            }
            existing_samples = []
        
        event_id = pending_id
        emb_dst = embeddings_dir / f"{event_id}.txt"
        rec_dst = recordings_dir / f"{event_id}.wav"
        
        expire_at = (
            datetime.datetime.utcfromtimestamp(time.time() + 3 * 24 * 3600)
            .replace(microsecond=0)
            .isoformat()
            + "Z"
        )
        
        try:
            shutil.move(str(emb_src), str(emb_dst))
            shutil.move(str(wav_src), str(rec_dst))
            print(f"Moved files to enrollment: {event_id}")
        except Exception as e:
            print(f"Failed to move files: {e}")
            return
        
        sample_entry = {
            "event_id": event_id,
            "embedding": f"embeddings/{event_id}.txt",
            "recording": f"recordings/{event_id}.wav",
            "enrolled_at": datetime.datetime.utcnow()
            .replace(microsecond=0)
            .isoformat()
            + "Z",
            "expire_at": expire_at,
            "retention_days": 3,
            "source": "active_node",
        }
        
        metadata["samples"] = existing_samples + [sample_entry]
        metadata["last_updated"] = (
            datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
        )
        metadata["total_samples"] = len(metadata["samples"])
        
        with open(metadata_file, "w") as f:
            json.dump(metadata, f, indent=2)
        
        buffer = [e for e in buffer if e["id"] != pending_id]
        save_pending_buffer(buffer)
        
        # Refresh gallery so new enrollment is immediately used
        userdata["gallery"] = load_gallery()
        
        publish_pending_status(client)
        
        response = {
            "success": True,
            "pending_id": pending_id,
            "person_id": person_id,
            "display_name": display_name,
            "total_samples": metadata["total_samples"],
        }
        client.publish(f"voicebm/pending_active/enroll/response", json.dumps(response), qos=1)
        
        print(f"Successfully enrolled {pending_id} as {display_name}")
        
    except Exception as e:
        print(f"Error handling enroll command: {e}")
        import traceback

        traceback.print_exc()


def handle_pending_reject(client, userdata, msg):
    """Handle rejection command for pending active voice."""
    try:
        data = json.loads(msg.payload.decode("utf-8"))
        pending_id = data.get("id")
        
        if not pending_id:
            print("Reject command missing id")
            return
        
        print(f"Rejecting pending: {pending_id}")
        
        try:
            wav_path = PENDING_RECORDINGS / f"{pending_id}.wav"
            emb_path = PENDING_EMBEDDINGS / f"{pending_id}.txt"
            if wav_path.exists():
                wav_path.unlink()
            if emb_path.exists():
                emb_path.unlink()
        except Exception as e:
            print(f"Failed to delete files for {pending_id}: {e}")
        
        buffer = load_pending_buffer()
        buffer = [e for e in buffer if e["id"] != pending_id]
        save_pending_buffer(buffer)
        
        publish_pending_status(client)
        
        response = {"success": True, "rejected_id": pending_id}
        client.publish(f"voicebm/pending_active/reject/response", json.dumps(response), qos=1)
        
        print(f"Successfully rejected {pending_id}")
        
    except Exception as e:
        print(f"Error handling reject command: {e}")


def handle_pending_clear(client, userdata, msg):
    """Clear all pending entries."""
    try:
        print("Clearing all pending entries")
        
        buffer = load_pending_buffer()
        
        for entry in buffer:
            try:
                wav_path = PENDING_RECORDINGS / f"{entry['id']}.wav"
                emb_path = PENDING_EMBEDDINGS / f"{entry['id']}.txt"
                if wav_path.exists():
                    wav_path.unlink()
                if emb_path.exists():
                    emb_path.unlink()
            except Exception as e:
                print(f"Failed to delete {entry['id']}: {e}")
        
        save_pending_buffer([])
        publish_pending_status(client)
        
        print(f"Cleared {len(buffer)} pending entries")
        
    except Exception as e:
        print(f"Error handling clear command: {e}")


def handle_person_name_set(client, userdata, msg):
    """Handle person name text input for pending enrollment."""
    global pending_person_name
    
    try:
        pending_person_name = msg.payload.decode("utf-8").strip()
        
        client.publish(
            "voicebm/pending_active/person_name",
            pending_person_name,
            qos=1,
            retain=True,
        )
        
        print(f"Pending person name set to: '{pending_person_name}'")
        
    except Exception as e:
        print(f"Error handling person name set: {e}")


def handle_enroll_button(client, userdata, msg):
    """
    Handle enroll button press.

    CHANGE: uses the NEWEST pending entry (buffer[-1]) to match
    what we surface as 'current' in publish_pending_status().
    """
    global pending_person_name
    
    try:
        buffer = load_pending_buffer()
        
        if not buffer:
            print("Enroll button pressed but no pending entries")
            return
        
        if not pending_person_name:
            print("Enroll button pressed but no person name set")
            return
        
        # Use newest pending entry
        current = buffer[-1]
        pending_id = current["id"]
        
        person_id = pending_person_name.lower().replace(" ", "_")
        display_name = pending_person_name.title()
        
        print(f"Enrolling pending {pending_id} as {display_name} ({person_id})")
        
        enroll_data = {
            "id": pending_id,
            "person_id": person_id,
            "display_name": display_name,
        }
        
        class MockMsg:
            def __init__(self, payload):
                self.payload = payload
        
        mock_msg = MockMsg(json.dumps(enroll_data).encode("utf-8"))
        handle_pending_enroll(client, userdata, mock_msg)
        
        pending_person_name = ""
        client.publish(
            "voicebm/pending_active/person_name", "", qos=1, retain=True
        )
        
    except Exception as e:
        print(f"Error handling enroll button: {e}")
        import traceback

        traceback.print_exc()


def handle_reject_button(client, userdata, msg):
    """
    Handle reject button press.

    CHANGE: rejects the NEWEST pending entry (buffer[-1]),
    to stay consistent with what HA is showing as 'current'.
    """
    try:
        buffer = load_pending_buffer()
        
        if not buffer:
            print("Reject button pressed but no pending entries")
            return
        
        current = buffer[-1]
        pending_id = current["id"]
        
        print(f"Rejecting pending {pending_id}")
        
        reject_data = {"id": pending_id}
        
        class MockMsg:
            def __init__(self, payload):
                self.payload = payload
        
        mock_msg = MockMsg(json.dumps(reject_data).encode("utf-8"))
        handle_pending_reject(client, userdata, mock_msg)
        
    except Exception as e:
        print(f"Error handling reject button: {e}")


def handle_play_button(client, userdata, msg):
    """
    Handle play button press.

    CHANGE: plays the NEWEST pending entry (buffer[-1]),
    again matching the surfaced 'current'.
    """
    try:
        buffer = load_pending_buffer()
        
        if not buffer:
            print("Play button pressed but no pending entries")
            return
        
        current = buffer[-1]
        audio_url = current.get("audio_url", "")
        
        if audio_url:
            client.publish(
                "voicebm/pending_active/play_trigger", audio_url, qos=1
            )
            print(f"Play triggered: {audio_url}")
        else:
            print("No audio URL for pending entry")
        
    except Exception as e:
        print(f"Error handling play button: {e}")


def handle_analysis_request(client, userdata, msg):
    """Process voice biometrics analysis request."""
    global inject_identity_enabled, last_published_person, biopsy_seen_ids
    
    try:
        request = json.loads(msg.payload.decode("utf-8"))
        request_id = request.get("request_id")
        audio_path = request.get("audio_path")
        
        print(f"\nAnalysis request: {request_id}")
        print(f"  Audio: {audio_path}")
        
        if not audio_path or not os.path.exists(audio_path):
            print("  Audio file not found")
            return

        # Determine whether this is a biopsy (early identity) or full audio (current speaker)
        # Biopsy filename always contains '_biopsy' (set by handler.py)
        # Full audio that arrives with no prior biopsy (short utterance) falls back to
        # publishing active identity so the primitives don't go stale
        is_biopsy = "_biopsy" in os.path.basename(audio_path)
        is_full_audio = not is_biopsy
        
        if is_biopsy:
            biopsy_seen_ids.add(request_id)
            if len(biopsy_seen_ids) > 50:
                biopsy_seen_ids.clear()
        
        # Publish active identity on biopsy, OR on full audio when no biopsy ran (short utterance)
        should_publish_active = is_biopsy or (is_full_audio and request_id not in biopsy_seen_ids)
        
        # Clear current_speaker at utterance start - new enrollment sample incoming
        # Active identity sensors are NOT cleared here; biopsy populates them
        client.publish("voicebm/current_speaker", "none", qos=1, retain=True)
        
        # Clear previous person's binary sensor BEFORE identifying new speaker
        # This ensures OFF->ON state change even if same person speaks twice
        # Prevents stuck sensors in Home Assistant automations
        if should_publish_active:
            if last_published_person:
                print(f"  Clearing previous sensor: {last_published_person}/voice")
                client.publish(f"{last_published_person}/voice", "OFF", qos=1, retain=True)
                time.sleep(0.05)  # 50ms for HA to register OFF state
        
        # Load ACTIVE threshold (slider-controlled)
        try:
            with open(THRESHOLD_FILE, "r") as f:
                thr = json.load(f)
                threshold = float(thr.get("MATCH_T_ACTIVE", DEFAULT_THRESHOLD_ACTIVE))
                print(
                    f"  Using STT threshold: {threshold:.2f} "
                    f"(from thresholds.json MATCH_T_ACTIVE)"
                )
        except Exception as e:
            threshold = DEFAULT_THRESHOLD_ACTIVE
            print(
                f"  Using STT threshold: {threshold:.2f} "
                f"(default, file read failed: {e})"
            )
        
        embedding = create_embedding(audio_path)
        
        if embedding is None:
            print("  Failed to create embedding")
            return
        
        gallery = userdata["gallery"]
        speaker_id, display_name, confidence = identify_speaker(
            embedding, gallery, threshold
        )
        
        # Verify speaker meets their custom threshold (if set)
        # If custom threshold is higher and not met, treat as unknown
        speaker_id = verify_person_threshold(speaker_id, confidence, threshold)
        
        # If speaker_id was cleared by custom threshold check, reset display_name
        if speaker_id is None and display_name is not None:
            print(f"  Match rejected: {display_name} did not meet custom threshold")
            display_name = None
        
        # ALWAYS add to pending buffer (unknowns AND known persons)
        # This enables continuous training and gallery strengthening
        # Unknowns -> can enroll as new person
        # Known persons -> can add training samples to existing gallery
        print(f"  Adding to pending buffer: {display_name or 'user'} (available for enrollment/training)")
        entry = add_to_pending_buffer(audio_path, embedding, request_id)
        if entry:
            publish_pending_status(client)

        # Carry the pending wav path for emote — used after all identity work is done
        pending_wav_for_emote = None
        if entry and is_full_audio:
            pending_wav_for_emote = str(PENDING_RECORDINGS / f"{entry['id']}.wav")

        # =================================================================
        # CRITICAL FIX: Map unknowns to virtual "user" identity for blocklist check
        # =================================================================
        # For unknowns: speaker_id = None
        # Map to "user" so the blocklist check can actually block them
        effective_id = speaker_id if speaker_id else "user"
        is_blocked = is_speaker_blocked(effective_id)
        
        response = {
            "request_id": request_id,
            "speaker_id": speaker_id,
            "display_name": display_name,
            "confidence": confidence,
            "inject_enabled": inject_identity_enabled,
            "is_blocked": is_blocked,
            "timestamp": time.time(),
        }
        
        if is_blocked:
            print(
                f"  [BLOCKED] Speaker {display_name or 'user'} ({speaker_id or 'user'}) "
                f"is on blocklist - STT will silent fail"
            )
        
        response_topic = f"voicebm/stt/analyze_response/{request_id}"
        client.publish(response_topic, json.dumps(response), qos=1)
        print(f"  Published response to {response_topic}")
        
        if should_publish_active:
            # Publish Active Identity data for HA sensors (8 entities)
            decision = "accepted" if speaker_id else "unknown"
            active_identity_data = {
                "speaker_id": speaker_id,
                "display_name": display_name or "user",
                "confidence": confidence,
                "decision": decision,
                "score": confidence  # Score = confidence for active pipeline
            }
            client.publish("voicebm/active/identity", json.dumps(active_identity_data), qos=1, retain=True)
            client.publish("voicebm/active/current_event_id", request_id, qos=1, retain=True)
            
            # Publish binary sensor state for detected person
            # This creates OFF->ON transition even for consecutive utterances from same person
            if speaker_id:
                client.publish(f"{speaker_id}/voice", "ON", qos=1, retain=True)
                last_published_person = speaker_id  # Store for next clearing cycle
                print(f"  Published binary sensor: {speaker_id}/voice = ON")
            
            # Write active state to filesystem for dashboard (Flask/OpenWebUI multi-platform sync)
            write_active_state_file(speaker_id, display_name, confidence, decision)
            
            # Publish confidence + source + gallery_size as attributes for per-person binary sensor
            # IMPORTANT: Include gallery_size to keep it synced with enrollment_watcher
            if speaker_id:  # Only for identified users, not unknowns
                # Count embeddings in enrollment gallery
                from pathlib import Path
                enroll_dir = Path("/home/user/voicebm/enroll") / speaker_id / "embeddings"
                gallery_size = len(list(enroll_dir.glob('*.txt'))) if enroll_dir.exists() else 0
                
                # Merge all attributes together
                attributes = {
                    "confidence": round(confidence, 4),
                    "source": "active",
                    "gallery_size": gallery_size,
                    "last_updated": time.strftime('%Y-%m-%d %H:%M:%S')
                }
                client.publish(f"{speaker_id}/voice/attributes", json.dumps(attributes), qos=1, retain=True)
            
            # Publish plain-string active speaker primitives (each concern its own topic)
            client.publish("voicebm/active_speaker", display_name or "user", qos=1, retain=True)
            client.publish("voicebm/active_speaker_id", speaker_id or "user", qos=1, retain=True)
            print(f"  Published Active Speaker: {display_name or 'user'} / {speaker_id or 'user'}")

            print(f"  Published Active Identity: {display_name} ({decision}, {confidence:.2%})")
        
        if is_full_audio:
            # Full audio path: publish current_speaker and current_speaker_id (enrollment-grade sample)
            client.publish("voicebm/current_speaker", display_name or "user", qos=1, retain=True)
            client.publish("voicebm/current_speaker_id", speaker_id or "user", qos=1, retain=True)
            print(f"  Published Current Speaker: {display_name or 'user'} / {speaker_id or 'user'}")

        # Emote Edition — runs last, after all identity work is published.
        # Full audio only. Blocks here but identity is already done.
        # If voicebm_emote.py is not installed this is a no-op (see soft import above).
        if pending_wav_for_emote:
            run_emote(pending_wav_for_emote, client)
        
    except Exception as e:
        print(f"  Error processing request: {e}")
        import traceback

        traceback.print_exc()


def handle_active_threshold_set(client, userdata, msg):
    """Handle active threshold slider changes and update thresholds.json."""
    try:
        new_threshold = float(msg.payload.decode("utf-8"))
        
        # Validate range
        if not (0.01 <= new_threshold <= 1.00):
            print(f"Invalid active threshold value: {new_threshold}")
            return
        
        print(f"Active threshold changed to: {new_threshold:.2f}")
        
        # Update thresholds.json MATCH_T_ACTIVE
        try:
            if os.path.exists(THRESHOLD_FILE):
                with open(THRESHOLD_FILE, 'r') as f:
                    thresholds = json.load(f)
            else:
                thresholds = {}
            
            thresholds['MATCH_T_ACTIVE'] = new_threshold
            
            os.makedirs(os.path.dirname(THRESHOLD_FILE), exist_ok=True)
            with open(THRESHOLD_FILE, 'w') as f:
                json.dump(thresholds, f, indent=2)
            
            print(f"  Updated thresholds.json: MATCH_T_ACTIVE = {new_threshold:.2f}")
            
            # Echo back to state topic
            client.publish("voicebm/active/threshold", str(new_threshold), qos=1, retain=True)
            
            # Write settings to filesystem for dashboard
            write_settings_file()
            
        except Exception as e:
            print(f"Failed to update thresholds.json: {e}")
    
    except Exception as e:
        print(f"Error handling active threshold change: {e}")


def handle_person_threshold_set(client, userdata, msg):
    """Handle per-person threshold override changes."""
    global person_thresholds
    
    try:
        # Extract person_id from topic: {person_id}/threshold_override/set
        topic_parts = msg.topic.split('/')
        if len(topic_parts) < 3:
            print(f"Invalid threshold override topic: {msg.topic}")
            return
        
        person_id = topic_parts[0]
        new_threshold = float(msg.payload.decode("utf-8"))
        
        # Validate range
        if not (0.10 <= new_threshold <= 0.90):
            print(f"Invalid threshold value for {person_id}: {new_threshold}")
            return
        
        # Update cache
        person_thresholds[person_id] = new_threshold
        print(f"Custom threshold for {person_id}: {new_threshold:.2f}")
        
        # Echo back to state topic
        client.publish(f"{person_id}/threshold_override", str(new_threshold), qos=1, retain=True)
        
    except ValueError:
        print(f"Invalid threshold value received: {msg.payload}")
    except Exception as e:
        print(f"Error handling person threshold change: {e}")


def handle_lead_trim_set(client, userdata, msg):
    """Handle Active Lead Trim slider changes; persist to config.json (F-02)."""
    try:
        new_trim = int(float(msg.payload.decode("utf-8")))
        if not (0 <= new_trim <= 2000):
            print(f"Invalid lead trim value: {new_trim}")
            return
        print(f"Active lead trim changed to: {new_trim} ms")
        if update_voicebm_config_key("active_lead_trim_ms", new_trim):
            print(f"  Updated config.json: voicebm.active_lead_trim_ms = {new_trim}")
            client.publish("voicebm/active/lead_trim", str(new_trim), qos=1, retain=True)
    except ValueError:
        print(f"Invalid lead trim value received: {msg.payload}")
    except Exception as e:
        print(f"Error handling lead trim change: {e}")


def handle_gallery_max_set(client, userdata, msg):
    """Handle Gallery Max changes and update thresholds.json GALLERY_MAX."""
    try:
        new_max = int(float(msg.payload.decode("utf-8")))

        # Validate range
        if not (0 <= new_max <= 200):
            print(f"Invalid gallery max value: {new_max}")
            return

        print(f"Gallery max changed to: {new_max}")

        # Update thresholds.json GALLERY_MAX
        try:
            if os.path.exists(THRESHOLD_FILE):
                with open(THRESHOLD_FILE, "r") as f:
                    thresholds = json.load(f)
            else:
                thresholds = {}

            thresholds["GALLERY_MAX"] = new_max

            os.makedirs(os.path.dirname(THRESHOLD_FILE), exist_ok=True)
            with open(THRESHOLD_FILE, "w") as f:
                json.dump(thresholds, f, indent=2)

            print(f"  Updated thresholds.json: GALLERY_MAX = {new_max}")

            # Echo back to state topic
            client.publish("voicebm/gallery_max", str(new_max), qos=1, retain=True)

        except Exception as e:
            print(f"Failed to update thresholds.json: {e}")

    except Exception as e:
        print(f"Error handling gallery max change: {e}")


def on_connect(client, userdata, flags, reason_code, properties):
    global inject_identity_enabled
    
    if reason_code == 0:
        print(f"Connected to MQTT broker at 127.0.0.1:1883")
        
        # OWNERSHIP: analysis belongs to voicebm_stt_service — the ONE lab.
        # This service must NOT consume analyze_request. When it did, every
        # utterance was embedded twice by two code vintages, two pending
        # files were banked (one untrimmed), and two responders raced on
        # analyze_response. Management duties only here.
        # client.subscribe(REQUEST_TOPIC, qos=1)  # REMOVED — STT service owns analysis
        
        client.subscribe(INJECT_STATE_TOPIC, qos=1)
        print(f"Subscribed to voicebm/inject_identity")
        
        client.subscribe("voicebm/blocklist/+", qos=1)
        print("Subscribed to voicebm/blocklist/+ (blocklist states)")
        
        client.subscribe(PENDING_ENROLL_TOPIC, qos=1)
        client.subscribe(PENDING_REJECT_TOPIC, qos=1)
        client.subscribe(PENDING_CLEAR_TOPIC, qos=1)
        print("Subscribed to pending command topics")
        
        client.subscribe("voicebm/pending_active/person_name/set", qos=1)
        client.subscribe("voicebm/pending_active/enroll_btn", qos=1)
        client.subscribe("voicebm/pending_active/reject_btn", qos=1)
        client.subscribe("voicebm/pending_active/play_btn", qos=1)
        print("Subscribed to pending UI control topics")
        
        client.subscribe("voicebm/active/threshold/set", qos=1)
        client.subscribe("voicebm/active/lead_trim/set", qos=1)
        client.subscribe("voicebm/gallery_max/set", qos=1)
        print("Subscribed to active threshold control")
        
        # Subscribe to per-person threshold overrides
        client.subscribe("+/threshold_override/set", qos=1)
        print("Subscribed to per-person threshold overrides (+/threshold_override/set)")
        
        publish_discovery(client)
        publish_pending_status(client)
        publish_emote_discovery(client)
        
    else:
        print(f"Failed to connect, reason code: {reason_code}")


def on_message(client, userdata, msg):
    global inject_identity_enabled, pending_person_name
    
    topic = msg.topic
    
    if topic.startswith("voicebm/blocklist/") and not topic.endswith("/set"):
        handle_blocklist_state(client, userdata, msg)
    elif topic == REQUEST_TOPIC:
        handle_analysis_request(client, userdata, msg)
    elif topic == INJECT_STATE_TOPIC:
        try:
            state = msg.payload.decode("utf-8")
            new_enabled = state == "ON"
            if inject_identity_enabled != new_enabled:
                inject_identity_enabled = new_enabled
                print(f"Injection state updated: {state} (enabled={new_enabled})")
                # Write settings to filesystem for dashboard
                write_settings_file()
        except Exception as e:
            print(f"Failed to parse injection state: {e}")
    elif topic == PENDING_ENROLL_TOPIC:
        handle_pending_enroll(client, userdata, msg)
    elif topic == PENDING_REJECT_TOPIC:
        handle_pending_reject(client, userdata, msg)
    elif topic == PENDING_CLEAR_TOPIC:
        handle_pending_clear(client, userdata, msg)
    elif topic == "voicebm/pending_active/person_name/set":
        handle_person_name_set(client, userdata, msg)
    elif topic == "voicebm/pending_active/enroll_btn":
        handle_enroll_button(client, userdata, msg)
    elif topic == "voicebm/pending_active/reject_btn":
        handle_reject_button(client, userdata, msg)
    elif topic == "voicebm/pending_active/play_btn":
        handle_play_button(client, userdata, msg)
    elif topic == "voicebm/active/threshold/set":
        handle_active_threshold_set(client, userdata, msg)
    elif topic == "voicebm/active/lead_trim/set":
        handle_lead_trim_set(client, userdata, msg)
    elif topic == "voicebm/gallery_max/set":
        handle_gallery_max_set(client, userdata, msg)
    elif topic.endswith("/threshold_override/set"):
        handle_person_threshold_set(client, userdata, msg)


def main():
    global inject_identity_enabled
    
    print("=" * 60)
    print("Voice Biometrics MQTT Service (ACTIVE PIPELINE)")
    print("=" * 60)
    print(f"MQTT Broker: 127.0.0.1:1883")
    print(f"Request Topic: voicebm/stt/analyze_request")
    print(f"Response Topic: voicebm/stt/analyze_response")
    print(f"Pending Buffer Size: 5")
    print("=" * 60)
    
    setup_pending_dirs()
    
    # Write initial settings for dashboard
    print("\nInitializing dashboard state files...")
    write_settings_file()
    
    print("\nLoading enrollment gallery...")
    gallery = load_gallery()
    
    if not gallery:
        print("Warning: No enrolled speakers found!")
    
    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(USER, PASS)
    client.user_data_set({"gallery": gallery})
    client.on_connect = on_connect
    client.on_message = on_message
    
    try:
        client.connect(BROKER, PORT, 60)
    except Exception as e:
        print(f"MQTT connection failed: {e}")
        return
    
    print("\nVoice biometrics service ready")
    print("Press Ctrl+C to exit\n")
    
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print("\n\nShutting down...")
        client.disconnect()
        print("Service stopped")


if __name__ == "__main__":
    main()
```


## 8. `enrollment_watcher.py` <a id="8-enrollment-watcherpy"></a>

_Enrollment Watcher - Monitors /home/user/voicebm/enroll/ for new person folders_

```python
# FILE: enrollment_watcher.py.template
# TYPE: script
################################################################################

#!/usr/bin/env python3
"""
Enrollment Watcher - Monitors /home/user/voicebm/enroll/ for new person folders
and publishes MQTT device configs.

When a person is enrolled:
1. Create device with presence and voice binary sensors
2. Publish device config to {person_id}/device
3. Initialize state topics
"""

import os
import json
import time
import shutil
import paho.mqtt.client as mqtt
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# MQTT Configuration
# MQTT Configuration (centralized)
import sys
sys.path.insert(0, '/home/user/voicebm')
from voicebm_config import get_mqtt_config

mqtt_config = get_mqtt_config()
BROKER = mqtt_config['broker']
PORT = mqtt_config['port']
USER = mqtt_config['user']
PASS = mqtt_config['password']

# Directories
ENROLL_DIR = Path("/home/user/voicebm/enroll")
TRACKED_FILE = Path("/home/user/voicebm/meta/enrolled_devices.json")
USER_SETTINGS_FILE = Path("/home/user/voicebm/meta/user_settings.json")
DELETE_ENABLED_FILE = Path("/home/user/voicebm/meta/delete_enabled.json")

# Current room this instance monitors
CURRENT_ROOM = "living"

# Track last published gallery sizes to avoid overwriting STT attributes
last_published_gallery_sizes = {}


# ============================================================================
# PERSON ID NORMALIZATION AND VALIDATION
# ============================================================================

def normalize_person_id(name):
    """
    Normalize person name to person_id format.
    Converts to lowercase and replaces spaces/hyphens with underscores.
    
    Transform rules:
    1. Convert to lowercase
    2. Replace hyphens with underscores
    3. Replace multiple spaces with single underscore
    4. Collapse multiple underscores to one
    5. Strip leading/trailing underscores
    
    Examples:
        "David Dryver Sr"  "david_dryver_sr"
        "MARY-JANE Watson"  "mary_jane_watson"
        "Jean   Luc   Picard"  "jean_luc_picard"
        "ada_von-holtz"  "ada_von_holtz"
    
    Returns:
        Normalized person_id (lowercase with underscores)
    """
    import re
    
    # Convert to lowercase
    normalized = name.lower()
    
    # Replace hyphens with underscores
    normalized = normalized.replace('-', '_')
    
    # Replace multiple spaces with single underscore
    normalized = re.sub(r'\s+', '_', normalized)
    
    # Collapse multiple underscores to one
    normalized = re.sub(r'_+', '_', normalized)
    
    # Strip leading/trailing underscores
    normalized = normalized.strip('_')
    
    return normalized


def derive_display_name(person_id, metadata=None):
    """
    Resolve a person's display name (B-03).

    The virtual 'user' identity ALWAYS displays as lowercase "user" - it is the
    error-trap identity for any unenrolled speaker, never "Unknown" and never
    "User". For real enrolled people, prefer metadata's display_name, otherwise
    derive a human label from the slug (e.g. 'david_dryver' -> 'David Dryver').

    Args:
        person_id: the identity slug
        metadata: optional already-loaded metadata dict

    Returns:
        str: display name
    """
    if person_id == "user":
        return "user"
    if metadata:
        dn = metadata.get('display_name')
        if dn:
            return dn
    return person_id.replace('_', ' ').title()


def validate_person_name(name):
    """
    Validate user input for person name.
    
    Rules:
    1. Must begin with a letter
    2. Must end with a letter
    3. Cannot contain digits
    4. Can only contain: letters, spaces, hyphens, underscores
    5. Must have at least one letter
    
    Examples of VALID input:
        "David", "David Dryver Sr", "Mary-Jane Watson"
        "Jean Luc Picard", "ada_von-holtz"
    
    Examples of INVALID input:
        "David_" (ends with non-letter)
        "_David" (starts with non-letter)
        "David2" (contains digits)
        "Ron@Kitchen" (special characters)
    
    Returns:
        (valid: bool, error_message: str or None)
    """
    import re
    
    if not name or len(name.strip()) == 0:
        return False, "Name cannot be empty"
    
    name = name.strip()
    
    # Must begin with a letter
    if not name[0].isalpha():
        return False, "Name must begin with a letter"
    
    # Must end with a letter
    if not name[-1].isalpha():
        return False, "Name must end with a letter"
    
    # Can only contain letters, spaces, hyphens, underscores
    if not re.match(r'^[a-zA-Z\s_-]+$', name):
        return False, "Name can only contain letters, spaces, hyphens, and underscores"
    
    # No digits allowed (already covered by regex, but explicit check)
    if any(char.isdigit() for char in name):
        return False, "Name cannot contain digits"
    
    return True, None


def check_for_duplicate_folders():
    """
    Check for duplicate person folders (e.g., 'David Dryver Sr' vs 'david_dryver_sr').
    
    Returns:
        dict of normalized_id  [actual_folder_names] for folders that normalize to the same ID
    """
    if not ENROLL_DIR.exists():
        return {}
    
    duplicates = {}
    for person_dir in ENROLL_DIR.iterdir():
        if not person_dir.is_dir():
            continue
        
        actual_name = person_dir.name
        normalized = normalize_person_id(actual_name)
        
        if normalized not in duplicates:
            duplicates[normalized] = []
        duplicates[normalized].append(actual_name)
    
    # Return only entries with actual duplicates
    return {k: v for k, v in duplicates.items() if len(v) > 1}


# ============================================================================
# EXISTING HELPER FUNCTIONS
# ============================================================================

def load_tracked_devices():
    """Load set of person_ids we've already published"""
    if not TRACKED_FILE.exists():
        return set()
    try:
        with open(TRACKED_FILE, 'r') as f:
            data = json.load(f)
            return set(data.get('person_ids', []))
    except:
        return set()


def save_tracked_devices(person_ids):
    """Save set of enrolled person_ids"""
    try:
        TRACKED_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(TRACKED_FILE, 'w') as f:
            json.dump({
                'person_ids': list(person_ids),
                'last_updated': time.strftime('%Y-%m-%d %H:%M:%S')
            }, f, indent=2)
    except PermissionError as e:
        print(f"Warning: Cannot save tracked devices (permission denied): {e}")
        print(f"  Try: sudo chown -R user:user /home/user/voicebm/meta/")
    except Exception as e:
        print(f"Warning: Cannot save tracked devices: {e}")


def load_user_settings():
    """Load user settings (blocklist state for 'user' device)"""
    if not USER_SETTINGS_FILE.exists():
        return {"blocked": False}
    try:
        with open(USER_SETTINGS_FILE, 'r') as f:
            return json.load(f)
    except:
        return {"blocked": False}


def save_user_settings(settings):
    """Save user settings"""
    try:
        USER_SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(USER_SETTINGS_FILE, 'w') as f:
            json.dump(settings, f, indent=2)
    except Exception as e:
        print(f"Warning: Cannot save user settings: {e}")


def load_delete_enabled():
    """Load which person_ids have delete enabled"""
    if not DELETE_ENABLED_FILE.exists():
        return {}
    try:
        with open(DELETE_ENABLED_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}


def save_delete_enabled(enabled_dict):
    """Save delete enabled states"""
    try:
        DELETE_ENABLED_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(DELETE_ENABLED_FILE, 'w') as f:
            json.dump(enabled_dict, f, indent=2)
    except Exception as e:
        print(f"Warning: Cannot save delete enabled: {e}")



def get_gallery_size(person_id):
    """
    Count number of .txt embedding files for a person (Sherpa format).
    Embeddings are stored in /enroll/{person_id}/embeddings/*.txt
    
    Returns:
        Integer count of gallery samples
    """
    person_dir = Path(ENROLL_DIR) / person_id
    if not person_dir.exists():
        return 0
    
    # Embeddings are in a subdirectory (Sherpa format)
    embeddings_dir = person_dir / 'embeddings'
    if not embeddings_dir.exists():
        return 0
    
    # Count .txt files (Sherpa embeddings)
    txt_files = list(embeddings_dir.glob('*.txt'))
    return len(txt_files)


def publish_gallery_attributes(client, person_id):
    """
    Publish gallery size as attributes for the voice binary sensor.
    Only publishes when gallery_size changes to avoid overwriting
    confidence/source attributes published by STT service.
    """
    global last_published_gallery_sizes
    
    gallery_size = get_gallery_size(person_id)
    
    # Only publish if gallery size changed
    if person_id not in last_published_gallery_sizes or last_published_gallery_sizes[person_id] != gallery_size:
        attributes = {
            "gallery_size": gallery_size,
            "last_updated": time.strftime('%Y-%m-%d %H:%M:%S')
        }
        
        client.publish(
            f"{person_id}/voice/attributes",
            json.dumps(attributes),
            qos=1,
            retain=True
        )
        
        last_published_gallery_sizes[person_id] = gallery_size


def publish_person_device(client, person_id, display_name, is_new_device=False):
    """
    Publish person device using Home Assistant MQTT Discovery.
    
    CRITICAL: Discovery config is always published (with retain).
              State is ONLY published for NEW devices.
              Existing devices keep their HA-retained state.
    
    Args:
        client: MQTT client
        person_id: Person identifier
        display_name: Human readable name
        is_new_device: If True, publish initial state. If False, only publish discovery.
    """
    discovery_prefix = "homeassistant"
    
    # Device info
    device = {
        "identifiers": [person_id],
        "name": display_name,
        "manufacturer": "",
        "model": "Person"
    }
    
    # Voice binary sensor config
    voice_config = {
        "name": "Voice",
        "unique_id": f"{person_id}_voice",
        "device_class": "sound",
        "state_topic": f"{person_id}/voice",
        "payload_on": "ON",
        "payload_off": "OFF",
        "json_attributes_topic": f"{person_id}/voice/attributes",
        "device": device
    }
    
    # Publish voice sensor discovery
    client.publish(
        f"{discovery_prefix}/binary_sensor/{person_id}_voice/config",
        json.dumps(voice_config),
        qos=1,
        retain=True
    )
    
    # Blocklist switch config - NOW INCLUDES "user"
    blocklist_config = {
        "name": "Blocklist",
        "unique_id": f"{person_id}_blocklist",
        "command_topic": f"voicebm/blocklist/{person_id}/set",
        "state_topic": f"voicebm/blocklist/{person_id}",
        "payload_on": "ON",
        "payload_off": "OFF",
        "icon": "mdi:account-cancel",
        "device": device
    }
    
    client.publish(
        f"{discovery_prefix}/switch/{person_id}_blocklist/config",
        json.dumps(blocklist_config),
        qos=1,
        retain=True
    )
    
    # Per-Person Threshold Override number entity
    threshold_config = {
        "name": "Threshold Override",
        "unique_id": f"{person_id}_threshold",
        "command_topic": f"{person_id}/threshold_override/set",
        "state_topic": f"{person_id}/threshold_override",
        "min": 0.10,
        "max": 0.90,
        "step": 0.01,
        "mode": "slider",
        "icon": "mdi:gauge",
        "device": device,
        "unit_of_measurement": "",
        "entity_category": "config"
    }
    
    client.publish(
        f"{discovery_prefix}/number/{person_id}_threshold/config",
        json.dumps(threshold_config),
        qos=1,
        retain=True
    )
    
    # Delete controls (only for enrolled persons, not "user")
    if person_id != "user":
        # Enable Delete Controls switch
        enable_delete_config = {
            "name": "Enable Delete Controls",
            "unique_id": f"{person_id}_enable_delete",
            "command_topic": f"voicebm/identity/{person_id}/enable_delete/set",
            "state_topic": f"voicebm/identity/{person_id}/enable_delete",
            "payload_on": "ON",
            "payload_off": "OFF",
            "icon": "mdi:lock-open-alert",
            "entity_category": "config",
            "device": device
        }
        
        client.publish(
            f"{discovery_prefix}/switch/{person_id}_enable_delete/config",
            json.dumps(enable_delete_config),
            qos=1,
            retain=True
        )
        
        # Delete This Identity button
        delete_button_config = {
            "name": "Delete This Identity",
            "unique_id": f"{person_id}_delete",
            "command_topic": f"voicebm/identity/{person_id}/delete",
            "payload_press": "PRESS",
            "icon": "mdi:delete-forever-outline",
            "entity_category": "config",
            "device": device
        }
        
        client.publish(
            f"{discovery_prefix}/button/{person_id}_delete/config",
            json.dumps(delete_button_config),
            qos=1,
            retain=True
        )
        
        # Thing Engine: Transform text input
        transform_name_config = {
            "name": "New Identity Name",
            "unique_id": f"{person_id}_transform_name",
            "command_topic": f"voicebm/thing/transform/{person_id}/name/set",
            "state_topic": f"voicebm/thing/transform/{person_id}/name",
            "icon": "mdi:account-edit",
            "device": device,
            "entity_category": "config"
        }
        
        client.publish(
            f"{discovery_prefix}/text/{person_id}_transform_name/config",
            json.dumps(transform_name_config),
            qos=1,
            retain=True
        )
        
        # Thing Engine: Transform button
        transform_execute_config = {
            "name": "Rename Identity",
            "unique_id": f"{person_id}_transform_execute",
            "command_topic": f"voicebm/thing/transform/{person_id}/execute",
            "payload_press": "PRESS",
            "icon": "mdi:account-convert",
            "device": device,
            "entity_category": "config"
        }
        
        client.publish(
            f"{discovery_prefix}/button/{person_id}_transform_execute/config",
            json.dumps(transform_execute_config),
            qos=1,
            retain=True
        )
        
        # Thing Engine: Merge tag switch
        merge_tag_config = {
            "name": "Tag for Merge",
            "unique_id": f"{person_id}_merge_tag",
            "command_topic": f"voicebm/thing/merge/tag/{person_id}/set",
            "state_topic": f"voicebm/thing/merge/tag/{person_id}",
            "payload_on": "ON",
            "payload_off": "OFF",
            "icon": "mdi:account-multiple",
            "device": device,
            "entity_category": "config"
        }
        
        client.publish(
            f"{discovery_prefix}/switch/{person_id}_merge_tag/config",
            json.dumps(merge_tag_config),
            qos=1,
            retain=True
        )
    
    # ONLY publish initial state for NEW devices
    # Existing devices keep their HA-retained state
    if is_new_device:
        if person_id == "user":
            # For "user", use separate settings file
            user_settings = load_user_settings()
            blocked = user_settings.get("blocked", False)
        else:
            # For enrolled persons, use metadata.json
            metadata_path = Path(ENROLL_DIR) / person_id / "metadata.json"
            blocked = False
            if metadata_path.exists():
                try:
                    with open(metadata_path, 'r') as f:
                        metadata = json.load(f)
                        blocked = metadata.get("blocked", False)
                except:
                    pass
        
        client.publish(
            f"voicebm/blocklist/{person_id}",
            "ON" if blocked else "OFF",
            qos=1,
            retain=True
        )
        
        # Initialize threshold override (default: None = use global threshold)
        # Read from metadata if available, otherwise leave unset
        threshold = None
        if person_id != "user":
            metadata_path = Path(ENROLL_DIR) / person_id / "metadata.json"
            if metadata_path.exists():
                try:
                    with open(metadata_path, 'r') as f:
                        metadata = json.load(f)
                        threshold = metadata.get("threshold_override")
                except:
                    pass
        
        # Only publish if threshold is explicitly set
        if threshold is not None:
            client.publish(
                f"{person_id}/threshold_override",
                str(threshold),
                qos=1,
                retain=True
            )
        
        # Initialize enable_delete state (OFF by default for safety)
        if person_id != "user":
            client.publish(
                f"voicebm/identity/{person_id}/enable_delete",
                "OFF",
                qos=1,
                retain=True
            )
        
        print(f"Published device config for {person_id} (NEW, blocked={blocked}, threshold={threshold or 'global'})")
    else:
        print(f"Published device config for {person_id} (discovery only, state preserved)")
    
    return True


def scan_enrollments(client, tracked, force_republish=False):
    """
    Scan enrollment directory for persons.
    
    Args:
        client: MQTT client
        tracked: Set of already tracked person_ids
        force_republish: If True, republish ALL (for startup). If False, only publish new ones.
    """
    if not ENROLL_DIR.exists():
        print(f"Enrollment directory not found: {ENROLL_DIR}")
        return tracked
    
    newly_enrolled = []
    republished = []
    
    for person_dir in ENROLL_DIR.iterdir():
        if not person_dir.is_dir():
            continue
        
        person_id = person_dir.name
        
        # ALWAYS publish gallery attributes (updates gallery size even for existing devices)
        publish_gallery_attributes(client, person_id)
        
        # Skip device discovery if already tracked and not forcing republish
        if person_id in tracked and not force_republish:
            continue
        
        # Load metadata for display name
        metadata_file = person_dir / 'metadata.json'
        if metadata_file.exists():
            try:
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
                    display_name = derive_display_name(person_id, metadata)
            except:
                display_name = derive_display_name(person_id)
        else:
            # If no metadata, derive display name from person_id
            display_name = derive_display_name(person_id)
        
        # Determine if this is a new device or republish
        is_new = person_id not in tracked
        
        # Publish device - only publish state for NEW devices
        success = publish_person_device(client, person_id, display_name, is_new_device=is_new)
        
        if success:
            if person_id in tracked:
                republished.append((person_id, display_name))
            else:
                newly_enrolled.append((person_id, display_name))
                tracked.add(person_id)
    
    if newly_enrolled or republished:
        save_tracked_devices(tracked)
        
        if republished:
            print(f"\nRepublished: {len(republished)} person(s)")
            for pid, name in republished:
                print(f"  - {name} ({pid})")
        
        if newly_enrolled:
            print(f"\nNewly enrolled: {len(newly_enrolled)} person(s)")
            for pid, name in newly_enrolled:
                print(f"  - {name} ({pid})")
    
    return tracked


def delete_person_identity(client, person_id, tracked):
    """
    Delete a person's identity completely.
    
    Two-step safety:
    1. Check if delete is enabled
    2. Delete enrollment folder
    3. Clear MQTT retained topics
    4. Remove from tracked devices
    """
    # Check if delete is enabled for this person
    delete_enabled = load_delete_enabled()
    if not delete_enabled.get(person_id, False):
        print(f"' DELETE BLOCKED: {person_id} - enable_delete switch is OFF")
        return tracked
    
    print(f"\n  DELETING IDENTITY: {person_id}")
    
    # 1. Delete enrollment folder
    person_folder = ENROLL_DIR / person_id
    if person_folder.exists():
        try:
            shutil.rmtree(person_folder)
            print(f"  [OK] Deleted folder: {person_folder}")
        except Exception as e:
            print(f"  ' Failed to delete folder: {e}")
            return tracked
    else:
        print(f"    Folder not found: {person_folder}")
    
    # 2. Clear MQTT retained topics (None payload = delete retained)
    discovery_prefix = "homeassistant"
    topics_to_clear = [
        # State topics
        f"voicebm/blocklist/{person_id}",
        f"voicebm/identity/{person_id}/enable_delete",
        f"voicebm/thing/transform/{person_id}/name",
        f"voicebm/thing/merge/tag/{person_id}",
        f"{person_id}/voice",
        f"{person_id}/threshold_override",
        # Discovery topics
        f"{discovery_prefix}/switch/{person_id}_blocklist/config",
        f"{discovery_prefix}/switch/{person_id}_enable_delete/config",
        f"{discovery_prefix}/button/{person_id}_delete/config",
        f"{discovery_prefix}/binary_sensor/{person_id}_voice/config",
        f"{discovery_prefix}/number/{person_id}_threshold/config",
        f"{discovery_prefix}/text/{person_id}_transform_name/config",
        f"{discovery_prefix}/button/{person_id}_transform_execute/config",
        f"{discovery_prefix}/switch/{person_id}_merge_tag/config",
    ]
    
    for topic in topics_to_clear:
        client.publish(topic, None, qos=1, retain=True)
    
    print(f"  [OK] Cleared {len(topics_to_clear)} MQTT retained topics")
    
    # 3. Remove from tracked devices
    if person_id in tracked:
        tracked.discard(person_id)
        save_tracked_devices(tracked)
        print(f"  [OK] Removed from tracked devices")
    
    # 4. Remove from delete_enabled
    if person_id in delete_enabled:
        del delete_enabled[person_id]
        save_delete_enabled(delete_enabled)
    
    # Refresh aggregate blocklist (B-04) - deleted identity may have been blocked
    publish_blocklist_state(client)
    
    print(f"[OK] DELETED: {person_id}\n")
    
    return tracked


class EnrollmentHandler(FileSystemEventHandler):
    """Watch for new enrollment folders"""
    
    def __init__(self, client, tracked):
        self.client = client
        self.tracked = tracked
    
    def on_created(self, event):
        """Handle new folder creation"""
        if not event.is_directory:
            return
        
        person_dir = Path(event.src_path)
        person_id = person_dir.name
        
        # Skip if already tracked
        if person_id in self.tracked:
            return
        
        # Wait a moment for metadata.json to be written
        time.sleep(0.5)
        
        # Load display name
        metadata_file = person_dir / 'metadata.json'
        if metadata_file.exists():
            try:
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
                    display_name = derive_display_name(person_id, metadata)
            except:
                display_name = derive_display_name(person_id)
        else:
            display_name = derive_display_name(person_id)
        
        # Publish device - this IS a new device
        print(f"\n' New enrollment detected: {person_id}")
        success = publish_person_device(self.client, person_id, display_name, is_new_device=True)
        
        if success:
            self.tracked.add(person_id)
            save_tracked_devices(self.tracked)


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print(f"[OK] Connected to MQTT broker at {BROKER}:{PORT}")
        # Subscribe to blocklist commands HERE on connect
        client.subscribe("voicebm/blocklist/+/set", qos=1)
        print("Subscribed to voicebm/blocklist/+/set")
        # Subscribe to delete controls
        client.subscribe("voicebm/identity/+/enable_delete/set", qos=1)
        client.subscribe("voicebm/identity/+/delete", qos=1)
        print("Subscribed to delete control topics")
    else:
        print(f"[X] Failed to connect, reason code: {reason_code}")


def on_message(client, userdata, msg):
    """Handle all incoming messages - required for wildcard topic matching."""
    topic = msg.topic
    payload = msg.payload.decode('utf-8')
    
    # Handle blocklist commands
    if topic.startswith("voicebm/blocklist/") and topic.endswith("/set"):
        handle_blocklist_command(client, userdata, msg)
        return
    
    # Handle enable_delete switch
    if "/enable_delete/set" in topic:
        parts = topic.split('/')
        if len(parts) >= 3:
            person_id = parts[2]
            
            delete_enabled = load_delete_enabled()
            delete_enabled[person_id] = (payload == "ON")
            save_delete_enabled(delete_enabled)
            
            # Publish state back
            client.publish(
                f"voicebm/identity/{person_id}/enable_delete",
                payload,
                qos=1,
                retain=True
            )
            
            status = "ENABLED" if payload == "ON" else "DISABLED"
            print(f"[*] Delete controls {status}: {person_id}")
        return
    
    # Handle delete button press
    if topic.endswith("/delete") and payload == "PRESS":
        parts = topic.split('/')
        if len(parts) >= 3:
            person_id = parts[2]
            
            # Get tracked set from userdata
            tracked = userdata.get('tracked', set())
            tracked = delete_person_identity(client, person_id, tracked)
            userdata['tracked'] = tracked
        return


def get_blocklist_view():
    """
    Build the full identity blocklist view (B-04), mirroring the dashboard's
    get_enrolled_people() source-of-truth pattern EXACTLY so there is one
    definition of where block state lives:

      - virtual 'user'  -> user_settings.json 'blocked' flag ONLY
                           (user has no gallery; it is NEVER read from enroll/)
      - enrolled persons -> their /enroll/{id}/metadata.json 'blocked' flag

    Returns the full list (blocked AND unblocked) so consumers can filter.
    Each entry: {"person_id", "blocked", "is_virtual"}.
    """
    people = []

    # Virtual 'user' - single source: user_settings.json. Never scanned from enroll/.
    try:
        user_blocked = load_user_settings().get('blocked', False)
    except Exception as e:
        print(f"  [blocklist-state] Failed to read user settings: {e}")
        user_blocked = False
    people.append({"person_id": "user", "blocked": bool(user_blocked), "is_virtual": True})

    # Enrolled persons - source: each metadata.json. Skip any stray 'user' folder
    # so the virtual identity is never double-sourced.
    if ENROLL_DIR.exists():
        for person_dir in ENROLL_DIR.iterdir():
            if not person_dir.is_dir():
                continue
            if person_dir.name == "user":
                continue  # user is virtual; its state is user_settings.json only
            metadata_path = person_dir / 'metadata.json'
            blocked = False
            if metadata_path.exists():
                try:
                    with open(metadata_path, 'r') as f:
                        blocked = json.load(f).get('blocked', False)
                except Exception:
                    blocked = False
            people.append({"person_id": person_dir.name, "blocked": bool(blocked), "is_virtual": False})

    return people


def publish_blocklist_state(client):
    """
    Publish the aggregate blocklist as a single readable MQTT topic (B-04).

    Topic:   voicebm/blocklist_state   (retained)
    Payload: JSON object with the full per-identity view, e.g.
             {"user": false, "blanca_sanchez": true, ...}

    Publishes BOTH blocked and unblocked so Home Assistant can filter; this is
    a read-only mirror that NEVER writes any per-person voicebm/blocklist/{id}
    topic, so it cannot drive a switch back to a prior state.
    """
    view = get_blocklist_view()
    payload = {p["person_id"]: p["blocked"] for p in view}
    try:
        client.publish(
            "voicebm/blocklist_state",
            json.dumps(payload),
            qos=1,
            retain=True
        )
        blocked_now = [pid for pid, b in payload.items() if b]
        print(f"  [blocklist-state] Published view (blocked: {blocked_now})")
    except Exception as e:
        print(f"  [blocklist-state] Failed to publish aggregate: {e}")


def handle_blocklist_command(client, userdata, msg):
    """Handle blocklist toggle commands."""
    try:
        # Extract person_id from topic: voicebm/blocklist/{person_id}/set
        parts = msg.topic.split('/')
        if len(parts) < 4:
            print(f"Invalid blocklist topic: {msg.topic}")
            return
        
        person_id = parts[2]
        command = msg.payload.decode('utf-8')
        
        print(f"\nBlocklist command for {person_id}: {command}")
        
        new_blocked = (command == "ON")
        
        if person_id == "user":
            # Handle "user" blocklist separately
            user_settings = load_user_settings()
            user_settings['blocked'] = new_blocked
            user_settings['last_updated'] = time.strftime('%Y-%m-%d %H:%M:%S')
            save_user_settings(user_settings)
        else:
            # Handle enrolled person blocklist
            metadata_path = Path(ENROLL_DIR) / person_id / "metadata.json"
            
            # Create metadata if it doesn't exist
            if not metadata_path.exists():
                print(f"  Creating metadata.json for {person_id}")
                metadata_path.parent.mkdir(parents=True, exist_ok=True)
                metadata = {
                    'person_id': person_id,
                    'display_name': derive_display_name(person_id),
                    'created_at': time.strftime('%Y-%m-%d %H:%M:%S'),
                    'blocked': new_blocked
                }
            else:
                try:
                    with open(metadata_path, 'r') as f:
                        metadata = json.load(f)
                except:
                    metadata = {
                        'person_id': person_id,
                        'display_name': derive_display_name(person_id)
                    }
            
            # Update blocked status
            metadata['blocked'] = new_blocked
            metadata['last_updated'] = time.strftime('%Y-%m-%d %H:%M:%S')
            
            try:
                with open(metadata_path, 'w') as f:
                    json.dump(metadata, f, indent=2)
                print(f"  Metadata saved for {person_id}")
            except Exception as e:
                print(f"  Warning: Failed to save metadata: {e}")
        
        # ALWAYS publish state update back to state topic
        client.publish(
            f"voicebm/blocklist/{person_id}",
            command,
            qos=1,
            retain=True
        )
        
        # Publish aggregate blocklist (B-04) after any change
        publish_blocklist_state(client)
        
        status = "BLOCKED" if new_blocked else "UNBLOCKED"
        print(f"  {status}: {person_id}")
        
    except Exception as e:
        print(f"  Error handling blocklist command: {e}")
        import traceback
        traceback.print_exc()


def main():
    """
    Main enrollment watcher loop.
    
    Startup behavior:
    1. Scans enrollment directory
    2. REPUBLISHES device config for ALL enrolled persons (even if tracked)
    3. This ensures devices exist in MQTT/HA even if manually deleted
    4. unique_id prevents duplicates
    
    Runtime behavior:
    1. Watches for NEW enrollment folders
    2. Publishes device config only for newly created persons
    """
    print("=" * 60)
    print("VoiceBM Enrollment Watcher")
    print("=" * 60)
    print(f"Monitoring: {ENROLL_DIR}")
    print(f"MQTT Broker: {BROKER}:{PORT}")
    print(f"Current Room: living")
    print("=" * 60)
    
    # Check for duplicate person folders (e.g., 'David Dryver Sr' vs 'david_dryver_sr')
    duplicates = check_for_duplicate_folders()
    if duplicates:
        print("\nWARNING: Duplicate person folders detected!")
        print("These folders normalize to the same person_id:")
        for normalized_id, folder_list in duplicates.items():
            print(f"  {normalized_id}:")
            for folder in folder_list:
                print(f"    - {folder}")
        print("\nRecommendation: Delete duplicate folders and keep only lowercase_with_underscores format")
        print("Example: Keep 'david_dryver_sr', delete 'David Dryver Sr'\n")
    
    # Create enrollment directory if it doesn't exist
    ENROLL_DIR.mkdir(parents=True, exist_ok=True)
    
    # Connect to MQTT
    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(USER, PASS)
    client.on_connect = on_connect
    
    try:
        client.connect(BROKER, PORT, 60)
    except Exception as e:
        print(f"[X] MQTT connection failed: {e}")
        return
    
    client.loop_start()
    
    # Load tracked devices
    tracked = load_tracked_devices()
    print(f"\nAlready enrolled: {len(tracked)} person(s)")
    if tracked:
        for pid in sorted(tracked):
            print(f"  - {pid}")
    
    # CRITICAL: Create "user" device for non-enrolled speakers (now with blocklist!)
    # Only publish initial state if "user" is not already tracked
    user_is_new = "user" not in tracked
    print(f"\nCreating 'user' device for non-enrolled speakers (is_new={user_is_new})...")
    publish_person_device(client, "user", "user", is_new_device=user_is_new)
    if user_is_new:
        tracked.add("user")
        save_tracked_devices(tracked)
    
    # STARTUP: Force republish ALL enrolled persons (in case devices were deleted in MQTT/HA)
    print("\nRepublishing all enrolled devices on startup...")
    tracked = scan_enrollments(client, tracked, force_republish=True)
    
    # Publish aggregate blocklist state once at startup (B-04)
    publish_blocklist_state(client)
    
    # Set up filesystem watcher
    event_handler = EnrollmentHandler(client, tracked)
    observer = Observer()
    observer.schedule(event_handler, str(ENROLL_DIR), recursive=False)
    
    # Set userdata for on_message handlers (needed for delete functionality)
    client.user_data_set({'tracked': tracked})
    
    # Set on_message callback for wildcard topic handling (blocklist, delete commands)
    client.on_message = on_message
    
    observer.start()
    
    print("\n[OK] Watching for new enrollments...")
    print("Press Ctrl+C to exit\n")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\nShutting down...")
        observer.stop()
        observer.join()
        client.loop_stop()
        client.disconnect()
        print("[OK] Enrollment watcher stopped")


if __name__ == "__main__":
    main()



################################################################################
```


## 9. `mqtt_commands.py` <a id="9-mqtt-commandspy"></a>

_MQTT Command Listener for Voice Biometrics - Label/Reject Events_

```python
#!/usr/bin/env python3
"""MQTT Command Listener for Voice Biometrics - Label/Reject Events

UPDATED: Now room-aware (handles all rooms with one service)
"""

import os
import json
import time
import datetime
import paho.mqtt.client as mqtt

# MQTT Configuration (centralized)
import sys
sys.path.insert(0, '/home/user/voicebm')
from voicebm_config import get_mqtt_config

mqtt_config = get_mqtt_config()
BROKER = mqtt_config['broker']
PORT = mqtt_config['port']
USER = mqtt_config['user']
PASS = mqtt_config['password']

# Base directories (room-agnostic)
VOICEBM_BASE = "/home/user/voicebm"
META_LAB = f"/home/user/voicebm/meta/labeled"
ENROLL_DIR = f"/home/user/voicebm/enroll"
THRESHOLD_FILE = "/home/user/voicebm/out/thresholds.json"
DEFAULT_GALLERY_MAX = 0


def get_gallery_max():
    """Read GALLERY_MAX from thresholds.json. 0/missing = unlimited."""
    try:
        if os.path.exists(THRESHOLD_FILE):
            with open(THRESHOLD_FILE, "r") as f:
                return int(json.load(f).get("GALLERY_MAX", DEFAULT_GALLERY_MAX))
    except Exception:
        pass
    return DEFAULT_GALLERY_MAX


def enforce_gallery_cap(person_dir, metadata):
    """
    Trim a person's gallery to GALLERY_MAX samples, dropping the OLDEST first.
    Deletes pruned embedding .txt and recording .wav files, updates metadata in
    place, returns it. No-op when GALLERY_MAX <= 0 or count within cap.

    NOTE: kept self-contained (not imported from the STT service) because these
    run as separate processes in different contexts. Mirror of the STT helper.
    """
    from pathlib import Path
    cap = get_gallery_max()
    samples = metadata.get("samples", [])
    if cap <= 0 or len(samples) <= cap:
        return metadata

    ordered = sorted(samples, key=lambda s: s.get("enrolled_at", ""))
    drop_count = len(ordered) - cap
    to_drop = ordered[:drop_count]
    keep = ordered[drop_count:]

    for s in to_drop:
        for rel_key in ("embedding", "recording"):
            rel = s.get(rel_key)
            if not rel:
                continue
            fpath = Path(person_dir) / rel
            try:
                if fpath.exists():
                    fpath.unlink()
                    print(f"  [gallery_cap] Pruned {rel_key}: {fpath.name}")
            except Exception as e:
                print(f"  [gallery_cap] Failed to prune {fpath}: {e}")

    metadata["samples"] = keep
    metadata["total_samples"] = len(keep)
    print(f"  [gallery_cap] Trimmed gallery to {len(keep)}/{cap} samples")
    return metadata

# Subscribe to all rooms
LABEL_TOPIC_PATTERN = "voicebm/+/label"
REJECT_TOPIC_PATTERN = "voicebm/+/reject"

def iso_now():
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

def label_event(eid, person_id, room):
    """
    Label an event and enroll it to a person.
    
    Args:
        eid: Event ID
        person_id: Person identifier
        room: Room name (for finding files)
    """
    import shutil
    from pathlib import Path
    
    ts_label = int(time.time())
    expire_at = datetime.datetime.utcfromtimestamp(
        ts_label + 3*24*3600
    ).replace(microsecond=0).isoformat() + "Z"

    # Create labeled metadata
    os.makedirs(META_LAB, exist_ok=True)
    sidecar = os.path.join(META_LAB, f"{eid}.json")
    data = {
        "id": eid,
        "room": room,
        "status": "labeled",
        "person_id": person_id,
        "ts_labeled": iso_now(),
        "expire_at": expire_at
    }
    with open(sidecar, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Labeled event {eid} from {room} as person {person_id}")

    # Create enrollment directory structure
    person_dir = Path(ENROLL_DIR) / person_id
    embeddings_dir = person_dir / "embeddings"
    recordings_dir = person_dir / "recordings"
    
    person_dir.mkdir(parents=True, exist_ok=True)
    embeddings_dir.mkdir(exist_ok=True)
    recordings_dir.mkdir(exist_ok=True)
    
    # Load existing metadata if it exists
    metadata_file = person_dir / 'metadata.json'
    if metadata_file.exists():
        with open(metadata_file, 'r') as f:
            metadata = json.load(f)
            existing_samples = metadata.get('samples', [])
    else:
        # Create display name from person_id
        display_name = person_id.replace('_', ' ').title()
        metadata = {
            'person_id': person_id,
            'display_name': display_name,
            'created_at': iso_now()
        }
        existing_samples = []
    
    # Source files (room-specific paths)
    rec_dir = f"/home/user/voicebm/recordings/{room}"
    emb_dir = f"/home/user/voicebm/embeddings/{room}"
    
    emb_src = Path(emb_dir) / f"{eid}.txt"
    rec_src = Path(rec_dir) / f"{eid}.wav"
    
    emb_dst = embeddings_dir / f"{eid}.txt"
    rec_dst = recordings_dir / f"{eid}.wav"
    
    # Calculate 3-day expiration for review period
    ts_enroll = int(time.time())
    expire_at = datetime.datetime.utcfromtimestamp(
        ts_enroll + 3*24*3600
    ).replace(microsecond=0).isoformat() + "Z"
    
    # MOVE embedding (not copy)
    if emb_src.exists() and not emb_dst.exists():
        try:
            shutil.move(str(emb_src), str(emb_dst))
            print(f"  âœ“ Moved embedding: {eid}.txt")
        except Exception as e:
            print(f"  âœ— Failed to move embedding: {e}")
    elif emb_dst.exists():
        print(f"  âš   Embedding already exists: {eid}.txt")
    else:
        print(f"  âœ— Embedding NOT FOUND at: {emb_src}")
    
    # MOVE recording (not copy)
    wav_moved = False
    if rec_src.exists():
        if not rec_dst.exists():
            try:
                shutil.move(str(rec_src), str(rec_dst))
                print(f"  âœ“ Moved recording: {eid}.wav")
                wav_moved = True
            except Exception as e:
                print(f"  âœ— Failed to move recording: {e}")
        else:
            print(f"  âš   Recording already exists: {eid}.wav")
            wav_moved = True
    else:
        print(f"  âœ— Recording NOT FOUND at: {rec_src}")
        print(f"     Looked in: {rec_dir}")
        print(f"     Event ID: {eid}")
    
    # Track sample in metadata
    sample_entry = {
        'event_id': eid,
        'embedding': f"embeddings/{eid}.txt",
        'recording': f"recordings/{eid}.wav" if wav_moved else None,
        'enrolled_at': iso_now(),
        'expire_at': expire_at,
        'retention_days': 3,
        'source_room': room
    }
    
    # Update metadata
    metadata['samples'] = existing_samples + [sample_entry]
    metadata['last_updated'] = iso_now()
    metadata['total_samples'] = len(metadata['samples'])
    
    # Gallery rollover cap: prune oldest beyond GALLERY_MAX (no-op if unlimited)
    metadata = enforce_gallery_cap(person_dir, metadata)
    
    with open(metadata_file, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    print(f"Enrolled to {person_id}, total samples: {metadata['total_samples']}")


def reject_event(eid, room):
    """Delete both .wav and .txt files for rejected event"""
    rec_dir = f"/home/user/voicebm/recordings/{room}"
    emb_dir = f"/home/user/voicebm/embeddings/{room}"
    
    deleted = []
    errors = []
    
    # Delete .wav file
    wav_path = os.path.join(rec_dir, f"{eid}.wav")
    if os.path.exists(wav_path):
        try:
            os.remove(wav_path)
            deleted.append(f"WAV: {wav_path}")
            print(f"  âœ“ Deleted: {wav_path}")
        except Exception as e:
            errors.append(f"WAV delete failed: {e}")
            print(f"  âœ— Failed to delete WAV: {e}")
    else:
        print(f"  âš   WAV not found: {wav_path}")
    
    # Delete .txt embedding file
    emb_path = os.path.join(emb_dir, f"{eid}.txt")
    if os.path.exists(emb_path):
        try:
            os.remove(emb_path)
            deleted.append(f"EMB: {emb_path}")
            print(f"  âœ“ Deleted: {emb_path}")
        except Exception as e:
            errors.append(f"EMB delete failed: {e}")
            print(f"  âœ— Failed to delete embedding: {e}")
    else:
        print(f"  âš   Embedding not found: {emb_path}")
    
    # Summary
    if deleted:
        print(f"Rejected event {eid} from {room} - deleted {len(deleted)} file(s)")
    if errors:
        print(f"Errors during rejection: {errors}")
    if not deleted and not errors:
        print(f"Rejected event {eid} from {room} - no files found to delete")

def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print(f"Connected to MQTT broker at {BROKER}:{PORT}")
        # Subscribe to all rooms
        client.subscribe([(LABEL_TOPIC_PATTERN, 1), (REJECT_TOPIC_PATTERN, 1)])
        print(f"Subscribed to:")
        print(f"  - {LABEL_TOPIC_PATTERN}")
        print(f"  - {REJECT_TOPIC_PATTERN}")
        print(f"Listening for commands from ALL rooms")
    else:
        print(f"Failed to connect, reason code: {reason_code}")

def on_message(client, userdata, msg):
    try:
        payload_str = msg.payload.decode("utf-8")
        
        # Extract room from topic: voicebm/{room}/label or voicebm/{room}/reject
        topic_parts = msg.topic.split('/')
        if len(topic_parts) < 3:
            print(f"  Error: Invalid topic format: {msg.topic}")
            return
        
        room = topic_parts[1]
        action = topic_parts[2]
        
        print(f"\nReceived on {msg.topic} (room={room}, action={action}):")
        print(f"  Payload: {payload_str}")
        
        p = json.loads(payload_str)
        eid = p.get("id")
        if not eid:
            print("  Error: No 'id' field in payload")
            return
            
        if action == "label":
            pid = p.get("person_id")
            if not pid:
                print("  Error: No 'person_id' field in label payload")
                return
            label_event(eid, pid, room)
        elif action == "reject":
            reject_event(eid, room)
        else:
            print(f"  Unknown action: {action}")
            
    except json.JSONDecodeError as e:
        print(f"  Error: Invalid JSON - {e}")
    except Exception as e:
        print(f"  Error processing message: {e}")
        import traceback
        traceback.print_exc()

def main():
    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(USER, PASS)
    client.on_connect = on_connect
    client.on_message = on_message
    
    try:
        client.connect(BROKER, PORT, 60)
    except Exception as e:
        print(f"Connection failed: {e}")
        return
    
    print("=" * 60)
    print("VoiceBM MQTT Command Listener (Room-Aware)")
    print("=" * 60)
    print("Handles label/reject commands from ALL rooms")
    print("Press Ctrl+C to exit\n")
    
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        client.disconnect()

if __name__ == "__main__":
    main()
```


# Workers — per-call inference (subprocess)


## 10. `sherpa_embed.py` <a id="10-sherpa-embedpy"></a>

```python
#!/usr/bin/env python3
import sys, wave, numpy as np
import sherpa_onnx

def load_wav_f32(path):
    with wave.open(path, "rb") as w:
        ch = w.getnchannels()
        sr = w.getframerate()
        sw = w.getsampwidth()
        n = w.getnframes()
        raw = w.readframes(n)

    # Supported widths: 16-bit or 32-bit PCM
    if sw == 2:
        pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif sw == 4:
        pcm = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        raise RuntimeError(f"Unsupported sample width: {sw} bytes")

    # Convert stereo → mono
    if ch > 1:
        pcm = pcm.reshape(-1, ch).mean(axis=1)

    return sr, pcm

def main():
    args = sys.argv
    model = args[args.index("--model")+1]
    wav   = args[args.index("--wav")+1]
    out   = args[args.index("--out")+1]

    sr, pcm = load_wav_f32(wav)

    cfg = sherpa_onnx.SpeakerEmbeddingExtractorConfig(
        model=model,
        num_threads=1,
        debug=False
    )
    extractor = sherpa_onnx.SpeakerEmbeddingExtractor(cfg)

    stream = extractor.create_stream()
    stream.accept_waveform(sr, pcm)
    stream.input_finished()

    emb = extractor.compute(stream)

    with open(out, "w") as f:
        f.write(" ".join(str(x) for x in emb))

if __name__ == "__main__":
    main()
```


## 11. `ser_worker.py` <a id="11-ser-workerpy"></a>

_VoiceBM Emote Edition — pre-alpha_

```python
#!/usr/bin/python3
"""
VoiceBM Emote Edition — pre-alpha
SenseVoice emotion inference worker. Standalone, runs under vb Python.
Per-call: loads model, runs inference, writes JSON result to output file, exits.
Called by ser_infer.sh which is called by voicebm_emote.py thread.

Usage: ser_worker.py --wav <path> --out <json_path>

Output JSON: {"emotion": "neutral", "scores": {"neutral": 0.72, "sad": 0.24, ...}}

Scores are real normalized probabilities derived from CTC logits,
not one-hot. Dominant emotion is the highest-scoring class.

Real emotion classes (from model.emo_dict, unk excluded):
  happy, sad, angry, neutral
"""

import sys
import argparse
import json
import math

MODEL_ID = 'FunAudioLLM/SenseVoiceSmall'


def run_ser(wav_path, output_path):
    try:
        import torch
        import soundfile as sf
        from funasr import AutoModel
        from funasr.utils.load_utils import load_audio_text_image_video, extract_fbank

        # ── Load model ────────────────────────────────────────────────────
        auto = AutoModel(
            model=MODEL_ID,
            hub='hf',
            device='cpu',
            disable_update=True,
        )
        m         = auto.model
        tokenizer = auto.kwargs['tokenizer']
        frontend  = auto.kwargs['frontend']

        # ── Prepare audio input ───────────────────────────────────────────
        audio_sample_list = load_audio_text_image_video(
            wav_path,
            fs=frontend.fs,
            audio_fs=16000,
            data_type='sound',
            tokenizer=tokenizer,
        )
        speech, speech_lengths = extract_fbank(
            audio_sample_list,
            data_type='sound',
            frontend=frontend,
        )

        # ── Build input sequence (mirrors inference() internals) ──────────
        # Prepend language, textnorm, and event+emotion query embeddings
        # exactly as the model expects before the encoder sees the audio.
        language_query = m.embed(
            torch.LongTensor([[m.lid_dict['en']]]).to('cpu')
        ).repeat(speech.size(0), 1, 1)

        textnorm_query = m.embed(
            torch.LongTensor([[m.textnorm_dict['woitn']]]).to('cpu')
        ).repeat(speech.size(0), 1, 1)

        speech = torch.cat((textnorm_query, speech), dim=1)
        speech_lengths += 1

        event_emo_query = m.embed(
            torch.LongTensor([[1, 2]]).to('cpu')
        ).repeat(speech.size(0), 1, 1)

        input_query = torch.cat((language_query, event_emo_query), dim=1)
        speech = torch.cat((input_query, speech), dim=1)
        speech_lengths += 3

        # ── Encoder + CTC logits ──────────────────────────────────────────
        with torch.no_grad():
            encoder_out, encoder_out_lens = m.encoder(speech, speech_lengths)
            if isinstance(encoder_out, tuple):
                encoder_out = encoder_out[0]
            # Shape: [1, frames, vocab_size] — log probabilities
            ctc_logits = m.ctc.log_softmax(encoder_out)

        # ── Extract emotion scores ────────────────────────────────────────
        # emo_dict: {'unk': 25009, 'happy': 25001, 'sad': 25002,
        #            'angry': 25003, 'neutral': 25004}
        # Take max log-prob across all frames for each emotion token.
        # unk is excluded (mirrors ban_emo_unk=True in generate()).
        valid_frames = encoder_out_lens[0].item()
        log_scores = {}
        for label, tok_id in m.emo_dict.items():
            if label == 'unk':
                continue
            frame_log_probs = ctc_logits[0, :valid_frames, tok_id]
            log_scores[label] = frame_log_probs.max().item()

        # ── Normalize to probability distribution ─────────────────────────
        raw_probs = {k: math.exp(v) for k, v in log_scores.items()}
        total     = sum(raw_probs.values())
        scores    = {k: round(v / total, 4) for k, v in raw_probs.items()}

        # ── Dominant emotion = highest normalized score ───────────────────
        emotion = max(scores, key=scores.get)

        print(f"[ser_worker] emotion={emotion} scores={scores}", file=sys.stderr)

        result = {'emotion': emotion, 'scores': scores}
        with open(output_path, 'w') as f:
            json.dump(result, f)

        return True

    except ImportError as e:
        print(f"ERROR: import failed: {e}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"ERROR: SER inference failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SenseVoice emotion inference worker")
    parser.add_argument("--wav", required=True, help="Input WAV file")
    parser.add_argument("--out", required=True, help="Output JSON file")
    args = parser.parse_args()
    success = run_ser(args.wav, args.out)
    sys.exit(0 if success else 1)
```


# Emote add-on — Speech Emotion Recognition (active side)


## 12. `voicebm_emote.py` <a id="12-voicebm-emotepy"></a>

_VoiceBM Emote Edition — pre-alpha_

```python
#!/usr/bin/env python3
"""
VoiceBM Emote Edition — pre-alpha
Speech Emotion Recognition primitive for the active pipeline.

Sits post-VAD on the active side. Receives the same audio slice as the
STT/identity pipeline. Resolves a dominant emotional state and publishes
it to MQTT.

Threading model: run_emote fires a daemon thread. The thread calls
ser_infer.sh (subprocess, per utterance), reads the JSON result, and
publishes to MQTT. The paho client publish() is thread-safe. The main
paho loop is never blocked.

MQTT topics published:
  voicebm/emote/state   — dominant state string (neutral/happy/sad/angry/etc)
  voicebm/emote/scores  — one-hot JSON dict

HA entities land on the existing Voice Biometrics device.

Plug-in contract:
  Install:  drop ser_worker.py + ser_infer.sh + voicebm_emote.py, restart
  Remove:   delete those three files, restart — core unaffected
  Broken:   soft import in voicebm_stt_service.py loads no-ops
"""

import os
import json
import subprocess
import tempfile
import threading

SER_SCRIPT = "/home/user/voicebm/bin/ser_infer.sh"
CONFIG_FILE = "/home/user/voicebm/config.json"


def _emote_config():
    """SER script path + timeout from config.json -> emote (safe defaults).
    Read per call — live-tunable, and a broken config never breaks the hook."""
    script, timeout = SER_SCRIPT, 60
    try:
        with open(CONFIG_FILE, 'r') as f:
            emote = json.load(f).get('emote', {})
        script  = emote.get('ser_script', script)
        timeout = float(emote.get('ser_timeout_s', timeout))
    except Exception:
        pass
    return script, timeout

DISCOVERY_PREFIX = "homeassistant"

DEVICE = {
    "identifiers": ["voicebm"],
    "name": "Voice Biometrics",
    "manufacturer": "David M. Dryver Sr.",
    "model": "Home Assistant Voice Biometrics",
    "sw_version": "1.0",
}


def publish_emote_discovery(client):
    """
    Publish HA MQTT discovery for the two Emote Edition entities.
    Called once on MQTT connect. Retained — safe to call on every restart.
    """
    state_config = {
        "name": "Emote State",
        "unique_id": "voicebm_emote_state",
        "state_topic": "voicebm/emote/state",
        "icon": "mdi:emoticon-outline",
        "device": DEVICE,
    }
    client.publish(
        f"{DISCOVERY_PREFIX}/sensor/voicebm_emote_state/config",
        json.dumps(state_config),
        qos=1,
        retain=True,
    )

    scores_config = {
        "name": "Emote Scores",
        "unique_id": "voicebm_emote_scores",
        "state_topic": "voicebm/emote/scores",
        "value_template": "{{ value_json.keys() | list | length }}",
        "json_attributes_topic": "voicebm/emote/scores",
        "icon": "mdi:chart-bar",
        "device": DEVICE,
    }
    client.publish(
        f"{DISCOVERY_PREFIX}/sensor/voicebm_emote_scores/config",
        json.dumps(scores_config),
        qos=1,
        retain=True,
    )

    print("[emote] Published MQTT discovery: Emote State, Emote Scores")


def run_emote(audio_path, client):
    """
    Run SER on audio_path and publish state + scores to MQTT.

    Fires a daemon thread — returns immediately. The thread calls
    ser_infer.sh, reads the result JSON, and publishes via the same
    paho client. publish() is thread-safe in paho.

    Any failure in the thread is caught and logged. Core pipeline
    is never affected regardless of outcome.
    """

    def _infer():
        result_path = None
        try:
            ser_script, ser_timeout = _emote_config()

            with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as tmp:
                result_path = tmp.name

            result = subprocess.run(
                [ser_script, audio_path, result_path],
                capture_output=True,
                text=True,
                timeout=ser_timeout,
            )

            if result.returncode != 0:
                print(f"[emote] SER script failed (rc={result.returncode}): {result.stderr.strip()}")
                return

            with open(result_path, 'r') as f:
                data = json.load(f)

            emotion = data.get('emotion', 'unknown')
            scores = data.get('scores', {})

            client.publish("voicebm/emote/state",  emotion,            qos=1, retain=True)
            client.publish("voicebm/emote/scores", json.dumps(scores), qos=1, retain=True)

            print(f"[emote] state={emotion}")

        except subprocess.TimeoutExpired:
            print("[emote] SER timed out — skipping")
        except Exception as e:
            print(f"[emote] Failed: {e}")
        finally:
            if result_path:
                try:
                    os.unlink(result_path)
                except OSError:
                    pass

    threading.Thread(target=_infer, daemon=True).start()
```


# Ambient add-on — Audio Event Detection (passive side)


## 13. `voicebm_ambient.py` <a id="13-voicebm-ambientpy"></a>

_VoiceBM Ambient Edition — Audio Event Detection Service_

```python
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
```


## 14. `voicebm_ambient_hooks.py` <a id="14-voicebm-ambient-hookspy"></a>

_VoiceBM Ambient Edition — Passive Context Soft Hooks (pre-alpha)_

```python
#!/usr/bin/env python3
"""
VoiceBM Ambient Edition — Passive Context Soft Hooks (pre-alpha)

Joins ambient speech detection with identity resolution and emotion in a
single per-room topic. Real-time: a fresh embedding is created from the
exact WAV slice that triggered the ambient speech event — never relies on
the passive pipeline's embedder cycle.

Plug-in contract:
  Install:  drop this file in /home/user/voicebm/bin/, restart ambient
  Remove:   delete this file, restart — ambient unaffected
  Broken:   soft import in voicebm_ambient.py no-ops

Hook activation (checked at runtime, per capability):
  Identity: vb python + sherpa_embed.py + titanet model + enroll/ exist
  Emote:    ser_infer.sh exists (optional — omitted from payload if absent)
  No identity capability -> nothing publishes; ambient runs as before.

Publishes (per room, retained):
  voicebm/{room}/passive_context
    {
      "ts":       ISO timestamp (first — David's spec: ts, speech, identity, emote),
      "room":     room,
      "source":   stream name,
      "speech":   {"state": ..., "prob": ...},
      "identity": {"speaker_id", "display_name", "confidence", "decision"},
      "emote":    {"state": ..., "scores": {...}}        # only if Emote installed
    }

HA discovery: one sensor per room, attached to the room's existing
Voice Biometrics device (identifiers ["voicebm_{room}"]). MQTT discovery
merges onto the device if the passive side already created it, or creates
it if not. Never duplicates.

Identity follows the VoiceBM identity state model: speech occurred and the
voice did not match the gallery -> identity is "user". Threshold is the
PASSIVE threshold (out/thresholds.json MATCH_T) — this is passive ambient
context, not live STT injection.

Threading: one daemon thread per speech event, guarded by a non-blocking
in-flight lock — if a context job is still running, the new event is
skipped and logged. Protects the host from stacked CPU inference.
"""

import os
import json
import time
import shutil
import tempfile
import threading
import subprocess

import numpy as np
from pathlib import Path

# ── Fixed paths (canonical VoiceBM layout — overridable via config.json) ──────
SHERPA_PYTHON = '/home/user/miniforge3/envs/vb/bin/python3'
SHERPA_WORKER = '/home/user/.local/bin/sherpa_embed.py'
SHERPA_MODEL  = '/home/user/sherpa_models/nemo_en_titanet_small.onnx'
SER_SCRIPT    = '/home/user/voicebm/bin/ser_infer.sh'
ENROLL_DIR    = '/home/user/voicebm/enroll'
THR_FILE      = '/home/user/voicebm/out/thresholds.json'
CONFIG_FILE   = '/home/user/voicebm/config.json'

DISCOVERY_PREFIX = 'homeassistant'


def _hook_config():
    """Tunables from config.json with safe fallbacks:
    paths.sherpa_model, voicebm.embed_timeout_s, emote.ser_timeout_s,
    emote.ser_script."""
    model, embed_t, ser_script, ser_t = SHERPA_MODEL, 30, SER_SCRIPT, 60
    try:
        with open(CONFIG_FILE, 'r') as f:
            cfg = json.load(f)
        model      = cfg.get('paths', {}).get('sherpa_model', model)
        embed_t    = float(cfg.get('voicebm', {}).get('embed_timeout_s', embed_t))
        ser_script = cfg.get('emote', {}).get('ser_script', ser_script)
        ser_t      = float(cfg.get('emote', {}).get('ser_timeout_s', ser_t))
    except Exception:
        pass
    return model, embed_t, ser_script, ser_t

# In-flight guard — one context job at a time
_inflight = threading.Lock()


def _child_env():
    """
    Subprocess env mirroring the active pipeline's invocation conditions.
    The ambient service runs with PYTHONNOUSERSITE=1 (required for AST),
    but sherpa_onnx lives in user site-packages — the workers must see it,
    exactly as they do when called from voicebm-stt.service.
    """
    env = os.environ.copy()
    env.pop('PYTHONNOUSERSITE', None)
    return env


# ─────────────────────────────────────────────────────────────────────────────
# Capability checks
# ─────────────────────────────────────────────────────────────────────────────
def identity_available():
    model, _, _, _ = _hook_config()
    return (os.path.exists(SHERPA_PYTHON)
            and os.path.exists(SHERPA_WORKER)
            and os.path.exists(model)
            and os.path.isdir(ENROLL_DIR))


def emote_available():
    _, _, ser_script, _ = _hook_config()
    return os.path.exists(ser_script)


# ─────────────────────────────────────────────────────────────────────────────
# Gallery (mirrors publish_identity_living.py exactly)
# ─────────────────────────────────────────────────────────────────────────────
def load_gallery():
    """Load enrolled speakers from /enroll/. Returns {(person_id, display_name): centroid}."""
    people = {}
    enroll_path = Path(ENROLL_DIR)

    if not enroll_path.exists():
        return {}

    try:
        for person_dir in enroll_path.iterdir():
            if not person_dir.is_dir():
                continue

            person_id      = person_dir.name
            embeddings_dir = person_dir / 'embeddings'
            metadata_file  = person_dir / 'metadata.json'

            if metadata_file.exists():
                try:
                    with open(metadata_file, 'r') as f:
                        metadata = json.load(f)
                        display_name = metadata.get('display_name', person_id.replace('_', ' ').title())
                except Exception:
                    display_name = person_id.replace('_', ' ').title()
            else:
                display_name = person_id.replace('_', ' ').title()

            if not embeddings_dir.exists():
                continue

            vectors = []
            for emb_file in embeddings_dir.glob('*.txt'):
                try:
                    v = np.loadtxt(emb_file)
                    if v is not None and len(v) > 0:
                        vectors.append(v)
                except Exception:
                    pass

            if vectors:
                people[(person_id, display_name)] = vectors

    except Exception as e:
        print(f'[ambient-hooks] gallery load error: {e}')
        return {}

    cents = {}
    for (sid, name), vecs in people.items():
        cents[(sid, name)] = np.mean(vecs, axis=0)
    return cents


def cos(a, b):
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def passive_threshold():
    try:
        with open(THR_FILE, 'r') as f:
            thr = json.load(f)
            return float(thr.get('MATCH_T', 0.22))
    except Exception:
        return 0.22


def ambient_thresholds():
    """
    Dedicated decision knobs for ambient-probe identity.
    Far-field camera audio is its own domain — neither the passive nor the
    active pipeline threshold fits it. config.json -> thresholds:
      ambient_context — absolute floor for acceptance (default 0.18)
      ambient_margin  — best must beat runner-up by this gap (default 0.05)
    Falls back to the passive MATCH_T if ambient_context is not configured.
    """
    try:
        with open('/home/user/voicebm/config.json', 'r') as f:
            thr = json.load(f).get('thresholds', {})
        match_t = float(thr.get('ambient_context', passive_threshold()))
        margin  = float(thr.get('ambient_margin', 0.05))
        return match_t, margin
    except Exception:
        return passive_threshold(), 0.05


# ─────────────────────────────────────────────────────────────────────────────
# Workers
# ─────────────────────────────────────────────────────────────────────────────
def _embed(wav_path):
    """Run sherpa embedding on wav_path. Returns vector or None."""
    emb_path = None
    try:
        model, embed_t, _, _ = _hook_config()

        with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as tmp:
            emb_path = tmp.name

        result = subprocess.run(
            [SHERPA_PYTHON, SHERPA_WORKER,
             '--model', model,
             '--wav', wav_path,
             '--out', emb_path],
            capture_output=True,
            text=True,
            timeout=embed_t,
            env=_child_env(),
        )
        if result.returncode != 0:
            print(f'[ambient-hooks] embed failed (rc={result.returncode}): {result.stderr.strip()}')
            return None

        v = np.loadtxt(emb_path)
        if v is None or len(v) == 0:
            return None
        return v

    except subprocess.TimeoutExpired:
        print('[ambient-hooks] embed timed out — skipping')
        return None
    except Exception as e:
        print(f'[ambient-hooks] embed error: {e}')
        return None
    finally:
        if emb_path:
            try:
                os.unlink(emb_path)
            except OSError:
                pass


def _resolve_identity(wav_path):
    """
    Fresh embedding -> gallery match -> identity.

    Decision rule (ambient-probe domain):
      accept iff best >= ambient_context threshold
               AND best beats the runner-up by ambient_margin.
    A best-vs-runner-up gap inside the margin is a coin flip, not a match —
    coin flips resolve to 'user' (the error trap doing its job).
    Speech occurred: no acceptance means 'user' (VoiceBM identity state model).
    """
    v = _embed(wav_path)
    if v is None:
        return None

    cents           = load_gallery()
    match_t, margin = ambient_thresholds()

    best_sid, best_name, best_sim = None, None, -1.0
    second_sid, second_sim        = None, -1.0
    for (psid, pname), cent in cents.items():
        sim = cos(v, cent)
        if sim > best_sim:
            second_sid, second_sim = best_sid, best_sim
            best_sid, best_name, best_sim = psid, pname, sim
        elif sim > second_sim:
            second_sid, second_sim = psid, sim

    gap = best_sim - second_sim if second_sid is not None else None
    print(f'[ambient-hooks] resolve: best={best_sid}({best_sim:.4f}) '
          f'2nd={second_sid}({second_sim:.4f}) '
          f'thr={match_t} margin={margin}'
          if second_sid is not None else
          f'[ambient-hooks] resolve: best={best_sid}({best_sim:.4f}) thr={match_t}')

    accepted = bool(cents) and best_sim >= match_t and (gap is None or gap >= margin)

    if accepted:
        return {
            'speaker_id':   best_sid,
            'display_name': best_name,
            'confidence':   round(best_sim, 4),
            'decision':     'accepted',
        }

    return {
        'speaker_id':   'user',
        'display_name': 'user',
        'confidence':   round(max(best_sim, 0.0), 4),
        'decision':     'unknown',
    }


def _resolve_emote(wav_path):
    """Run SER on wav_path. Returns {'state', 'scores'} or None."""
    result_path = None
    try:
        _, _, ser_script, ser_t = _hook_config()

        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as tmp:
            result_path = tmp.name

        result = subprocess.run(
            [ser_script, wav_path, result_path],
            capture_output=True,
            text=True,
            timeout=ser_t,
            env=_child_env(),
        )
        if result.returncode != 0:
            print(f'[ambient-hooks] SER failed (rc={result.returncode}): {result.stderr.strip()}')
            return None

        with open(result_path, 'r') as f:
            data = json.load(f)

        return {
            'state':  data.get('emotion', 'unknown'),
            'scores': data.get('scores', {}),
        }

    except subprocess.TimeoutExpired:
        print('[ambient-hooks] SER timed out — skipping')
        return None
    except Exception as e:
        print(f'[ambient-hooks] SER error: {e}')
        return None
    finally:
        if result_path:
            try:
                os.unlink(result_path)
            except OSError:
                pass


# ─────────────────────────────────────────────────────────────────────────────
# Public API — called from voicebm_ambient.py
# ─────────────────────────────────────────────────────────────────────────────
def publish_context_discovery(client, sources):
    """
    One Passive Context sensor per room, attached to the room's
    Voice Biometrics device. Discovery merges onto the existing device
    (identifiers ["voicebm_{room}"]) or creates it — never duplicates.
    Called once on MQTT connect. Retained.
    """
    if not identity_available():
        print('[ambient-hooks] identity capability missing — passive context inactive')
        return

    for source in sources:
        room = source['room']
        uid  = room.replace(' ', '_').lower()
        nice = source.get('friendly_name', room.replace('_', ' ').title())

        device = {
            'identifiers': [f'voicebm_{uid}'],
            'name': f'Voice Biometrics {nice}',
            'manufacturer': 'David M. Dryver Sr.',
            'model': 'Home Assistant Voice Biometrics',
            'sw_version': '2.0',
        }

        config = {
            'name': 'Passive Context',
            'unique_id': f'voicebm_{uid}_passive_context',
            'state_topic': f'voicebm/{room}/passive_context',
            'value_template': "{{ value_json.identity.display_name if value_json.identity else 'none' }}",
            'json_attributes_topic': f'voicebm/{room}/passive_context',
            'icon': 'mdi:account-eye',
            'device': device,
        }
        client.publish(
            f'{DISCOVERY_PREFIX}/sensor/voicebm_{uid}_passive_context/config',
            json.dumps(config),
            qos=1,
            retain=True,
        )

    print(f'[ambient-hooks] passive context discovery published ({len(sources)} rooms)')


def run_passive_context(client, source, state, prob, wav_path):
    """
    Fire-and-forget passive context resolution for one ambient speech event.

    Copies the WAV synchronously (the ambient tmp WAV is overwritten next
    cycle), then resolves identity + emote in a daemon thread and publishes
    the combined payload. Non-blocking — ambient loop is never held up.

    One job at a time: if a previous context job is still running, this
    event is skipped.
    """
    if not identity_available():
        return

    if not _inflight.acquire(blocking=False):
        print('[ambient-hooks] context job in flight — skipping event')
        return

    # Snapshot the WAV before the ambient loop can overwrite it
    try:
        fd, wav_copy = tempfile.mkstemp(suffix='.wav')
        os.close(fd)
        shutil.copy2(wav_path, wav_copy)
    except Exception as e:
        print(f'[ambient-hooks] WAV snapshot failed: {e}')
        _inflight.release()
        return

    room        = source['room']
    source_name = source['name']
    ts          = time.strftime('%Y-%m-%dT%H:%M:%SZ')

    def _job():
        try:
            identity = _resolve_identity(wav_copy)
            if identity is None:
                print('[ambient-hooks] identity unresolved — no publish')
                return

            payload = {
                'ts':     ts,
                'room':   room,
                'source': source_name,
                'speech': {'state': state, 'prob': prob},
                'identity': identity,
            }

            if emote_available():
                emote = _resolve_emote(wav_copy)
                if emote is not None:
                    payload['emote'] = emote

            client.publish(
                f'voicebm/{room}/passive_context',
                json.dumps(payload),
                qos=1,
                retain=True,
            )
            print(f'[ambient-hooks] context: {room} -> '
                  f'{identity["display_name"]} ({identity["decision"]}, '
                  f'{identity["confidence"]:.4f})'
                  + (f' emote={payload["emote"]["state"]}' if 'emote' in payload else ''))

        except Exception as e:
            print(f'[ambient-hooks] context job failed: {e}')
        finally:
            try:
                os.unlink(wav_copy)
            except OSError:
                pass
            _inflight.release()

    threading.Thread(target=_job, daemon=True).start()
```


## 15. `setup_ambient.py` <a id="15-setup-ambientpy"></a>

_VoiceBM Ambient Edition — Interactive Setup_

```python
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
```


# Thing Engine — post-enrollment identity management


## 16. `thing_engine.py` <a id="16-thing-enginepy"></a>

_VoiceBM Thing Engine - Identity Transformation & Merging_

```python
#!/usr/bin/env python3
"""
VoiceBM Thing Engine - Identity Transformation & Merging
Handles permanent identity operations: rename (transform) and merge

LLM Voice Biometrics by David M. Dryver Sr.
"""

import os
import sys
import json
import time
import shutil
import datetime
import subprocess
import zipfile
from pathlib import Path
import paho.mqtt.client as mqtt
import re

# Load configuration
sys.path.insert(0, '/home/user/voicebm')
from voicebm_config import get_mqtt_config

# ============================================================================
# CONFIGURATION
# ============================================================================

VOICEBM_BASE = Path("/home/user/voicebm")
ENROLL_DIR = VOICEBM_BASE / "enroll"
LOGS_DIR = VOICEBM_BASE / "logs"
THING_LOG = LOGS_DIR / "thing_engine.log"

# Load MQTT config dynamically
mqtt_config = get_mqtt_config()
MQTT_BROKER = mqtt_config['broker']
MQTT_PORT = mqtt_config['port']

# MQTT Topics
TOPIC_TRANSFORM = "voicebm/thing/transform"
TOPIC_MERGE_EXECUTE = "voicebm/thing/merge/execute"
TOPIC_MERGE_TAG_PREFIX = "voicebm/thing/merge/tag"
TOPIC_MERGE_TAGGED_COUNT = "voicebm/thing/merge/tagged_count"
TOPIC_MERGE_STATUS = "voicebm/thing/merge/status"

# Discovery prefix
DISCOVERY_PREFIX = "homeassistant"

# First-run detection marker
DISCOVERY_INITIALIZED_FILE = VOICEBM_BASE / "meta" / "discovery_initialized_thing_engine"

# Global state for merge tagging
tagged_identities = set()

# Global state for text inputs
transform_names = {}  # person_id -> new_name
merge_name = ""  # Name for merged identity


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def is_first_run():
    """Check if this is the first time discovery has been published."""
    return not DISCOVERY_INITIALIZED_FILE.exists()


def mark_initialized():
    """Mark that discovery has been initialized."""
    DISCOVERY_INITIALIZED_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DISCOVERY_INITIALIZED_FILE, 'w') as f:
        f.write(time.strftime('%Y-%m-%d %H:%M:%S'))
    print("  Marked Thing Engine discovery as initialized")

def log_operation(operation: str, details: dict):
    """Log Thing Engine operations to file"""
    LOGS_DIR.mkdir(exist_ok=True)
    
    log_entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "operation": operation,
        **details
    }
    
    with open(THING_LOG, 'a') as f:
        f.write(json.dumps(log_entry) + "\n")
    
    print(f"[THING ENGINE] {operation}: {details}")


def normalize_person_id(name: str) -> str:
    """
    Normalize person name to person_id format.
    Same logic as enrollment_watcher and dashboard.
    """
    # Convert to lowercase
    normalized = name.lower()
    
    # Replace hyphens with underscores
    normalized = normalized.replace('-', '_')
    
    # Replace multiple spaces with single underscore
    normalized = re.sub(r'\s+', '_', normalized)
    
    # Collapse multiple underscores into single
    normalized = re.sub(r'_+', '_', normalized)
    
    # Strip leading/trailing underscores
    normalized = normalized.strip('_')
    
    return normalized


def validate_person_name(name: str) -> tuple[bool, str]:
    """
    Validate person name meets requirements.
    Returns (is_valid, error_message)
    """
    if not name:
        return False, "Name cannot be empty"
    
    if len(name) > 100:
        return False, "Name too long (max 100 characters)"
    
    # Must start and end with letter
    if not name[0].isalpha():
        return False, "Name must start with a letter"
    if not name[-1].isalpha():
        return False, "Name must end with a letter"
    
    # Check for invalid characters (allow letters, spaces, hyphens, underscores)
    if not re.match(r'^[A-Za-z][A-Za-z0-9\s\-_]*[A-Za-z]$', name):
        return False, "Name can only contain letters, spaces, hyphens, and underscores"
    
    return True, ""


def person_exists(person_id: str) -> bool:
    """Check if person directory exists"""
    return (ENROLL_DIR / person_id).exists()


def get_person_metadata(person_id: str) -> dict:
    """Load person metadata.json"""
    metadata_file = ENROLL_DIR / person_id / "metadata.json"
    if metadata_file.exists():
        with open(metadata_file, 'r') as f:
            return json.load(f)
    return {}


def update_person_metadata(person_id: str, metadata: dict):
    """Update person metadata.json"""
    metadata_file = ENROLL_DIR / person_id / "metadata.json"
    metadata_file.parent.mkdir(parents=True, exist_ok=True)
    with open(metadata_file, 'w') as f:
        json.dump(metadata, f, indent=2)


def restart_enrollment_watcher(client):
    """
    Restart enrollment_watcher service to force complete republish.
    
    enrollment_watcher now publishes ALL entities (Voice, Blocklist, Threshold, Delete, Thing Engine)
    so we just need to restart the service and it handles everything.
    """
    print("[THING ENGINE] Restarting enrollment_watcher service...")
    try:
        result = subprocess.run(
            ['systemctl', 'restart', 'voicebm-enrollment-watcher'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            print("[THING ENGINE] ✓ Successfully restarted enrollment_watcher service")
            time.sleep(3)  # Give it time to republish all devices
        else:
            print(f"[THING ENGINE] ⚠️  Warning: Failed to restart enrollment_watcher")
            print(f"[THING ENGINE] Error: {result.stderr}")
            print(f"[THING ENGINE] You may need to restart manually")
    except subprocess.TimeoutExpired:
        print(f"[THING ENGINE] ⚠️  Warning: Restart command timed out")
    except Exception as e:
        print(f"[THING ENGINE] ⚠️  Warning: Error restarting enrollment_watcher: {e}")


# ============================================================================
# TRANSFORM OPERATION (Rename Identity)
# ============================================================================

def transform_identity(client, old_person_id: str, new_display_name: str) -> tuple[bool, str]:
    """
    Transform (rename) a person's identity permanently.
    
    Steps:
    1. Validate inputs
    2. Normalize new person_id
    3. Rename directory
    4. Update metadata.json
    5. Trigger MQTT discovery republish
    6. Log operation
    
    Returns:
        (success, message)
    """
    print(f"\n[TRANSFORM] Renaming '{old_person_id}' to '{new_display_name}'")
    
    # Validate old person exists
    if not person_exists(old_person_id):
        error = f"Person '{old_person_id}' does not exist"
        log_operation("transform_failed", {
            "old_id": old_person_id,
            "new_name": new_display_name,
            "error": error
        })
        return False, error
    
    # Validate new name
    is_valid, error_msg = validate_person_name(new_display_name)
    if not is_valid:
        log_operation("transform_failed", {
            "old_id": old_person_id,
            "new_name": new_display_name,
            "error": error_msg
        })
        return False, error_msg
    
    # Normalize new person_id
    new_person_id = normalize_person_id(new_display_name)
    
    # Check if new person_id already exists (but allow same as old for display name changes)
    if new_person_id != old_person_id and person_exists(new_person_id):
        error = f"Person '{new_person_id}' already exists"
        log_operation("transform_failed", {
            "old_id": old_person_id,
            "new_id": new_person_id,
            "new_name": new_display_name,
            "error": error
        })
        return False, error
    
    try:
        old_dir = ENROLL_DIR / old_person_id
        
        # If only display name is changing (person_id stays same), just update metadata
        if old_person_id == new_person_id:
            print(f"  Display name only change: {old_person_id} -> {new_display_name}")
            metadata = get_person_metadata(old_person_id)
            metadata['display_name'] = new_display_name
            metadata['last_modified'] = datetime.datetime.now().isoformat()
            metadata['modified_by'] = 'thing_engine'
            update_person_metadata(old_person_id, metadata)
            
            # Restart enrollment_watcher to update HA device name
            restart_enrollment_watcher(client)
        else:
            # Full identity transformation with delete
            print(f"  Full identity transformation: {old_person_id} -> {new_person_id}")
            
            # 1. Update metadata.json IN PLACE (before zipping)
            print(f"  Updating metadata in source directory...")
            metadata = get_person_metadata(old_person_id)
            metadata['person_id'] = new_person_id
            metadata['display_name'] = new_display_name
            metadata['previous_id'] = old_person_id
            metadata['last_modified'] = datetime.datetime.now().isoformat()
            metadata['modified_by'] = 'thing_engine'
            update_person_metadata(old_person_id, metadata)
            
            # 2. Create zip backup with NEW name (metadata already correct inside)
            zip_path = ENROLL_DIR / f"{new_person_id}.zip"
            print(f"  Creating backup: {zip_path.name}")
            
            try:
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for item in old_dir.rglob('*'):
                        if item.is_file():
                            arcname = item.relative_to(old_dir)
                            zipf.write(item, arcname)
                
                # 3. Enable delete for old person_id
                print(f"  Enabling delete for: {old_person_id}")
                client.publish(
                    f"voicebm/identity/{old_person_id}/enable_delete/set",
                    "ON",
                    qos=1,
                    retain=False
                )
                time.sleep(0.5)
                
                # 4. Trigger delete
                print(f"  Deleting old identity: {old_person_id}")
                client.publish(
                    f"voicebm/identity/{old_person_id}/delete",
                    "PRESS",
                    qos=1,
                    retain=False
                )
                
                # 5. Wait and check metadata.json (more reliable than checking directory)
                print(f"  Waiting 3 seconds...")
                time.sleep(3)
                
                metadata_file = old_dir / "metadata.json"
                if metadata_file.exists():
                    print(f"  metadata.json still exists, waiting 5 more seconds...")
                    time.sleep(5)
                    # Trust it's gone after 8 seconds total
                    print(f"  Proceeding (trusting deletion completed)")
                else:
                    print(f"  Deletion confirmed (metadata.json gone)")
                
                # 6. Unzip directly to enroll directory (metadata already correct)
                new_dir = ENROLL_DIR / new_person_id
                print(f"  Extracting backup...")
                with zipfile.ZipFile(zip_path, 'r') as zipf:
                    zipf.extractall(new_dir)
                
            except Exception as e:
                # Backup preserved on failure
                if zip_path.exists():
                    print(f"  ERROR: Backup preserved at {zip_path}")
                raise e
            
            # 7. Restart enrollment_watcher (sees new directory, publishes all entities)
            restart_enrollment_watcher(client)
            
            # 8. Delete backup zip after successful completion
            if zip_path.exists():
                zip_path.unlink()
                print(f"  ✓ Cleaned up backup zip")
        
        # Log success
        log_operation("transform_success", {
            "old_id": old_person_id,
            "new_id": new_person_id,
            "new_display_name": new_display_name
        })
        
        print(f"  ✓ Transform complete: {old_person_id} -> {new_person_id}")
        return True, f"Successfully renamed to '{new_display_name}'"
    
    except Exception as e:
        error = f"Transform failed: {str(e)}"
        log_operation("transform_error", {
            "old_id": old_person_id,
            "new_name": new_display_name,
            "error": str(e)
        })
        return False, error


# ============================================================================
# MERGE OPERATION (Combine Identities)
# ============================================================================

def merge_identities(client, source_ids: list, new_display_name: str) -> tuple[bool, str]:
    """
    Merge multiple identities into one new identity.
    
    Steps:
    1. Validate inputs
    2. Create new identity directory
    3. Copy all embeddings from source identities
    4. Copy all audio files from source identities
    5. Delete source identity directories
    6. Trigger MQTT discovery republish
    7. Log operation
    
    Returns:
        (success, message)
    """
    print(f"\n[MERGE] Combining {len(source_ids)} identities into '{new_display_name}'")
    print(f"  Sources: {', '.join(source_ids)}")
    
    # Validate at least 2 sources
    if len(source_ids) < 2:
        error = "Must select at least 2 identities to merge"
        log_operation("merge_failed", {
            "sources": source_ids,
            "new_name": new_display_name,
            "error": error
        })
        return False, error
    
    # Validate all sources exist
    for source_id in source_ids:
        if not person_exists(source_id):
            error = f"Source identity '{source_id}' does not exist"
            log_operation("merge_failed", {
                "sources": source_ids,
                "new_name": new_display_name,
                "error": error
            })
            return False, error
    
    # Validate new name
    is_valid, error_msg = validate_person_name(new_display_name)
    if not is_valid:
        log_operation("merge_failed", {
            "sources": source_ids,
            "new_name": new_display_name,
            "error": error_msg
        })
        return False, error_msg
    
    # Normalize new person_id
    new_person_id = normalize_person_id(new_display_name)
    
    # Check if new person_id already exists
    if person_exists(new_person_id):
        error = f"Person '{new_person_id}' already exists"
        log_operation("merge_failed", {
            "sources": source_ids,
            "new_id": new_person_id,
            "new_name": new_display_name,
            "error": error
        })
        return False, error
    
    try:
        # Create new identity directory structure
        new_dir = ENROLL_DIR / new_person_id
        new_dir.mkdir(parents=True, exist_ok=True)
        embeddings_dir = new_dir / "embeddings"
        embeddings_dir.mkdir(exist_ok=True)
        
        # Create metadata for merged identity
        metadata = {
            "person_id": new_person_id,
            "display_name": new_display_name,
            "created": datetime.datetime.now().isoformat(),
            "source": "thing_engine_merge",
            "merged_from": source_ids,
            "blocked": False
        }
        update_person_metadata(new_person_id, metadata)
        
        # Copy embeddings and audio from all sources
        total_embeddings = 0
        total_audio = 0
        
        for source_id in source_ids:
            source_dir = ENROLL_DIR / source_id
            
            # Copy embeddings
            source_embeddings = source_dir / "embeddings"
            if source_embeddings.exists():
                for emb_file in source_embeddings.glob("*.txt"):
                    # Rename to new person_id
                    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
                    new_filename = f"{new_person_id}_{timestamp}_{total_embeddings}.txt"
                    shutil.copy2(emb_file, embeddings_dir / new_filename)
                    total_embeddings += 1
            
            # Copy audio files
            for audio_file in source_dir.glob("*.wav"):
                timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
                new_filename = f"{new_person_id}_{timestamp}_{total_audio}.wav"
                shutil.copy2(audio_file, new_dir / new_filename)
                total_audio += 1
        
        print(f"  Copied {total_embeddings} embeddings, {total_audio} audio files")
        
        # Delete source identities via MQTT (two-step safety)
        for source_id in source_ids:
            print(f"  Deleting source: {source_id}")
            
            # Enable delete
            client.publish(
                f"voicebm/identity/{source_id}/enable_delete/set",
                "ON",
                qos=1,
                retain=False
            )
            time.sleep(0.5)
            
            # Trigger delete
            client.publish(
                f"voicebm/identity/{source_id}/delete",
                "PRESS",
                qos=1,
                retain=False
            )
            
            # Wait and check metadata.json (same logic as transform)
            print(f"  Waiting 3 seconds...")
            time.sleep(3)
            
            source_dir = ENROLL_DIR / source_id
            metadata_file = source_dir / "metadata.json"
            if metadata_file.exists():
                print(f"  metadata.json still exists for {source_id}, waiting 5 more seconds...")
                time.sleep(5)
                print(f"  Proceeding (trusting deletion completed)")
            else:
                print(f"  Deletion confirmed for {source_id}")
        
        # Restart enrollment_watcher (sees new merged identity, publishes all entities)
        restart_enrollment_watcher(client)
        
        # Log success
        log_operation("merge_success", {
            "sources": source_ids,
            "new_id": new_person_id,
            "new_display_name": new_display_name,
            "embeddings_count": total_embeddings,
            "audio_count": total_audio
        })
        
        print(f"  ✓ Merge complete: {new_person_id} created from {len(source_ids)} sources")
        return True, f"Successfully merged into '{new_display_name}' ({total_embeddings} samples)"
    
    except Exception as e:
        error = f"Merge failed: {str(e)}"
        log_operation("merge_error", {
            "sources": source_ids,
            "new_name": new_display_name,
            "error": str(e)
        })
        return False, error


# ============================================================================
# MQTT HANDLERS
# ============================================================================

def handle_transform_name_input(client, userdata, msg):
    """
    Handle transform name text input changes.
    Stores the new name for when button is pressed.
    """
    global transform_names
    
    try:
        # Extract person_id from topic: voicebm/thing/transform/{person_id}/name/set
        parts = msg.topic.split('/')
        person_id = parts[3]
        new_name = msg.payload.decode('utf-8').strip()
        
        transform_names[person_id] = new_name
        
        # Echo back to state topic
        client.publish(f"voicebm/thing/transform/{person_id}/name", new_name, qos=1, retain=True)
        print(f"[TRANSFORM NAME] {person_id} -> {new_name}")
        
    except Exception as e:
        print(f"[TRANSFORM NAME] Error: {e}")


def handle_transform_execute(client, userdata, msg):
    """
    Handle transform execute button press.
    Uses stored name from text input.
    """
    global transform_names
    
    try:
        # Extract person_id from topic: voicebm/thing/transform/{person_id}/execute
        parts = msg.topic.split('/')
        person_id = parts[3]
        
        # Get stored new name
        new_display_name = transform_names.get(person_id, "").strip()
        
        if not new_display_name:
            print(f"[TRANSFORM] No name set for {person_id}")
            status = {
                "operation": "transform",
                "success": False,
                "message": "Please enter a new name first",
                "timestamp": datetime.datetime.now().isoformat()
            }
            client.publish(TOPIC_MERGE_STATUS, json.dumps(status), qos=1, retain=True)
            return
        
        success, message = transform_identity(client, person_id, new_display_name)
        
        # Clear stored name on success
        if success:
            transform_names.pop(person_id, None)
            client.publish(f"voicebm/thing/transform/{person_id}/name", "", qos=1, retain=True)
        
        # Publish status
        status = {
            "operation": "transform",
            "person": person_id,
            "success": success,
            "message": message,
            "timestamp": datetime.datetime.now().isoformat()
        }
        client.publish(TOPIC_MERGE_STATUS, json.dumps(status), qos=1, retain=True)
        
    except Exception as e:
        print(f"[TRANSFORM EXECUTE] Error: {e}")


def handle_merge_tag(client, userdata, msg):
    """
    Handle merge tag switch changes.
    Tracks which identities are tagged for merging.
    """
    global tagged_identities
    
    try:
        # Extract person_id from topic: voicebm/thing/merge/tag/{person_id}/set
        parts = msg.topic.split('/')
        person_id = parts[-2]  # Second to last element
        state = msg.payload.decode('utf-8').upper()
        
        if state == "ON":
            tagged_identities.add(person_id)
            print(f"[MERGE TAG] Added: {person_id} (total: {len(tagged_identities)})")
        elif state == "OFF":
            tagged_identities.discard(person_id)
            print(f"[MERGE TAG] Removed: {person_id} (total: {len(tagged_identities)})")
        
        # Echo back to state topic
        client.publish(f"voicebm/thing/merge/tag/{person_id}", state, qos=1, retain=True)
        
        # Publish updated count
        client.publish(TOPIC_MERGE_TAGGED_COUNT, str(len(tagged_identities)), qos=1, retain=True)
        
    except Exception as e:
        print(f"[MERGE TAG] Error: {e}")


def handle_merge_name_input(client, userdata, msg):
    """
    Handle merge name text input changes.
    Stores the name for when merge button is pressed.
    """
    global merge_name
    
    try:
        merge_name = msg.payload.decode('utf-8').strip()
        
        # Echo back to state topic
        client.publish("voicebm/thing/merge/name", merge_name, qos=1, retain=True)
        print(f"[MERGE NAME] Set to: {merge_name}")
        
    except Exception as e:
        print(f"[MERGE NAME] Error: {e}")


def handle_merge_execute(client, userdata, msg):
    """
    Handle merge execution button press.
    Uses globally tracked tagged_identities and merge_name.
    """
    global tagged_identities, merge_name
    
    try:
        if not merge_name.strip():
            print("[MERGE] No name set for merged identity")
            status = {
                "operation": "merge",
                "success": False,
                "message": "Please enter a name for the merged identity",
                "timestamp": datetime.datetime.now().isoformat()
            }
            client.publish(TOPIC_MERGE_STATUS, json.dumps(status), qos=1, retain=True)
            return
        
        if len(tagged_identities) < 2:
            print("[MERGE] Not enough identities tagged (need at least 2)")
            status = {
                "operation": "merge",
                "success": False,
                "message": f"Need at least 2 identities tagged (currently {len(tagged_identities)})",
                "timestamp": datetime.datetime.now().isoformat()
            }
            client.publish(TOPIC_MERGE_STATUS, json.dumps(status), qos=1, retain=True)
            return
        
        # Convert set to list for merge
        source_ids = list(tagged_identities)
        
        success, message = merge_identities(client, source_ids, merge_name)
        
        # Clear tagged identities and merge name on success
        if success:
            tagged_identities.clear()
            merge_name = ""
            client.publish(TOPIC_MERGE_TAGGED_COUNT, "0", qos=1, retain=True)
            client.publish("voicebm/thing/merge/name", "", qos=1, retain=True)
            
            # Clear all tag switches
            for person_id in source_ids:
                client.publish(f"voicebm/thing/merge/tag/{person_id}", "OFF", qos=1, retain=True)
        
        # Publish status
        status = {
            "operation": "merge",
            "success": success,
            "message": message,
            "sources": source_ids,
            "timestamp": datetime.datetime.now().isoformat()
        }
        client.publish(TOPIC_MERGE_STATUS, json.dumps(status), qos=1, retain=True)
        
    except Exception as e:
        print(f"[MERGE] Error: {e}")


def remove_person_thing_entities(client, person_id: str):
    """
    Remove Thing Engine entities for a person by publishing empty config.
    Called before transform to clean up old person_id's entities.
    """
    # Remove transform text input
    client.publish(
        f"{DISCOVERY_PREFIX}/text/{person_id}_transform_name/config",
        "",
        qos=1,
        retain=True
    )
    
    # Remove transform button
    client.publish(
        f"{DISCOVERY_PREFIX}/button/{person_id}_transform_execute/config",
        "",
        qos=1,
        retain=True
    )
    
    # Remove merge tag switch
    client.publish(
        f"{DISCOVERY_PREFIX}/switch/{person_id}_merge_tag/config",
        "",
        qos=1,
        retain=True
    )
    
    print(f"[THING ENGINE] Removed Thing Engine entities for: {person_id}")


def publish_person_thing_entities(client, person_id: str, display_name: str):
    """
    Publish Thing Engine entities for a specific person.
    Called when enrollment is refreshed.
    """
    device = {
        "identifiers": [person_id],
        "name": display_name,
        "manufacturer": "VoiceBM by David M. Dryver Sr.",
        "model": "Person"
    }
    
    # Transform Name Text Input
    transform_name_config = {
        "name": "New Identity Name",
        "unique_id": f"{person_id}_transform_name",
        "command_topic": f"voicebm/thing/transform/{person_id}/name/set",
        "state_topic": f"voicebm/thing/transform/{person_id}/name",
        "mode": "text",
        "icon": "mdi:rename-box",
        "device": device
    }
    client.publish(
        f"{DISCOVERY_PREFIX}/text/{person_id}_transform_name/config",
        json.dumps(transform_name_config),
        qos=1,
        retain=True
    )
    
    # Transform Execute Button
    transform_button_config = {
        "name": "Rename Identity",
        "unique_id": f"{person_id}_transform_execute",
        "command_topic": f"voicebm/thing/transform/{person_id}/execute",
        "payload_press": "PRESS",
        "icon": "mdi:account-convert",
        "device": device
    }
    client.publish(
        f"{DISCOVERY_PREFIX}/button/{person_id}_transform_execute/config",
        json.dumps(transform_button_config),
        qos=1,
        retain=True
    )
    
    # Merge Tag Switch
    merge_tag_config = {
        "name": "Tag for Merge",
        "unique_id": f"{person_id}_merge_tag",
        "command_topic": f"voicebm/thing/merge/tag/{person_id}/set",
        "state_topic": f"voicebm/thing/merge/tag/{person_id}",
        "payload_on": "ON",
        "payload_off": "OFF",
        "icon": "mdi:tag-multiple",
        "device": device
    }
    client.publish(
        f"{DISCOVERY_PREFIX}/switch/{person_id}_merge_tag/config",
        json.dumps(merge_tag_config),
        qos=1,
        retain=True
    )
    
    # Publish initial states for new entities
    client.publish(f"voicebm/thing/transform/{person_id}/name", "", qos=1, retain=True)
    client.publish(f"voicebm/thing/merge/tag/{person_id}", "OFF", qos=1, retain=True)


def scan_and_publish_person_entities(client):
    """
    Scan enrollment directory and publish Thing Engine entities for all persons.
    Thing Engine adds transform/merge controls to person devices created by enrollment_watcher.
    """
    if not ENROLL_DIR.exists():
        print(f"[THING ENGINE] Enrollment directory not found: {ENROLL_DIR}")
        return
    
    person_count = 0
    
    for person_dir in ENROLL_DIR.iterdir():
        if not person_dir.is_dir():
            continue
        
        person_id = person_dir.name
        
        # Load display name from metadata
        metadata_file = person_dir / "metadata.json"
        display_name = person_id
        if metadata_file.exists():
            try:
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
                    display_name = metadata.get('display_name', person_id)
            except:
                pass
        
        publish_person_thing_entities(client, person_id, display_name)
        person_count += 1
    
    print(f"[THING ENGINE] Published entities for {person_count} persons")


def publish_discovery(client):
    """Publish Home Assistant MQTT Discovery for Thing Engine system entities."""
    device = {
        "identifiers": ["voicebm_thing_engine"],
        "name": "VoiceBM Thing Engine",
        "model": "Identity Transformation & Merge",
        "manufacturer": "VoiceBM by David M. Dryver Sr."
    }
    
    # Merge Tagged Count Sensor
    tagged_count_config = {
        "name": "Merge Tagged Count",
        "unique_id": "voicebm_thing_tagged_count",
        "state_topic": "voicebm/thing/merge/tagged_count",
        "icon": "mdi:counter",
        "device": device
    }
    client.publish(
        f"{DISCOVERY_PREFIX}/sensor/voicebm_thing_tagged_count/config",
        json.dumps(tagged_count_config),
        qos=1,
        retain=True
    )
    
    # Merge Status Sensor
    status_config = {
        "name": "Thing Engine Status",
        "unique_id": "voicebm_thing_status",
        "state_topic": "voicebm/thing/merge/status",
        "value_template": "{{ value_json.message | default('Ready') }}",
        "json_attributes_topic": "voicebm/thing/merge/status",
        "icon": "mdi:state-machine",
        "device": device
    }
    client.publish(
        f"{DISCOVERY_PREFIX}/sensor/voicebm_thing_status/config",
        json.dumps(status_config),
        qos=1,
        retain=True
    )
    
    # Merge Name Text Input
    merge_name_config = {
        "name": "New Merged Identity Name",
        "unique_id": "voicebm_thing_merge_name",
        "command_topic": "voicebm/thing/merge/name/set",
        "state_topic": "voicebm/thing/merge/name",
        "mode": "text",
        "icon": "mdi:form-textbox",
        "device": device
    }
    client.publish(
        f"{DISCOVERY_PREFIX}/text/voicebm_thing_merge_name/config",
        json.dumps(merge_name_config),
        qos=1,
        retain=True
    )
    
    # Merge Execute Button
    merge_button_config = {
        "name": "Execute Merge",
        "unique_id": "voicebm_thing_merge_execute",
        "command_topic": "voicebm/thing/merge/execute/trigger",
        "payload_press": "PRESS",
        "icon": "mdi:merge",
        "device": device
    }
    client.publish(
        f"{DISCOVERY_PREFIX}/button/voicebm_thing_merge_execute/config",
        json.dumps(merge_button_config),
        qos=1,
        retain=True
    )
    
    print("[THING ENGINE] Published system entity discovery configs")


def on_connect(client, userdata, flags, reason_code, properties):
    """MQTT connection callback"""
    if reason_code == 0:
        print("[THING ENGINE] Connected to MQTT broker")
        
        # Publish discovery first
        publish_discovery(client)
        
        # Subscribe to command topics
        client.subscribe("voicebm/thing/transform/+/name/set")  # Per-person name input
        client.subscribe("voicebm/thing/transform/+/execute")  # Per-person transform button
        client.subscribe("voicebm/thing/merge/name/set")  # Merge name input
        client.subscribe("voicebm/thing/merge/execute/trigger")  # Merge button
        client.subscribe(f"{TOPIC_MERGE_TAG_PREFIX}/+/set")  # Tag switches
        
        # Check if this is first run
        first_run = is_first_run()
        
        if first_run:
            print("[THING ENGINE] First run detected - will publish initial states")
        else:
            print("[THING ENGINE] Subsequent run - respecting HA state")
        
        # ONLY publish initial state on first run
        # Subsequent runs preserve HA's retained state
        if first_run:
            client.publish(TOPIC_MERGE_TAGGED_COUNT, "0", qos=1, retain=True)
            client.publish("voicebm/thing/merge/name", "", qos=1, retain=True)
            client.publish(TOPIC_MERGE_STATUS, json.dumps({
                "status": "ready",
                "message": "Ready",
                "timestamp": datetime.datetime.now().isoformat()
            }), qos=1, retain=True)
            print("[THING ENGINE] Published initial states")
            mark_initialized()
        
        # Scan and publish Thing Engine entities for all persons
        # This adds transform/merge controls to devices created by enrollment_watcher
        scan_and_publish_person_entities(client)
        
        print("[THING ENGINE] Subscriptions active")
        print("  - Transform name inputs: voicebm/thing/transform/+/name/set")
        print("  - Transform buttons: voicebm/thing/transform/+/execute")
        print("  - Merge name input: voicebm/thing/merge/name/set")
        print("  - Merge button: voicebm/thing/merge/execute/trigger")
        print("  - Tag switches: voicebm/thing/merge/tag/+/set")
    else:
        print(f"[THING ENGINE] Connection failed with reason code {reason_code}")


def on_message(client, userdata, msg):
    """MQTT message router"""
    try:
        topic = msg.topic
        
        if topic.startswith("voicebm/thing/transform/") and topic.endswith("/name/set"):
            handle_transform_name_input(client, userdata, msg)
        elif topic.startswith("voicebm/thing/transform/") and topic.endswith("/execute"):
            handle_transform_execute(client, userdata, msg)
        elif topic == "voicebm/thing/merge/name/set":
            handle_merge_name_input(client, userdata, msg)
        elif topic == "voicebm/thing/merge/execute/trigger":
            handle_merge_execute(client, userdata, msg)
        elif topic.startswith(TOPIC_MERGE_TAG_PREFIX) and topic.endswith("/set"):
            handle_merge_tag(client, userdata, msg)
    except Exception as e:
        print(f"[THING ENGINE] Message handler error: {e}")


# ============================================================================
# MAIN
# ============================================================================

def main():
    """Main Thing Engine service loop"""
    print("=" * 70)
    print("VoiceBM Thing Engine - Identity Transformation & Merging")
    print("LLM Voice Biometrics by David M. Dryver Sr.")
    print("=" * 70)
    print(f"Enrollment directory: {ENROLL_DIR}")
    print(f"Logs directory: {LOGS_DIR}")
    print(f"MQTT Broker: {MQTT_BROKER}:{MQTT_PORT}")
    print()
    
    # Ensure directories exist
    ENROLL_DIR.mkdir(exist_ok=True)
    LOGS_DIR.mkdir(exist_ok=True)
    
    # Setup MQTT client
    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    if mqtt_config.get('user') and mqtt_config.get('password'):
        client.username_pw_set(mqtt_config['user'], mqtt_config['password'])
    client.on_connect = on_connect
    client.on_message = on_message
    
    print(f"Connecting to MQTT broker at {MQTT_BROKER}:{MQTT_PORT}...")
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    
    print("Thing Engine running. Press Ctrl+C to stop.")
    print()
    
    # Start MQTT loop
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print("\n[THING ENGINE] Shutting down...")
        client.disconnect()


if __name__ == "__main__":
    main()
```


## 17. `thing_discovery.py` <a id="17-thing-discoverypy"></a>

_Thing Engine MQTT Discovery Publisher_

```python
#!/usr/bin/env python3
"""
Thing Engine MQTT Discovery Publisher
Creates HA entities for identity transformation and merging

LLM Voice Biometrics by David M. Dryver Sr.
"""

import sys
import json
import time
import paho.mqtt.client as mqtt
from pathlib import Path

# Load configuration
sys.path.insert(0, '/home/user/voicebm')
from voicebm_config import get_mqtt_config

VOICEBM_BASE = Path("/home/user/voicebm")
ENROLL_DIR = VOICEBM_BASE / "enroll"

# Load MQTT config dynamically
mqtt_config = get_mqtt_config()
MQTT_BROKER = mqtt_config['broker']
MQTT_PORT = mqtt_config['port']

DISCOVERY_PREFIX = "homeassistant"


def publish_system_entities(client):
    """
    Publish Thing Engine system device entities.
    These handle merge operations.
    """
    device = {
        "identifiers": ["voicebm_thing_engine"],
        "name": "VoiceBM Thing Engine",
        "model": "Identity Transformation & Merge",
        "manufacturer": "VoiceBM by David M. Dryver Sr."
    }
    
    # Merge Tagged Count Sensor
    tagged_count_config = {
        "name": "Merge Tagged Count",
        "unique_id": "voicebm_thing_tagged_count",
        "state_topic": "voicebm/thing/merge/tagged_count",
        "icon": "mdi:counter",
        "device": device
    }
    client.publish(
        f"{DISCOVERY_PREFIX}/sensor/voicebm_thing_tagged_count/config",
        json.dumps(tagged_count_config),
        qos=1,
        retain=True
    )
    
    # Merge Status Sensor
    status_config = {
        "name": "Thing Engine Status",
        "unique_id": "voicebm_thing_status",
        "state_topic": "voicebm/thing/merge/status",
        "value_template": "{{ value_json.message | default('Ready') }}",
        "json_attributes_topic": "voicebm/thing/merge/status",
        "icon": "mdi:state-machine",
        "device": device
    }
    client.publish(
        f"{DISCOVERY_PREFIX}/sensor/voicebm_thing_status/config",
        json.dumps(status_config),
        qos=1,
        retain=True
    )
    
    # Merge Name Text Input
    merge_name_config = {
        "name": "New Merged Identity Name",
        "unique_id": "voicebm_thing_merge_name",
        "command_topic": "voicebm/thing/merge/name/set",
        "state_topic": "voicebm/thing/merge/name",
        "mode": "text",
        "icon": "mdi:form-textbox",
        "device": device
    }
    client.publish(
        f"{DISCOVERY_PREFIX}/text/voicebm_thing_merge_name/config",
        json.dumps(merge_name_config),
        qos=1,
        retain=True
    )
    
    # Merge Execute Button
    merge_button_config = {
        "name": "Execute Merge",
        "unique_id": "voicebm_thing_merge_execute",
        "command_topic": "voicebm/thing/merge/execute/trigger",
        "payload_press": "PRESS",
        "icon": "mdi:merge",
        "device": device
    }
    client.publish(
        f"{DISCOVERY_PREFIX}/button/voicebm_thing_merge_execute/config",
        json.dumps(merge_button_config),
        qos=1,
        retain=True
    )
    
    print("✓ Thing Engine system entities published")


def publish_person_entities(client, person_id: str, display_name: str):
    """
    Publish Thing Engine entities for a specific person.
    Adds transform and merge tag controls.
    """
    device = {
        "identifiers": [f"voicebm_person_{person_id}"],
        "name": display_name,
        "via_device": "voicebm",
        "manufacturer": "VoiceBM by David M. Dryver Sr."
    }
    
    # Transform Name Text Input
    transform_name_config = {
        "name": "New Identity Name",
        "unique_id": f"{person_id}_transform_name",
        "command_topic": f"voicebm/thing/transform/{person_id}/name/set",
        "state_topic": f"voicebm/thing/transform/{person_id}/name",
        "mode": "text",
        "icon": "mdi:rename-box",
        "device": device
    }
    client.publish(
        f"{DISCOVERY_PREFIX}/text/{person_id}_transform_name/config",
        json.dumps(transform_name_config),
        qos=1,
        retain=True
    )
    
    # Transform Execute Button
    transform_button_config = {
        "name": "Rename Identity",
        "unique_id": f"{person_id}_transform_execute",
        "command_topic": f"voicebm/thing/transform/{person_id}/execute",
        "payload_press": "PRESS",
        "icon": "mdi:account-convert",
        "device": device
    }
    client.publish(
        f"{DISCOVERY_PREFIX}/button/{person_id}_transform_execute/config",
        json.dumps(transform_button_config),
        qos=1,
        retain=True
    )
    
    # Merge Tag Switch
    merge_tag_config = {
        "name": "Tag for Merge",
        "unique_id": f"{person_id}_merge_tag",
        "command_topic": f"voicebm/thing/merge/tag/{person_id}/set",
        "state_topic": f"voicebm/thing/merge/tag/{person_id}",
        "payload_on": "ON",
        "payload_off": "OFF",
        "icon": "mdi:tag-multiple",
        "device": device
    }
    client.publish(
        f"{DISCOVERY_PREFIX}/switch/{person_id}_merge_tag/config",
        json.dumps(merge_tag_config),
        qos=1,
        retain=True
    )
    
    # Initialize states
    client.publish(f"voicebm/thing/transform/{person_id}/name", "", qos=1, retain=True)
    client.publish(f"voicebm/thing/merge/tag/{person_id}", "OFF", qos=1, retain=True)


def scan_and_publish_all(client):
    """Scan enrollment directory and publish entities for all persons"""
    if not ENROLL_DIR.exists():
        print(f"Enrollment directory not found: {ENROLL_DIR}")
        return
    
    person_count = 0
    
    for person_dir in ENROLL_DIR.iterdir():
        if not person_dir.is_dir():
            continue
        
        person_id = person_dir.name
        
        # Load display name from metadata
        metadata_file = person_dir / "metadata.json"
        display_name = person_id
        if metadata_file.exists():
            try:
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
                    display_name = metadata.get('display_name', person_id)
            except:
                pass
        
        publish_person_entities(client, person_id, display_name)
        person_count += 1
        print(f"✓ Published Thing Engine entities for: {display_name}")
    
    print(f"\nTotal: {person_count} persons")


def on_connect(client, userdata, flags, reason_code, properties):
    """MQTT connection callback"""
    if reason_code == 0:
        print("Connected to MQTT broker\n")
        
        # Publish system entities
        print("Publishing Thing Engine system entities...")
        publish_system_entities(client)
        
        # Publish per-person entities
        print("\nPublishing per-person Thing Engine entities...")
        scan_and_publish_all(client)
        
        print("\n" + "=" * 70)
        print("Thing Engine MQTT discovery complete!")
        print("=" * 70)
        
        client.disconnect()
    else:
        print(f"Connection failed with reason code {reason_code}")


def main():
    """Publish Thing Engine MQTT discovery"""
    print("=" * 70)
    print("Thing Engine MQTT Discovery Publisher")
    print("LLM Voice Biometrics by David M. Dryver Sr.")
    print("=" * 70)
    print()
    
    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    if mqtt_config.get('user') and mqtt_config.get('password'):
        client.username_pw_set(mqtt_config['user'], mqtt_config['password'])
    client.on_connect = on_connect
    
    print(f"Connecting to MQTT broker at {MQTT_BROKER}:{MQTT_PORT}...")
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    
    client.loop_forever()


if __name__ == "__main__":
    main()
```


# Node management


## 18. `node_engine.py` <a id="18-node-enginepy"></a>

_VoiceBM Node Engine - Node Identity Transformation_

```python
#!/usr/bin/env python3
"""
VoiceBM Node Engine - Node Identity Transformation
Renames a node's friendly_name (mutable display context) while node_id
(the immutable identity) never changes.

node_id is the node's biology: it lives in topics, directories, and device
identifiers, and never changes. friendly_name is display context for HA and
the LLM. This engine mutates ONLY friendly_name in config.json, then
delegates republish to the services that own the node's entities.

LLM Voice Biometrics by David M. Dryver Sr.
"""

import sys
import json
import time
import datetime
import subprocess
import re
from pathlib import Path
import paho.mqtt.client as mqtt

# Load configuration
sys.path.insert(0, '/home/user/voicebm')
from voicebm_config import get_mqtt_config

# ============================================================================
# CONFIGURATION
# ============================================================================

VOICEBM_BASE = Path("/home/user/voicebm")
CONFIG_FILE = VOICEBM_BASE / "config.json"
LOGS_DIR = VOICEBM_BASE / "logs"
NODE_LOG = LOGS_DIR / "node_engine.log"

mqtt_config = get_mqtt_config()
MQTT_BROKER = mqtt_config['broker']
MQTT_PORT = mqtt_config['port']

# MQTT Topics
TOPIC_TRANSFORM_PREFIX = "voicebm/node/transform"      # .../{node_id}/name(/set), .../{node_id}/execute
TOPIC_STATUS = "voicebm/node/transform/status"          # retained JSON status (MQTT topic, no HA sensor)

DISCOVERY_PREFIX = "homeassistant"

# First-run detection marker
DISCOVERY_INITIALIZED_FILE = VOICEBM_BASE / "meta" / "discovery_initialized_node_engine"

# Staged names: node_id -> new friendly_name (set by text input, used by button)
transform_names = {}


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def is_first_run():
    """Check if this is the first time discovery has been published."""
    return not DISCOVERY_INITIALIZED_FILE.exists()


def mark_initialized():
    """Mark that discovery has been initialized."""
    DISCOVERY_INITIALIZED_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DISCOVERY_INITIALIZED_FILE, 'w') as f:
        f.write(time.strftime('%Y-%m-%d %H:%M:%S'))
    print("  Marked Node Engine discovery as initialized")


def log_operation(operation: str, details: dict):
    """Log Node Engine operations to file"""
    LOGS_DIR.mkdir(exist_ok=True)

    log_entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "operation": operation,
        **details
    }

    with open(NODE_LOG, 'a') as f:
        f.write(json.dumps(log_entry) + "\n")

    print(f"[NODE ENGINE] {operation}: {details}")


def validate_friendly_name(name: str) -> tuple[bool, str]:
    """
    Validate a friendly name. Same grammar as the Thing Engine's validator:
    letters, digits, spaces, hyphens, underscores; starts and ends with a letter.
    """
    if not name:
        return False, "Name cannot be empty"

    if len(name) > 100:
        return False, "Name too long (max 100 characters)"

    if not name[0].isalpha():
        return False, "Name must start with a letter"
    if not name[-1].isalpha():
        return False, "Name must end with a letter"

    if not re.match(r'^[A-Za-z][A-Za-z0-9\s\-_]*[A-Za-z]$', name):
        return False, "Name can only contain letters, digits, spaces, hyphens, and underscores"

    return True, ""


def load_config() -> dict:
    """Load config.json (single source of truth)."""
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)


def write_config_atomic(cfg: dict):
    """
    Atomic config.json write: temp file in the same directory, then replace.
    A crash mid-write can never leave a truncated config behind.
    """
    tmp = CONFIG_FILE.with_suffix('.json.tmp')
    with open(tmp, 'w') as f:
        json.dump(cfg, f, indent=2)
        f.write('\n')
    tmp.replace(CONFIG_FILE)


def get_nodes() -> dict:
    """nodes block from config.json: node_id -> node settings."""
    try:
        return load_config().get('nodes', {}) or {}
    except Exception as e:
        print(f"[NODE ENGINE] Failed to read config.json: {e}")
        return {}


def node_friendly(node: dict, node_id: str) -> str:
    """Display name for a node, with the same fallback the publishers use."""
    return node.get('friendly_name', node_id.replace('_', ' ').title())


def restart_service(unit: str) -> bool:
    """
    Restart one systemd unit so it republishes discovery with the new name.
    Same delegation pattern (and tolerance) as the Thing Engine's
    enrollment_watcher restart.
    """
    try:
        result = subprocess.run(
            ['systemctl', 'restart', unit],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            print(f"[NODE ENGINE] ✓ Restarted {unit}")
            return True
        print(f"[NODE ENGINE] ⚠️  Failed to restart {unit}: {result.stderr.strip()}")
        return False
    except subprocess.TimeoutExpired:
        print(f"[NODE ENGINE] ⚠️  Restart timed out: {unit}")
        return False
    except Exception as e:
        print(f"[NODE ENGINE] ⚠️  Error restarting {unit}: {e}")
        return False


def owning_units_for(node_id: str) -> list:
    """
    The services that publish this node's device and must republish after a
    rename. Ambient owns device configs for every ambient node; recorder
    nodes additionally have a per-node passive publisher and cluster entities.
    Only units that actually exist on the box are returned.
    """
    units = []
    candidates = [
        f"voicebm-publisher-{node_id}.service",
        "voicebm-cluster-publisher.service",
        "voicebm-ambient.service",
    ]
    # cluster publisher only matters when this node has a passive publisher
    has_publisher = Path(f"/etc/systemd/system/voicebm-publisher-{node_id}.service").exists()
    for unit in candidates:
        if unit == "voicebm-cluster-publisher.service" and not has_publisher:
            continue
        if Path(f"/etc/systemd/system/{unit}").exists():
            units.append(unit)
    return units


def publish_status(client, payload: dict):
    payload["timestamp"] = datetime.datetime.now().isoformat()
    client.publish(TOPIC_STATUS, json.dumps(payload), qos=1, retain=True)


# ============================================================================
# TRANSFORM OPERATION (Rename Node)
# ============================================================================

def transform_node(client, node_id: str, new_friendly_name: str) -> tuple[bool, str]:
    """
    Rename a node's friendly_name. node_id never changes.

    Steps:
    1. Validate node exists and name is valid
    2. Update nodes.{node_id}.friendly_name in config.json (atomic)
    3. Restart the services that own this node's entities (they read
       friendly_name from config at startup and republish discovery)
    4. Republish this engine's own entities with the new device name
    5. Log operation
    """
    print(f"\n[TRANSFORM] Renaming node '{node_id}' to '{new_friendly_name}'")

    nodes = get_nodes()
    if node_id not in nodes:
        error = f"Node '{node_id}' does not exist in config.json"
        log_operation("transform_failed", {"node_id": node_id, "new_name": new_friendly_name, "error": error})
        return False, error

    is_valid, error_msg = validate_friendly_name(new_friendly_name)
    if not is_valid:
        log_operation("transform_failed", {"node_id": node_id, "new_name": new_friendly_name, "error": error_msg})
        return False, error_msg

    old_friendly = node_friendly(nodes[node_id], node_id)
    if new_friendly_name == old_friendly:
        message = f"Node '{node_id}' is already named '{old_friendly}' — nothing to do"
        log_operation("transform_noop", {"node_id": node_id, "name": old_friendly})
        return True, message

    try:
        # 1. Mutate exactly one key in config.json, atomically
        cfg = load_config()
        cfg['nodes'][node_id]['friendly_name'] = new_friendly_name
        write_config_atomic(cfg)
        print(f"  ✓ config.json: nodes.{node_id}.friendly_name = '{new_friendly_name}'")

        # 2. Delegate republish to the owning services
        restarted = []
        for unit in owning_units_for(node_id):
            if restart_service(unit):
                restarted.append(unit)
        if restarted:
            time.sleep(3)  # give them time to republish device configs

        # 3. Republish this engine's own entities with the corrected device name
        publish_node_engine_entities(client, node_id, new_friendly_name)

        log_operation("transform_success", {
            "node_id": node_id,
            "old_name": old_friendly,
            "new_name": new_friendly_name,
            "restarted": restarted
        })

        print(f"  ✓ Transform complete: '{old_friendly}' -> '{new_friendly_name}' (node_id '{node_id}' unchanged)")
        return True, f"Renamed to '{new_friendly_name}'"

    except Exception as e:
        error = f"Transform failed: {str(e)}"
        log_operation("transform_error", {"node_id": node_id, "new_name": new_friendly_name, "error": str(e)})
        return False, error


# ============================================================================
# MQTT HANDLERS
# ============================================================================

def handle_transform_name_input(client, userdata, msg):
    """Stage a new name for a node (text input). Nothing executes here."""
    global transform_names

    try:
        # Topic: voicebm/node/transform/{node_id}/name/set
        parts = msg.topic.split('/')
        node_id = parts[3]
        new_name = msg.payload.decode('utf-8').strip()

        transform_names[node_id] = new_name

        # Echo back to state topic
        client.publish(f"{TOPIC_TRANSFORM_PREFIX}/{node_id}/name", new_name, qos=1, retain=True)
        print(f"[TRANSFORM NAME] {node_id} -> {new_name}")

    except Exception as e:
        print(f"[TRANSFORM NAME] Error: {e}")


def handle_transform_execute(client, userdata, msg):
    """Execute the rename using the staged name (button press)."""
    global transform_names

    try:
        # Topic: voicebm/node/transform/{node_id}/execute
        parts = msg.topic.split('/')
        node_id = parts[3]

        new_friendly_name = transform_names.get(node_id, "").strip()

        if not new_friendly_name:
            print(f"[TRANSFORM] No name staged for {node_id}")
            publish_status(client, {
                "operation": "node_transform",
                "node_id": node_id,
                "success": False,
                "message": "Please enter a new name first"
            })
            return

        success, message = transform_node(client, node_id, new_friendly_name)

        # Clear staged name on success
        if success:
            transform_names.pop(node_id, None)
            client.publish(f"{TOPIC_TRANSFORM_PREFIX}/{node_id}/name", "", qos=1, retain=True)

        publish_status(client, {
            "operation": "node_transform",
            "node_id": node_id,
            "success": success,
            "message": message
        })

    except Exception as e:
        print(f"[TRANSFORM EXECUTE] Error: {e}")


# ============================================================================
# DISCOVERY
# ============================================================================

def publish_node_engine_entities(client, node_id: str, friendly: str):
    """
    Publish the rename controls for one node, attached to the node's EXISTING
    device. The device block matches publish_identity_node exactly
    (identifiers ["voicebm_{node_id}"]) so these entities appear inside the
    node's own device area — never under the global device.
    """
    device = {
        "identifiers": [f"voicebm_{node_id}"],
        "name": f"Voice Biometrics {friendly}",
        "manufacturer": "David M. Dryver Sr.",
        "model": "Home Assistant Voice Biometrics",
        "sw_version": "2.0"
    }

    # New Node Name text input
    name_config = {
        "name": "New Node Name",
        "unique_id": f"voicebm_{node_id}_transform_name",
        "command_topic": f"{TOPIC_TRANSFORM_PREFIX}/{node_id}/name/set",
        "state_topic": f"{TOPIC_TRANSFORM_PREFIX}/{node_id}/name",
        "mode": "text",
        "icon": "mdi:rename-box",
        "device": device
    }
    client.publish(
        f"{DISCOVERY_PREFIX}/text/voicebm_{node_id}_transform_name/config",
        json.dumps(name_config),
        qos=1,
        retain=True
    )

    # Rename Node button
    button_config = {
        "name": "Rename Node",
        "unique_id": f"voicebm_{node_id}_transform_execute",
        "command_topic": f"{TOPIC_TRANSFORM_PREFIX}/{node_id}/execute",
        "payload_press": "PRESS",
        "icon": "mdi:home-edit",
        "device": device
    }
    client.publish(
        f"{DISCOVERY_PREFIX}/button/voicebm_{node_id}_transform_execute/config",
        json.dumps(button_config),
        qos=1,
        retain=True
    )


def scan_and_publish_node_entities(client, first_run: bool):
    """Publish rename controls for every node in config.json."""
    nodes = get_nodes()
    if not nodes:
        print("[NODE ENGINE] No nodes found in config.json")
        return

    for node_id, node in nodes.items():
        friendly = node_friendly(node, node_id)
        publish_node_engine_entities(client, node_id, friendly)
        # Initialize name state only on first run; afterwards respect retained state
        if first_run:
            client.publish(f"{TOPIC_TRANSFORM_PREFIX}/{node_id}/name", "", qos=1, retain=True)
        print(f"[NODE ENGINE] ✓ Published rename controls for: {friendly} ({node_id})")

    print(f"[NODE ENGINE] Published entities for {len(nodes)} nodes")


def on_connect(client, userdata, flags, reason_code, properties):
    """MQTT connection callback"""
    if reason_code == 0:
        print("[NODE ENGINE] Connected to MQTT broker")

        # Subscribe to command topics
        client.subscribe(f"{TOPIC_TRANSFORM_PREFIX}/+/name/set")
        client.subscribe(f"{TOPIC_TRANSFORM_PREFIX}/+/execute")

        first_run = is_first_run()
        if first_run:
            print("[NODE ENGINE] First run detected - will publish initial states")
            publish_status(client, {"status": "ready", "message": "Ready"})
        else:
            print("[NODE ENGINE] Subsequent run - respecting HA state")

        scan_and_publish_node_entities(client, first_run)

        if first_run:
            mark_initialized()

        print("[NODE ENGINE] Subscriptions active")
        print(f"  - Name inputs:  {TOPIC_TRANSFORM_PREFIX}/+/name/set")
        print(f"  - Rename buttons: {TOPIC_TRANSFORM_PREFIX}/+/execute")
    else:
        print(f"[NODE ENGINE] Connection failed with reason code {reason_code}")


def on_message(client, userdata, msg):
    """MQTT message router"""
    try:
        topic = msg.topic

        if topic.startswith(TOPIC_TRANSFORM_PREFIX) and topic.endswith("/name/set"):
            handle_transform_name_input(client, userdata, msg)
        elif topic.startswith(TOPIC_TRANSFORM_PREFIX) and topic.endswith("/execute"):
            handle_transform_execute(client, userdata, msg)
    except Exception as e:
        print(f"[NODE ENGINE] Message handler error: {e}")


# ============================================================================
# MAIN
# ============================================================================

def main():
    """Main Node Engine service loop"""
    print("=" * 70)
    print("VoiceBM Node Engine - Node Identity Transformation")
    print("LLM Voice Biometrics by David M. Dryver Sr.")
    print("=" * 70)
    print(f"Config: {CONFIG_FILE}")
    print(f"Logs directory: {LOGS_DIR}")
    print(f"MQTT Broker: {MQTT_BROKER}:{MQTT_PORT}")
    print()

    LOGS_DIR.mkdir(exist_ok=True)

    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    if mqtt_config.get('user') and mqtt_config.get('password'):
        client.username_pw_set(mqtt_config['user'], mqtt_config['password'])
    client.on_connect = on_connect
    client.on_message = on_message

    print(f"Connecting to MQTT broker at {MQTT_BROKER}:{MQTT_PORT}...")
    client.connect(MQTT_BROKER, MQTT_PORT, 60)

    print("Node Engine running. Press Ctrl+C to stop.")
    print()

    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print("\n[NODE ENGINE] Shutting down...")
        client.disconnect()


if __name__ == "__main__":
    main()
```


## 19. `setup_node.py` <a id="19-setup-nodepy"></a>

_VoiceBM — Passive Node Setup (interactive)_

```python
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
```


# Audio server & maintenance


## 20. `audio_server.py` <a id="20-audio-serverpy"></a>

_Simple HTTP server for voice recording playback_

```python
#!/usr/bin/env python3
"""
Simple HTTP server for voice recording playback
Serves both /recordings/ and /pending/ paths
"""

import http.server
import socketserver
import os
import json
from pathlib import Path
from urllib.parse import unquote

# Load configuration
CONFIG_FILE = "/home/user/voicebm/config.json"
try:
    with open(CONFIG_FILE, 'r') as f:
        config = json.load(f)
        PORT = config['audio_server']['port']
except:
    PORT = 9090  # Fallback

BASE_DIR = "/home/user/voicebm"


class VoiceBMHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    """Custom handler that routes to different directories based on path"""
    
    def __init__(self, *args, **kwargs):
        # Don't set directory in parent - we handle routing manually
        super().__init__(*args, **kwargs)
    
    def translate_path(self, path):
        """Translate URL path to filesystem path"""
        # Decode URL encoding
        path = unquote(path)
        
        # Remove leading slash
        path = path.lstrip('/')
        
        # Route based on first path component
        if path.startswith('pending/'):
            # Serve from pending_active/recordings
            relative = path[8:]  # Remove 'pending/'
            return os.path.join(BASE_DIR, 'pending_active', 'recordings', relative)
        
        elif path.startswith('living/'):
            # Serve from recordings/living
            relative = path[7:]  # Remove 'living/'
            return os.path.join(BASE_DIR, 'recordings', 'living', relative)
        
        elif path.startswith('recordings/'):
            # Direct recordings path
            relative = path[11:]  # Remove 'recordings/'
            return os.path.join(BASE_DIR, 'recordings', relative)
        
        else:
            # Default to recordings directory
            return os.path.join(BASE_DIR, 'recordings', path)
    
    def end_headers(self):
        # Add CORS headers so Home Assistant can access
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        super().end_headers()
    
    def do_OPTIONS(self):
        """Handle CORS preflight requests"""
        self.send_response(200)
        self.end_headers()
    
    def log_message(self, format, *args):
        """Custom logging"""
        print(f"[{self.log_date_time_string()}] {args[0]}")


def main():
    # Ensure directories exist
    Path(f"{BASE_DIR}/recordings/living").mkdir(parents=True, exist_ok=True)
    Path(f"{BASE_DIR}/pending_active/recordings").mkdir(parents=True, exist_ok=True)
    
    with socketserver.TCPServer(("", PORT), VoiceBMHTTPRequestHandler) as httpd:
        print(f"=" * 60)
        print(f"VoiceBM Audio Server")
        print(f"=" * 60)
        print(f"Listening on port {PORT}")
        print(f"")
        print(f"URL Paths:")
        print(f"  /living/          -> {BASE_DIR}/recordings/living/")
        print(f"  /recordings/      -> {BASE_DIR}/recordings/")
        print(f"  /pending/         -> {BASE_DIR}/pending_active/recordings/")
        print(f"")
        print(f"Example URLs:")
        print(f"  http://127.0.0.1:{PORT}/living/living_20251128_120000.wav")
        print(f"  http://127.0.0.1:{PORT}/pending/active_1732825200000.wav")
        print(f"=" * 60)
        print(f"Press Ctrl+C to stop")
        
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server...")


if __name__ == "__main__":
    main()
```


## 21. `retention.py` <a id="21-retentionpy"></a>

_VoiceBM Retention Service - Clean up expired WAV and embedding files_

```python
#!/usr/bin/env python3
"""
VoiceBM Retention Service - Clean up expired WAV and embedding files

RULES:
- Reads passive rooms from config.json rooms where recorder_enabled=true
- On startup: immediately sweep all rooms before entering loop
- Age-based: delete WAV+embedding pairs older than RETENTION_SECONDS
- Volume-based: if file count exceeds MAX_FILES, cycle out oldest regardless of age
- Enrolled files: WAV expires after 3 days, embedding stays PERMANENT (in enroll folder)

Files in recordings/{room} and embeddings/{room} are TEMPORARY.
Only files MOVED to enroll/{person}/ are permanent.
"""

import os
import json
import time
import datetime
import pathlib

CONFIG_FILE = "/home/user/voicebm/config.json"
META_LAB    = "/home/user/voicebm/meta/labeled"
ENROLL_DIR  = "/home/user/voicebm/enroll"

RETENTION_SECONDS = 3 * 24 * 3600  # 3 days
MAX_FILES         = 5000            # volume cap per room — matches recorder safety limit
SWEEP_INTERVAL    = 60              # seconds between sweeps


def load_config():
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)


def get_passive_rooms(config):
    """Return list of room names with recorder_enabled=true from config."""
    rooms = []
    for room_name, room_cfg in config.get("rooms", {}).items():
        if room_cfg.get("recorder_enabled", False):
            rooms.append(room_name)
    return rooms


def get_voicebm_base(config):
    return config.get("paths", {}).get("voicebm_base", "/home/user/voicebm")


def now():
    return int(time.time())


def parse_expire(sidecar):
    """Parse expiration timestamp from labeled sidecar JSON."""
    try:
        with open(sidecar, 'r') as f:
            j = json.load(f)
            expire_str = j.get("expire_at")
            if expire_str:
                return int(datetime.datetime.strptime(
                    expire_str, "%Y-%m-%dT%H:%M:%SZ").timestamp())
    except:
        pass
    return None


def is_enrolled(eid):
    """Check if an event ID has been enrolled to any person."""
    enroll_path = pathlib.Path(ENROLL_DIR)
    if not enroll_path.exists():
        return False
    for person_dir in enroll_path.iterdir():
        if not person_dir.is_dir():
            continue
        emb_file = person_dir / "embeddings" / f"{eid}.txt"
        if emb_file.exists():
            return True
    return False


def delete_file(path, file_type):
    """Delete a file and log result."""
    try:
        if os.path.exists(path):
            os.remove(path)
            print(f"  ✔ Deleted {file_type}: {os.path.basename(path)}")
            return True
    except Exception as e:
        print(f"  ✗ Failed to delete {file_type}: {e}")
    return False


def sweep_room(room, voicebm_base):
    """
    Sweep one room's recordings and embeddings.
    1. Delete age-expired unenrolled files.
    2. If file count still exceeds MAX_FILES, cycle out oldest until under limit.
    """
    rec_path = pathlib.Path(voicebm_base) / "recordings" / room
    emb_path = pathlib.Path(voicebm_base) / "embeddings" / room

    if not rec_path.exists():
        return

    emb_path.mkdir(parents=True, exist_ok=True)

    current      = now()
    deleted_wav  = 0
    deleted_emb  = 0

    # ── Pass 1: Age-based cleanup ─────────────────────────────────────────
    for wav in list(rec_path.glob("*.wav")):
        eid = wav.stem

        if is_enrolled(eid):
            continue

        sidecar      = os.path.join(META_LAB, f"{eid}.json")
        should_delete = False

        if os.path.exists(sidecar):
            exp = parse_expire(sidecar)
            if exp and current > exp:
                should_delete = True
        else:
            try:
                mtime = int(wav.stat().st_mtime)
                if current - mtime > RETENTION_SECONDS:
                    should_delete = True
            except:
                pass

        if should_delete:
            print(f"[{room}] Age expiry: {eid}")
            if delete_file(str(wav), "WAV"):
                deleted_wav += 1
            emb_file = emb_path / f"{eid}.txt"
            if delete_file(str(emb_file), "EMB"):
                deleted_emb += 1
            if os.path.exists(sidecar):
                delete_file(sidecar, "sidecar")

    # ── Pass 2: Volume cap — cycle out oldest until under MAX_FILES ───────
    wav_files = sorted(
        rec_path.glob("*.wav"),
        key=lambda f: f.stat().st_mtime
    )
    file_count = len(wav_files)

    TARGET_FILES = MAX_FILES // 2  # clean to half cap for breathing room
    if file_count >= MAX_FILES:
        overage = file_count - TARGET_FILES
        print(f"[{room}] Volume cap exceeded ({file_count}/{MAX_FILES}) — cycling out {overage} oldest files (target: {TARGET_FILES})")
        for wav in wav_files[:overage]:
            eid = wav.stem
            if is_enrolled(eid):
                continue
            print(f"[{room}] Volume evict: {eid}")
            if delete_file(str(wav), "WAV"):
                deleted_wav += 1
            emb_file = emb_path / f"{eid}.txt"
            if delete_file(str(emb_file), "EMB"):
                deleted_emb += 1
            sidecar = os.path.join(META_LAB, f"{eid}.json")
            if os.path.exists(sidecar):
                delete_file(sidecar, "sidecar")

    # ── Pass 3: Orphan embeddings (no matching WAV, old enough) ──────────
    if emb_path.exists():
        for emb in emb_path.glob("*.txt"):
            eid = emb.stem
            wav_file = rec_path / f"{eid}.wav"
            if is_enrolled(eid):
                continue
            if not wav_file.exists():
                try:
                    mtime = int(emb.stat().st_mtime)
                    if current - mtime > RETENTION_SECONDS:
                        print(f"[{room}] Orphan embedding: {eid}")
                        if delete_file(str(emb), "orphan EMB"):
                            deleted_emb += 1
                except:
                    pass

    if deleted_wav > 0 or deleted_emb > 0:
        print(f"[{room}] Sweep complete: {deleted_wav} WAVs, {deleted_emb} embeddings deleted")


def sweep_all(rooms, voicebm_base):
    for room in rooms:
        sweep_room(room, voicebm_base)


def main():
    config       = load_config()
    rooms        = get_passive_rooms(config)
    voicebm_base = get_voicebm_base(config)

    print("=" * 60)
    print("VoiceBM Retention Service")
    print("=" * 60)
    print(f"Base: {voicebm_base}")
    print(f"Rooms: {rooms}")
    print(f"Retention: {RETENTION_SECONDS // 3600} hours")
    print(f"Volume cap: {MAX_FILES} files per room")
    print("=" * 60)

    # Sweep immediately on startup
    print("Running startup sweep...")
    sweep_all(rooms, voicebm_base)
    print("Startup sweep complete — recorders will resume automatically once volume is clear.")

    print(f"Running retention sweep every {SWEEP_INTERVAL} seconds...")
    print("Press Ctrl+C to exit\n")

    while True:
        try:
            sweep_all(rooms, voicebm_base)
            time.sleep(SWEEP_INTERVAL)
        except KeyboardInterrupt:
            print("\nShutting down...")
            break
        except Exception as e:
            print(f"Error in sweep: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
```


## 22. `cleanup_recordings.py` <a id="22-cleanup-recordingspy"></a>

_VoiceBM Recording Cleanup - Delete expired WAV files after 3-day retention period_

```python
#!/usr/bin/env python3
"""
VoiceBM Recording Cleanup - Delete expired WAV files after 3-day retention period

PURPOSE:
- WAV files take up space, keep them for 3 days for manual review
- After 3 days, delete the WAV but keep the embedding
- Embeddings stay forever (small files, needed for recognition)

BEHAVIOR:
- Scans all person folders in /enroll/
- Reads metadata.json for each person
- Checks expire_at timestamp for each sample
- Deletes WAV if past expiration
- Updates metadata to mark recording as deleted
- Keeps embedding file

RUN AS:
- Systemd timer (daily)
- Or cron job: 0 2 * * * /home/user/voicebm/bin/cleanup_recordings.py
"""

import os
import json
import datetime
from pathlib import Path

ENROLL_DIR = "/home/user/voicebm/enroll"


def cleanup_expired_recordings():
    """
    Delete WAV files past their 3-day retention period.
    Keep embeddings forever.
    """
    enroll_path = Path(ENROLL_DIR)
    
    if not enroll_path.exists():
        print(f"Enrollment directory not found: {ENROLL_DIR}")
        return
    
    total_deleted = 0
    total_kept = 0
    
    print(f"Starting cleanup scan: {datetime.datetime.now().isoformat()}")
    print(f"Scanning: {ENROLL_DIR}\n")
    
    # Scan each person folder
    for person_dir in enroll_path.iterdir():
        if not person_dir.is_dir():
            continue
        
        person_id = person_dir.name
        metadata_file = person_dir / 'metadata.json'
        
        if not metadata_file.exists():
            print(f"âš  No metadata for {person_id}, skipping")
            continue
        
        # Load metadata
        try:
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)
        except Exception as e:
            print(f"âœ— Failed to load metadata for {person_id}: {e}")
            continue
        
        samples = metadata.get('samples', [])
        if not samples:
            continue
        
        print(f"Checking {person_id} ({len(samples)} samples)...")
        
        updated_samples = []
        person_deleted = 0
        person_kept = 0
        
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        
        for sample in samples:
            expire_at = sample.get('expire_at')
            recording_path = sample.get('recording')
            
            # If already marked as deleted, keep as-is
            if recording_path is None:
                updated_samples.append(sample)
                continue
            
            # If no expiration, keep forever
            if not expire_at:
                updated_samples.append(sample)
                person_kept += 1
                continue
            
            # Parse expiration timestamp
            try:
                # Handle ISO format with 'Z' suffix
                expire_dt = datetime.datetime.fromisoformat(expire_at.replace('Z', '+00:00'))
            except Exception as e:
                print(f"  âš  Invalid expire_at for {sample['event_id']}: {e}")
                updated_samples.append(sample)
                person_kept += 1
                continue
            
            # Check if expired
            if now_utc > expire_dt:
                # Delete WAV file
                wav_file = person_dir / recording_path
                
                if wav_file.exists():
                    try:
                        wav_file.unlink()
                        print(f"  âœ“ Deleted: {wav_file.name}")
                        person_deleted += 1
                    except Exception as e:
                        print(f"  âœ— Failed to delete {wav_file.name}: {e}")
                        updated_samples.append(sample)
                        person_kept += 1
                        continue
                else:
                    print(f"  âš  Already gone: {wav_file.name}")
                    person_deleted += 1
                
                # Update sample to mark recording as deleted
                sample['recording'] = None
                sample['recording_deleted_at'] = now_utc.isoformat()
                updated_samples.append(sample)
            else:
                # Not expired yet, keep it
                time_left = expire_dt - now_utc
                days_left = time_left.days
                # Don't print for every file, just count
                updated_samples.append(sample)
                person_kept += 1
        
        if person_deleted > 0:
            print(f"  Deleted {person_deleted} recording(s), kept {person_kept}")
        
        # Save updated metadata
        metadata['samples'] = updated_samples
        metadata['last_cleanup'] = now_utc.isoformat()
        
        try:
            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)
        except Exception as e:
            print(f"  âœ— Failed to save metadata: {e}")
        
        total_deleted += person_deleted
        total_kept += person_kept
    
    print(f"\nCleanup complete:")
    print(f"  Deleted: {total_deleted} recording(s)")
    print(f"  Kept: {total_kept} recording(s)")
    print(f"  Time: {datetime.datetime.now().isoformat()}")


if __name__ == "__main__":
    cleanup_expired_recordings()
```


# Dashboard (debug UI)


## 23. `voicebm_dashboard.py` <a id="23-voicebm-dashboardpy"></a>

_VoiceBM Web Dashboard - Professional UI with branding_

```python
#!/usr/bin/env python3
"""
VoiceBM Web Dashboard - Professional UI with branding
LLM Voice Biometrics by David M. Dryver Sr.

Provides web interface for VoiceBM control, enrollment, clustering, and blocklist management.
File-based shared state for multi-platform support (Home Assistant, Open WebUI, local LLM).
"""

from flask import Flask, render_template_string, jsonify, request, send_file
from flask_cors import CORS
from pathlib import Path
import json
import os
from typing import Dict, List, Optional
import datetime

app = Flask(__name__)
CORS(app)

# Configuration
VOICEBM_BASE = "/home/user/voicebm"
META_DIR = f"{VOICEBM_BASE}/meta"
ENROLL_DIR = f"{VOICEBM_BASE}/enroll"
PENDING_RECORDINGS = f"{VOICEBM_BASE}/pending_active/recordings"
AUDIO_SERVER_BASE = "http://127.0.0.1:9090"

# State files
SETTINGS_FILE = f"{META_DIR}/settings.json"
ACTIVE_STATE_FILE = f"{META_DIR}/active_state.json"
PENDING_FILE = f"{VOICEBM_BASE}/pending_active/pending.json"
CLUSTERS_FILE = f"{META_DIR}/clusters.json"
USER_SETTINGS_FILE = f"{META_DIR}/user_settings.json"
THING_ENGINE_COMMANDS_FILE = f"{META_DIR}/thing_engine_commands.json"

# HTML Template with Bootstrap tables and branding
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VoiceBM Control Dashboard</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.0/font/bootstrap-icons.css">
    <style>
        body {
            background-color: #1a1a1a;
            color: #e0e0e0;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            padding: 20px;
        }
        .main-container {
            max-width: 1400px;
            margin: 0 auto;
        }
        .brand-header {
            text-align: center;
            margin-bottom: 30px;
            padding: 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.3);
        }
        .brand-title {
            font-size: 2.5rem;
            font-weight: bold;
            margin: 0;
            color: white;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }
        .brand-author {
            font-size: 1.1rem;
            margin: 5px 0;
            color: rgba(255,255,255,0.9);
        }
        .brand-version {
            font-size: 0.9rem;
            color: rgba(255,255,255,0.7);
            font-style: italic;
        }
        .section-card {
            background-color: #2d2d2d;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.2);
        }
        .section-title {
            font-size: 1.5rem;
            font-weight: 600;
            margin-bottom: 15px;
            color: #4ade80;
            border-bottom: 2px solid #4ade80;
            padding-bottom: 8px;
        }
        .table-dark {
            background-color: #242424;
            color: #e0e0e0;
        }
        .table-dark thead {
            background-color: #1a1a1a;
        }
        .table-dark tbody tr:hover {
            background-color: #333;
        }
        .badge-virtual {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }
        .badge-active {
            background-color: #4ade80;
        }
        .badge-blocked {
            background-color: #ef4444;
        }
        .btn-play { background-color: #3b82f6; border: none; }
        .btn-play:hover { background-color: #2563eb; }
        .btn-enroll { background-color: #10b981; border: none; }
        .btn-enroll:hover { background-color: #059669; }
        .btn-reject { background-color: #ef4444; border: none; }
        .btn-reject:hover { background-color: #dc2626; }
        .form-switch .form-check-input {
            width: 3em;
            height: 1.5em;
            cursor: pointer;
        }
        .form-switch .form-check-input:checked {
            background-color: #4ade80;
            border-color: #4ade80;
        }
        .cluster-card {
            background-color: #242424;
            border-radius: 6px;
            padding: 15px;
            margin-bottom: 10px;
            border-left: 4px solid #f59e0b;
        }
        .similarity-badge {
            background-color: #f59e0b;
            color: #000;
            font-weight: bold;
        }
        .no-activity {
            color: #60a5fa;
            font-style: italic;
        }
        .threshold-slider {
            width: 100%;
        }
        .badge-count {
            background-color: #6366f1;
            font-size: 0.9rem;
        }
    </style>
</head>
<body>
    <div class="main-container">
        <!-- Branded Header -->
        <div class="brand-header">
            <div class="brand-title">
                <i class="bi bi-mic-fill"></i> LLM Voice Biometrics
            </div>
            <div class="brand-author">by David M. Dryver Sr.</div>
            <div class="brand-version">Firmware: 1.0</div>
        </div>

        <!-- Active Pipeline Section -->
        <div class="section-card">
            <h2 class="section-title"><i class="bi bi-broadcast"></i> Active Pipeline</h2>
            <div id="active-status" class="no-activity">No recent activity</div>
            <div class="row mt-3">
                <div class="col-md-4">
                    <div class="form-check form-switch">
                        <input class="form-check-input" type="checkbox" id="injectionToggle">
                        <label class="form-check-label" for="injectionToggle">
                            ID Injection: <span id="injectionStatus">OFF</span>
                        </label>
                    </div>
                </div>
                <div class="col-md-8">
                    <label for="thresholdSlider" class="form-label">
                        Active Threshold: <span id="thresholdValue">0.50</span>
                    </label>
                    <input type="range" class="form-range threshold-slider" id="thresholdSlider" 
                           min="0.01" max="1.00" step="0.01" value="0.50">
                </div>
            </div>
        </div>

        <!-- Blocklist Control Section -->
        <div class="section-card">
            <h2 class="section-title"><i class="bi bi-shield-lock"></i> Blocklist Control</h2>
            <table class="table table-dark table-hover">
                <thead>
                    <tr>
                        <th>Identity</th>
                        <th>Status</th>
                        <th>Samples</th>
                        <th>Control</th>
                    </tr>
                </thead>
                <tbody id="blocklistTable">
                    <tr><td colspan="4" class="text-center">Loading...</td></tr>
                </tbody>
            </table>
        </div>

        <!-- Thing Engine Section -->
        <div class="section-card">
            <h2 class="section-title"><i class="bi bi-tools"></i> Thing Engine - Identity Management</h2>
            <p class="text-muted mb-3">Permanent identity operations: rename, merge, and delete enrolled identities.</p>
            
            <table class="table table-dark table-hover">
                <thead>
                    <tr>
                        <th>Identity</th>
                        <th>Transform</th>
                        <th>Merge Tag</th>
                        <th>Delete</th>
                    </tr>
                </thead>
                <tbody id="thingEngineTable">
                    <tr><td colspan="4" class="text-center">Loading...</td></tr>
                </tbody>
            </table>
            
            <div class="mt-3">
                <button class="btn btn-warning" id="executeMergeBtn" disabled>
                    <i class="bi bi-arrow-down-up"></i> Merge Tagged Identities
                </button>
            </div>
        </div>

        <!-- Pending Voices Section -->
        <div class="section-card">
            <h2 class="section-title">
                <i class="bi bi-hourglass-split"></i> Pending Voices
                <span class="badge badge-count" id="pendingCount">0</span>
            </h2>
            <table class="table table-dark table-hover">
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Timestamp</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody id="pendingTable">
                    <tr><td colspan="3" class="text-center">No pending voices</td></tr>
                </tbody>
            </table>
        </div>

        <!-- Enrolled Identities Section -->
        <div class="section-card">
            <h2 class="section-title">
                <i class="bi bi-people-fill"></i> Enrolled Identities
                <span class="badge badge-count" id="enrolledCount">0</span>
            </h2>
            <table class="table table-dark table-hover">
                <thead>
                    <tr>
                        <th>Name</th>
                        <th>Samples</th>
                        <th>Type</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody id="enrolledTable">
                    <tr><td colspan="4" class="text-center">Loading...</td></tr>
                </tbody>
            </table>
        </div>

        <!-- Voice Clusters Section -->
        <div class="section-card">
            <h2 class="section-title">
                <i class="bi bi-diagram-3"></i> Voice Clusters
                <span class="badge badge-count" id="clusterCount">0</span>
            </h2>
            <div id="clustersList">
                <p class="text-center">No clusters available</p>
            </div>
        </div>
    </div>

    <script>
        // State
        let currentSettings = {};
        let currentActiveState = {};

        // Load initial state
        async function loadState() {
            try {
                const [settings, activeState, pending, clusters, enrolled] = await Promise.all([
                    fetch('/api/state/settings').then(r => r.json()),
                    fetch('/api/state/active').then(r => r.json()),
                    fetch('/api/state/pending').then(r => r.json()),
                    fetch('/api/state/clusters').then(r => r.json()),
                    fetch('/api/enrolled').then(r => r.json())
                ]);

                updateSettings(settings);
                updateActiveState(activeState);
                updatePending(pending);
                updateClusters(clusters);
                updateBlocklist(enrolled);
                updateEnrolled(enrolled);
                loadThingEngine();
            } catch (error) {
                console.error('Error loading state:', error);
            }
        }

        function updateSettings(settings) {
            currentSettings = settings;
            const injectionToggle = document.getElementById('injectionToggle');
            const injectionStatus = document.getElementById('injectionStatus');
            const thresholdSlider = document.getElementById('thresholdSlider');
            const thresholdValue = document.getElementById('thresholdValue');

            injectionToggle.checked = settings.inject_identity || false;
            injectionStatus.textContent = settings.inject_identity ? 'ON' : 'OFF';
            injectionStatus.style.color = settings.inject_identity ? '#4ade80' : '#ef4444';

            const threshold = settings.active_threshold || 0.50;
            thresholdSlider.value = threshold;
            thresholdValue.textContent = threshold.toFixed(2);
        }

        function updateActiveState(state) {
            currentActiveState = state;
            const statusDiv = document.getElementById('active-status');
            
            if (state.speaker_id) {
                statusDiv.innerHTML = `
                    <strong>Current Speaker:</strong> ${state.display_name || 'Unknown'} 
                    (${state.speaker_id})<br>
                    <strong>Confidence:</strong> ${(state.confidence * 100).toFixed(1)}%<br>
                    <strong>Decision:</strong> <span class="badge ${state.decision === 'accepted' ? 'badge-active' : 'bg-warning'}">${state.decision}</span>
                `;
                statusDiv.classList.remove('no-activity');
            } else {
                statusDiv.innerHTML = 'No recent activity';
                statusDiv.classList.add('no-activity');
            }
        }

        function updatePending(pending) {
            const table = document.getElementById('pendingTable');
            const count = document.getElementById('pendingCount');
            
            count.textContent = pending.entries?.length || 0;

            if (!pending.entries || pending.entries.length === 0) {
                table.innerHTML = '<tr><td colspan="3" class="text-center">No pending voices</td></tr>';
                return;
            }

            table.innerHTML = pending.entries.map(entry => `
                <tr>
                    <td><code>${entry.id}</code></td>
                    <td>${new Date(entry.timestamp * 1000).toLocaleString()}</td>
                    <td>
                        <button class="btn btn-sm btn-play" onclick="playAudio('${entry.audio_url}')">
                            <i class="bi bi-play-fill"></i> Play
                        </button>
                        <button class="btn btn-sm btn-enroll" onclick="enrollPending('${entry.id}')">
                            <i class="bi bi-check-circle"></i> Enroll
                        </button>
                        <button class="btn btn-sm btn-reject" onclick="rejectPending('${entry.id}')">
                            <i class="bi bi-x-circle"></i> Reject
                        </button>
                    </td>
                </tr>
            `).join('');
        }

        function updateBlocklist(enrolled) {
            const table = document.getElementById('blocklistTable');
            
            if (!enrolled || enrolled.length === 0) {
                table.innerHTML = '<tr><td colspan="4" class="text-center">No enrolled identities</td></tr>';
                return;
            }

            table.innerHTML = enrolled.map(person => {
                const statusBadge = person.blocked 
                    ? '<span class="badge badge-blocked">BLOCKED</span>'
                    : '<span class="badge badge-active">ACTIVE</span>';
                
                const typeBadge = person.is_virtual 
                    ? '<span class="badge badge-virtual">Virtual</span>'
                    : '<span class="badge bg-secondary">Enrolled</span>';

                return `
                    <tr ${person.is_virtual ? 'style="border-left: 4px solid #764ba2;"' : ''}>
                        <td><strong>${person.display_name}</strong></td>
                        <td>${statusBadge}</td>
                        <td>${person.sample_count}</td>
                        <td>
                            <div class="form-check form-switch">
                                <input class="form-check-input" type="checkbox" 
                                       id="block_${person.person_id}" 
                                       ${person.blocked ? '' : 'checked'}
                                       onchange="toggleBlocklist('${person.person_id}')">
                                <label class="form-check-label" for="block_${person.person_id}">
                                    ${person.blocked ? 'Blocked' : 'Active'}
                                </label>
                            </div>
                        </td>
                    </tr>
                `;
            }).join('');
        }

        function updateEnrolled(enrolled) {
            const table = document.getElementById('enrolledTable');
            const count = document.getElementById('enrolledCount');
            
            // Filter out virtual user for this table
            const realEnrolled = enrolled.filter(p => !p.is_virtual);
            count.textContent = realEnrolled.length;

            if (realEnrolled.length === 0) {
                table.innerHTML = '<tr><td colspan="4" class="text-center">No enrolled identities</td></tr>';
                return;
            }

            table.innerHTML = realEnrolled.map(person => {
                const statusBadge = person.blocked 
                    ? '<span class="badge badge-blocked">BLOCKED</span>'
                    : '<span class="badge badge-active">ACTIVE</span>';

                return `
                    <tr>
                        <td><strong>${person.display_name}</strong></td>
                        <td>${person.sample_count}</td>
                        <td><span class="badge bg-secondary">Enrolled</span></td>
                        <td>${statusBadge}</td>
                    </tr>
                `;
            }).join('');
        }

        function updateClusters(clusters) {
            const container = document.getElementById('clustersList');
            const count = document.getElementById('clusterCount');
            
            count.textContent = clusters.length || 0;

            if (!clusters || clusters.length === 0) {
                container.innerHTML = '<p class="text-center">No clusters available</p>';
                return;
            }

            container.innerHTML = clusters.map(cluster => `
                <div class="cluster-card">
                    <div class="row align-items-center">
                        <div class="col-md-8">
                            <strong>Cluster ${cluster.cluster_id}</strong> - 
                            ${cluster.stats.count} samples
                            <span class="badge similarity-badge ms-2">
                                Similarity: ${(cluster.stats.avg_similarity * 100).toFixed(1)}%
                            </span>
                            ${cluster.stats.time_range.start ? `
                                <div class="text-muted small mt-1">
                                    Time range: ${cluster.stats.time_range.start.split('T')[0]}
                                </div>
                            ` : ''}
                        </div>
                        <div class="col-md-4 text-end">
                            <button class="btn btn-sm btn-primary" onclick="viewClusterSamples(${cluster.cluster_id})">
                                <i class="bi bi-list-ul"></i> Samples
                            </button>
                            <button class="btn btn-sm btn-play" onclick="playCluster(${cluster.cluster_id})">
                                <i class="bi bi-play-fill"></i> Play All
                            </button>
                        </div>
                    </div>
                </div>
            `).join('');
        }

        // Event handlers
        document.getElementById('injectionToggle').addEventListener('change', async (e) => {
            try {
                await fetch('/api/settings/injection', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ enabled: e.target.checked })
                });
            } catch (error) {
                console.error('Error updating injection:', error);
            }
        });

        document.getElementById('thresholdSlider').addEventListener('input', (e) => {
            document.getElementById('thresholdValue').textContent = parseFloat(e.target.value).toFixed(2);
        });

        document.getElementById('thresholdSlider').addEventListener('change', async (e) => {
            try {
                await fetch('/api/settings/threshold', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ threshold: parseFloat(e.target.value) })
                });
            } catch (error) {
                console.error('Error updating threshold:', error);
            }
        });

        async function toggleBlocklist(personId) {
            try {
                await fetch('/api/blocklist/toggle', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ person_id: personId })
                });
                loadState(); // Refresh
            } catch (error) {
                console.error('Error toggling blocklist:', error);
            }
        }

        function playAudio(url) {
            const audio = new Audio(url);
            audio.play();
        }

        async function enrollPending(pendingId) {
            const name = prompt('Enter person name (will be converted to person_id):');
            if (!name) return;

            try {
                const response = await fetch('/api/pending/enroll', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        pending_id: pendingId,
                        display_name: name
                    })
                });
                
                if (response.ok) {
                    alert('Enrolled successfully!');
                    loadState();
                }
            } catch (error) {
                console.error('Error enrolling:', error);
                alert('Enrollment failed');
            }
        }

        async function rejectPending(pendingId) {
            if (!confirm('Reject this voice sample?')) return;

            try {
                await fetch('/api/pending/reject', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ pending_id: pendingId })
                });
                loadState();
            } catch (error) {
                console.error('Error rejecting:', error);
            }
        }

        function viewClusterSamples(clusterId) {
            alert(`Cluster ${clusterId} sample viewer - Coming soon!`);
        }

        function playCluster(clusterId) {
            alert(`Play all samples from cluster ${clusterId} - Coming soon!`);
        }

        // === Thing Engine Functions ===
        
        async function loadThingEngine() {
            try {
                const response = await fetch('/api/enrolled');
                const people = await response.json();
                const table = document.getElementById('thingEngineTable');
                
                // Filter out virtual "user"
                const enrolled = people.filter(p => !p.is_virtual);
                
                if (enrolled.length === 0) {
                    table.innerHTML = '<tr><td colspan="4" class="text-center">No enrolled identities</td></tr>';
                    return;
                }
                
                table.innerHTML = enrolled.map(person => `
                    <tr>
                        <td>${person.display_name}</td>
                        <td>
                            <div class="input-group input-group-sm">
                                <input type="text" class="form-control" id="transform_${person.person_id}" 
                                       placeholder="New name..." style="max-width: 200px;">
                                <button class="btn btn-sm btn-primary" onclick="transformIdentity('${person.person_id}')">
                                    <i class="bi bi-arrow-repeat"></i> Rename
                                </button>
                            </div>
                        </td>
                        <td>
                            <div class="form-check form-switch">
                                <input class="form-check-input" type="checkbox" id="merge_${person.person_id}"
                                       onchange="updateMergeButton()">
                            </div>
                        </td>
                        <td>
                            <button class="btn btn-sm btn-danger" onclick="deleteIdentity('${person.person_id}')">
                                <i class="bi bi-trash"></i> Delete
                            </button>
                        </td>
                    </tr>
                `).join('');
                
                updateMergeButton();
            } catch (error) {
                console.error('Error loading Thing Engine:', error);
            }
        }
        
        async function transformIdentity(personId) {
            const input = document.getElementById(`transform_${personId}`);
            const newName = input.value.trim();
            
            if (!newName) {
                alert('Please enter a new name');
                return;
            }
            
            if (!confirm(`Rename this identity to "${newName}"?`)) return;
            
            try {
                const response = await fetch('/api/thing_engine/transform', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        person_id: personId,
                        new_name: newName
                    })
                });
                
                const result = await response.json();
                
                if (response.ok && result.success) {
                    alert('Transform queued successfully!');
                    input.value = '';
                    setTimeout(loadState, 3000); // Reload after 3 seconds
                } else {
                    alert('Transform failed: ' + (result.error || 'Unknown error'));
                }
            } catch (error) {
                console.error('Error transforming:', error);
                alert('Transform failed');
            }
        }
        
        async function deleteIdentity(personId) {
            if (!confirm(`PERMANENTLY DELETE this identity? This cannot be undone!`)) return;
            if (!confirm('Are you ABSOLUTELY SURE? All voice samples will be deleted!')) return;
            
            try {
                const response = await fetch('/api/thing_engine/delete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ person_id: personId })
                });
                
                const result = await response.json();
                
                if (response.ok && result.success) {
                    alert('Delete queued successfully!');
                    setTimeout(loadState, 3000); // Reload after 3 seconds
                } else {
                    alert('Delete failed: ' + (result.error || 'Unknown error'));
                }
            } catch (error) {
                console.error('Error deleting:', error);
                alert('Delete failed');
            }
        }
        
        function updateMergeButton() {
            const checkboxes = document.querySelectorAll('[id^="merge_"]');
            const checked = Array.from(checkboxes).filter(cb => cb.checked);
            const btn = document.getElementById('executeMergeBtn');
            
            btn.disabled = checked.length < 2;
            btn.textContent = checked.length >= 2 
                ? `Merge ${checked.length} Tagged Identities`
                : 'Merge Tagged Identities (select 2+)';
        }
        
        async function executeMerge() {
            const checkboxes = document.querySelectorAll('[id^="merge_"]');
            const tagged = Array.from(checkboxes)
                .filter(cb => cb.checked)
                .map(cb => cb.id.replace('merge_', ''));
            
            if (tagged.length < 2) {
                alert('Please tag at least 2 identities to merge');
                return;
            }
            
            const newName = prompt('Enter name for merged identity:');
            if (!newName || !newName.trim()) return;
            
            if (!confirm(`Merge ${tagged.length} identities into "${newName}"?`)) return;
            
            try {
                const response = await fetch('/api/thing_engine/merge', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        source_ids: tagged,
                        new_name: newName.trim()
                    })
                });
                
                const result = await response.json();
                
                if (response.ok && result.success) {
                    alert('Merge queued successfully!');
                    setTimeout(loadState, 5000); // Reload after 5 seconds
                } else {
                    alert('Merge failed: ' + (result.error || 'Unknown error'));
                }
            } catch (error) {
                console.error('Error merging:', error);
                alert('Merge failed');
            }
        }
        
        // Wire up merge button
        document.addEventListener('DOMContentLoaded', function() {
            const mergeBtn = document.getElementById('executeMergeBtn');
            if (mergeBtn) {
                mergeBtn.addEventListener('click', executeMerge);
            }
        });

        // Auto-refresh
        setInterval(loadState, 2000);
        loadState();
    </script>
</body>
</html>
'''


# === State File Helpers ===

def load_json(filepath: str, default: dict) -> dict:
    """Load JSON file with fallback to default"""
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading {filepath}: {e}")
    return default


def save_json(filepath: str, data: dict):
    """Save JSON file atomically"""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    tmp_path = f"{filepath}.tmp"
    with open(tmp_path, 'w') as f:
        json.dump(data, f, indent=2)
    os.replace(tmp_path, filepath)


def get_settings() -> dict:
    """Load settings.json"""
    return load_json(SETTINGS_FILE, {
        'inject_identity': True,
        'active_threshold': 0.50
    })


def get_active_state() -> dict:
    """Load active_state.json"""
    return load_json(ACTIVE_STATE_FILE, {})


def get_pending() -> dict:
    """Load pending.json"""
    return load_json(PENDING_FILE, {'entries': []})


def get_clusters() -> list:
    """Load clusters.json"""
    data = load_json(CLUSTERS_FILE, [])
    return data if isinstance(data, list) else []


def get_enrolled_people() -> list:
    """Get all enrolled people including virtual 'user'"""
    people = []
    
    # Add virtual "user" first
    user_settings = load_json(USER_SETTINGS_FILE, {'blocked': False})
    people.append({
        'person_id': 'user',
        'display_name': 'user',
        'sample_count': 0,
        'blocked': user_settings.get('blocked', False),
        'is_virtual': True
    })
    
    # Add enrolled people
    if not os.path.exists(ENROLL_DIR):
        return people
    
    for person_dir in Path(ENROLL_DIR).iterdir():
        if not person_dir.is_dir():
            continue
        
        person_id = person_dir.name
        metadata_file = person_dir / 'metadata.json'
        
        if metadata_file.exists():
            try:
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
                    display_name = metadata.get('display_name', person_id.replace('_', ' ').title())
                    sample_count = len(metadata.get('samples', []))
                    blocked = metadata.get('blocked', False)
            except:
                display_name = person_id.replace('_', ' ').title()
                sample_count = 0
                blocked = False
        else:
            display_name = person_id.replace('_', ' ').title()
            sample_count = 0
            blocked = False
        
        people.append({
            'person_id': person_id,
            'display_name': display_name,
            'sample_count': sample_count,
            'blocked': blocked,
            'is_virtual': False
        })
    
    # Sort: virtual user first, then by sample count descending
    return sorted(people, key=lambda x: (not x['is_virtual'], -x['sample_count']))


# === API Routes ===

@app.route('/')
def index():
    """Main dashboard page"""
    return render_template_string(HTML_TEMPLATE)


@app.route('/api/state/settings')
def api_settings():
    """Get current settings"""
    return jsonify(get_settings())


@app.route('/api/state/active')
def api_active_state():
    """Get current active state"""
    return jsonify(get_active_state())


@app.route('/api/state/pending')
def api_pending():
    """Get pending voices"""
    return jsonify(get_pending())


@app.route('/api/state/clusters')
def api_clusters():
    """Get voice clusters"""
    return jsonify(get_clusters())


@app.route('/api/enrolled')
def api_enrolled():
    """Get enrolled people"""
    return jsonify(get_enrolled_people())


@app.route('/api/settings/injection', methods=['POST'])
def update_injection():
    """Update ID injection setting"""
    data = request.get_json()
    settings = get_settings()
    settings['inject_identity'] = data.get('enabled', False)
    settings['last_updated'] = datetime.datetime.now().isoformat()
    save_json(SETTINGS_FILE, settings)
    return jsonify({'success': True})


@app.route('/api/settings/threshold', methods=['POST'])
def update_threshold():
    """Update active threshold setting"""
    data = request.get_json()
    settings = get_settings()
    settings['active_threshold'] = float(data.get('threshold', 0.50))
    settings['last_updated'] = datetime.datetime.now().isoformat()
    save_json(SETTINGS_FILE, settings)
    return jsonify({'success': True})


@app.route('/api/blocklist/toggle', methods=['POST'])
def toggle_blocklist():
    """Toggle blocklist for a person or virtual user"""
    data = request.get_json()
    person_id = data.get('person_id')
    
    if not person_id:
        return jsonify({'error': 'Missing person_id'}), 400
    
    # Special handling for virtual "user"
    if person_id == 'user':
        user_settings = load_json(USER_SETTINGS_FILE, {'blocked': False})
        user_settings['blocked'] = not user_settings.get('blocked', False)
        user_settings['last_updated'] = datetime.datetime.now().isoformat()
        save_json(USER_SETTINGS_FILE, user_settings)
        return jsonify({'success': True, 'blocked': user_settings['blocked']})
    
    # Handle enrolled person
    metadata_file = Path(ENROLL_DIR) / person_id / 'metadata.json'
    
    if not metadata_file.exists():
        return jsonify({'error': 'Person not found'}), 404
    
    metadata = load_json(str(metadata_file), {})
    metadata['blocked'] = not metadata.get('blocked', False)
    metadata['last_updated'] = datetime.datetime.now().isoformat()
    save_json(str(metadata_file), metadata)
    
    return jsonify({'success': True, 'blocked': metadata['blocked']})


@app.route('/api/pending/enroll', methods=['POST'])
def enroll_pending():
    """Enroll a pending voice"""
    data = request.get_json()
    pending_id = data.get('pending_id')
    display_name = data.get('display_name', '').strip()
    
    if not pending_id or not display_name:
        return jsonify({'error': 'Missing required fields'}), 400
    
    person_id = display_name.lower().replace(' ', '_')
    
    # TODO: Implement enrollment logic
    # This would move files from pending_active/ to enroll/{person_id}/
    
    return jsonify({'success': True, 'person_id': person_id})


@app.route('/api/pending/reject', methods=['POST'])
def reject_pending():
    """Reject a pending voice"""
    data = request.get_json()
    pending_id = data.get('pending_id')
    
    if not pending_id:
        return jsonify({'error': 'Missing pending_id'}), 400
    
    # TODO: Implement rejection logic
    # This would delete files from pending_active/
    
    return jsonify({'success': True})


# === Thing Engine API Routes ===

def get_thing_engine_commands() -> dict:
    """Load Thing Engine command queue"""
    return load_json(THING_ENGINE_COMMANDS_FILE, {'commands': []})


def save_thing_engine_commands(data: dict):
    """Save Thing Engine command queue"""
    save_json(THING_ENGINE_COMMANDS_FILE, data)


def queue_thing_engine_command(command_type: str, **kwargs) -> str:
    """Queue a Thing Engine command and return command ID"""
    import uuid
    
    commands_data = get_thing_engine_commands()
    
    command_id = f"cmd_{int(datetime.datetime.now().timestamp())}_{uuid.uuid4().hex[:8]}"
    
    command = {
        'id': command_id,
        'type': command_type,
        'status': 'pending',
        'timestamp': datetime.datetime.now().isoformat(),
        **kwargs
    }
    
    commands_data['commands'].append(command)
    save_thing_engine_commands(commands_data)
    
    return command_id


@app.route('/api/thing_engine/transform', methods=['POST'])
def thing_engine_transform():
    """Queue a transform (rename) operation"""
    data = request.get_json()
    person_id = data.get('person_id')
    new_name = data.get('new_name', '').strip()
    
    if not person_id or not new_name:
        return jsonify({'error': 'Missing person_id or new_name'}), 400
    
    # Verify person exists
    person_dir = Path(ENROLL_DIR) / person_id
    if not person_dir.exists():
        return jsonify({'error': 'Person not found'}), 404
    
    # Queue command
    command_id = queue_thing_engine_command(
        'transform',
        person_id=person_id,
        new_name=new_name
    )
    
    return jsonify({'success': True, 'command_id': command_id})


@app.route('/api/thing_engine/delete', methods=['POST'])
def thing_engine_delete():
    """Queue a delete operation"""
    data = request.get_json()
    person_id = data.get('person_id')
    
    if not person_id:
        return jsonify({'error': 'Missing person_id'}), 400
    
    # Verify person exists
    person_dir = Path(ENROLL_DIR) / person_id
    if not person_dir.exists():
        return jsonify({'error': 'Person not found'}), 404
    
    # Queue command
    command_id = queue_thing_engine_command(
        'delete',
        person_id=person_id
    )
    
    return jsonify({'success': True, 'command_id': command_id})


@app.route('/api/thing_engine/merge', methods=['POST'])
def thing_engine_merge():
    """Queue a merge operation"""
    data = request.get_json()
    source_ids = data.get('source_ids', [])
    new_name = data.get('new_name', '').strip()
    
    if len(source_ids) < 2:
        return jsonify({'error': 'At least 2 source identities required'}), 400
    
    if not new_name:
        return jsonify({'error': 'Missing new_name'}), 400
    
    # Verify all sources exist
    for source_id in source_ids:
        person_dir = Path(ENROLL_DIR) / source_id
        if not person_dir.exists():
            return jsonify({'error': f'Source identity not found: {source_id}'}), 404
    
    # Queue command
    command_id = queue_thing_engine_command(
        'merge',
        source_ids=source_ids,
        new_name=new_name
    )
    
    return jsonify({'success': True, 'command_id': command_id})


if __name__ == '__main__':
    print("=" * 60)
    print("VoiceBM Dashboard - LLM Voice Biometrics")
    print("by David M. Dryver Sr.")
    print("=" * 60)
    print(f"Dashboard URL: http://127.0.0.1:5000")
    print(f"Settings file: {SETTINGS_FILE}")
    print(f"Active state: {ACTIVE_STATE_FILE}")
    print(f"Pending: {PENDING_FILE}")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=5000, debug=True)
```


---


# Example `config.json` <a id="example-configjson"></a>

Built by the setup wizard from your answers (the wizard is the only way `config.json` is created — it is never hand-edited). Shown here with every component enabled so the full schema is visible. Replace the documentation IPs, placeholder credentials, and `/home/user` paths with your own.

```json
{
  "mqtt": {
    "broker": "192.0.2.10",
    "port": 1883,
    "user": "mqtt-user",
    "password": "CHANGE_ME"
  },
  "hosts": {
    "home_assistant": "192.0.2.10",
    "voicebm_host": "192.0.2.20"
  },
  "paths": {
    "voicebm_base": "/home/user/voicebm",
    "sherpa_bin": "/home/user/.local/bin/sherpa",
    "sherpa_model": "/home/user/sherpa_models/nemo_en_titanet_small.onnx",
    "conda_path": "/home/user/miniforge3",
    "python_bin": "/home/user/miniforge3/envs/vb/bin/python3"
  },
  "environment": {
    "type": "conda",
    "conda_path": "/home/user/miniforge3",
    "env_name": "vb",
    "venv_path": "",
    "python_bin": "/home/user/miniforge3/envs/vb/bin/python3"
  },
  "audio_server": {
    "host": "192.0.2.20",
    "port": 9090,
    "base_url": "http://192.0.2.20:9090"
  },
  "components": {
    "active": true,
    "passive": true,
    "ambient": true,
    "emote": true
  },
  "nodes": {
    "living": {
      "friendly_name": "Living Room",
      "rtsp_url": "rtsp://USER:PASS@192.0.2.30:554/Preview_01_main",
      "audio_filter": "",
      "recorder_enabled": true,
      "ambient_enabled": true
    }
  },
  "thresholds": {
    "passive": 0.22,
    "active": 0.5,
    "ambient_context": 0.18,
    "ambient_margin": 0.05
  },
  "voicebm": {
    "gallery_max": 75,
    "current_lead_trim_ms": 900,
    "embed_timeout_s": 30
  },
  "vad": {
    "speech_threshold": 0.6,
    "min_speech_ratio": 0.5,
    "min_speech_duration": 0.8
  },
  "ambient": {
    "cycle_s": 30,
    "mode": "attention",
    "ping_timeout_s": 5
  },
  "emote": {
    "ser_script": "/home/user/voicebm/bin/ser_infer.sh",
    "ser_timeout_s": 60
  }
}
```
