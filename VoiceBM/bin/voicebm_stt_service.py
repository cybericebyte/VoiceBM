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


def _read_person_overrides_file():
    """Read per-person threshold overrides from thresholds.json (PERSON_OVERRIDES).
    This is the file the dashboard writes to (no broker required). Returns a dict
    {person_id: threshold}. Empty on any error."""
    try:
        if os.path.exists(THRESHOLD_FILE):
            with open(THRESHOLD_FILE, "r") as f:
                data = json.load(f)
            ov = data.get("PERSON_OVERRIDES", {})
            if isinstance(ov, dict):
                return ov
    except Exception:
        pass
    return {}


def _write_person_override_file(person_id, threshold):
    """Write/update one person's override in PERSON_OVERRIDES of thresholds.json.
    Atomic (temp + os.replace), preserving every other key (MATCH_T_ACTIVE,
    GALLERY_MAX, other people's overrides)."""
    try:
        if os.path.exists(THRESHOLD_FILE):
            with open(THRESHOLD_FILE, "r") as f:
                data = json.load(f)
        else:
            data = {}
    except Exception:
        data = {}
    overrides = data.get("PERSON_OVERRIDES", {})
    if not isinstance(overrides, dict):
        overrides = {}
    overrides[person_id] = threshold
    data["PERSON_OVERRIDES"] = overrides
    try:
        os.makedirs(os.path.dirname(THRESHOLD_FILE), exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(prefix=".thresholds.", suffix=".tmp",
                                        dir=os.path.dirname(THRESHOLD_FILE))
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, THRESHOLD_FILE)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except Exception as e:
        print(f"Failed to write person override for {person_id}: {e}")


def resolve_person_threshold(person_id):
    """Resolve a person's custom threshold from BOTH sources, FILE FIRST:
      - the PERSON_OVERRIDES map in thresholds.json (dashboard file path), and
      - the in-memory person_thresholds dict (live MQTT/HA path) as fallback.

    The file wins when it has an entry for this person, because the file is the
    channel the dashboard can write with no broker. The HA MQTT handler also
    writes the file, so both paths converge there; the in-memory dict is only the
    fallback for a value that hasn't been persisted to the file yet. Returns the
    float override or None.
    """
    file_ov = _read_person_overrides_file()
    if person_id in file_ov:
        try:
            return float(file_ov[person_id])
        except (TypeError, ValueError):
            pass
    if person_id in person_thresholds:
        return person_thresholds[person_id]
    return None


def get_person_threshold(person_id, global_threshold):
    """
    Get threshold for a specific person.

    Returns per-person threshold if set (from either the live MQTT cache or the
    dashboard-written file), otherwise returns global threshold.

    Args:
        person_id: Person identifier
        global_threshold: Fallback global threshold

    Returns:
        Threshold value to use for this person
    """
    custom = resolve_person_threshold(person_id)
    if custom is not None:
        print(f"  Using custom threshold for {person_id}: {custom:.2f}")
        return custom
    return global_threshold


def verify_person_threshold(speaker_id, confidence, global_threshold):
    """
    Verify that identified speaker meets their custom threshold (if set).

    If person has custom threshold and confidence doesn't meet it,
    returns None (treat as unknown). The override is resolved from both the
    live MQTT cache and the dashboard-written file.

    Args:
        speaker_id: Identified speaker ID
        confidence: Confidence score from identification
        global_threshold: Global threshold used for initial identification

    Returns:
        speaker_id if threshold met, None if custom threshold not met
    """
    if speaker_id is None:
        return None

    custom_threshold = resolve_person_threshold(speaker_id)
    if custom_threshold is not None:
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

        # Also persist to PERSON_OVERRIDES in thresholds.json so the file (which
        # the resolver reads first) stays consistent with HA-set values, survives
        # restart, and is visible to the dashboard. Two writers, one file.
        _write_person_override_file(person_id, new_threshold)

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
