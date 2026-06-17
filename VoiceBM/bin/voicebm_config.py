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
import tempfile
import stat
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

# Default ID-injection switch state. True = ON (prepend identity tag to the
# transcript). config.json is the single source of truth for this switch so the
# dashboard and Home Assistant stay in sync across restarts.
DEFAULT_INJECT_IDENTITY = True

# Default transcript-preferred switch state. True = ON (publish the gate-enforced
# transcript to voicebm/transcript/preferred). Turn OFF to keep bridge-driven
# speech out of the preferred topic (the debug topic is never gated). config.json
# is the single source of truth so the dashboard and HA stay in sync.
DEFAULT_TRANSCRIPT_PREFERRED = True


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


def get_inject_identity():
    """
    ID-injection switch state.

    Read from config.json -> voicebm.inject_identity. Falls back to
    DEFAULT_INJECT_IDENTITY if unset or invalid. config.json is the single
    source of truth shared by the dashboard and Home Assistant.

    Returns:
        bool: True if identity injection is ON
    """
    try:
        return bool(get_voicebm_config().get('inject_identity', DEFAULT_INJECT_IDENTITY))
    except:
        return DEFAULT_INJECT_IDENTITY


def get_transcript_preferred():
    """
    Transcript-preferred switch state.

    Read from config.json -> voicebm.transcript_preferred. Falls back to
    DEFAULT_TRANSCRIPT_PREFERRED if unset or invalid. config.json is the single
    source of truth shared by the dashboard and Home Assistant.

    Returns:
        bool: True if the preferred transcript topic should be published
    """
    try:
        return bool(get_voicebm_config().get('transcript_preferred', DEFAULT_TRANSCRIPT_PREFERRED))
    except:
        return DEFAULT_TRANSCRIPT_PREFERRED


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

    Used by the HA number entities (Gallery Max, Active Lead Trim) and the
    dashboard/HA switches so a change persists across restarts. Reads-modifies-
    writes the whole file to preserve every other setting. Returns True on success.

    The write is ATOMIC: the new content is written to a temp file in the same
    directory and then os.replace()'d over config.json. os.replace is atomic on
    POSIX, so a reader always sees either the complete old file or the complete
    new file — never a truncated or half-written one. This prevents the
    config.json corruption that a plain open('w')+dump can cause if the process
    is interrupted mid-write or two writers overlap.

    Args:
        key: e.g. 'gallery_max', 'active_lead_trim_ms', 'inject_identity'
        value: value to store
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

        # Atomic write: temp file in the same dir, fsync, then atomic rename.
        # Preserve the original file's permissions — mkstemp creates 0600, and
        # os.replace keeps the temp file's mode, which would silently strip
        # config.json from world-readable (644) down to owner-only (600) and
        # lock out any service/user that reads it. Copy the existing mode (or
        # default to 0644 on first create) onto the temp file before the swap.
        dir_name = config_file.parent
        try:
            prev_mode = stat.S_IMODE(os.stat(config_file).st_mode)
        except OSError:
            prev_mode = 0o644
        fd, tmp_path = tempfile.mkstemp(prefix=".config.", suffix=".tmp", dir=str(dir_name))
        try:
            with os.fdopen(fd, 'w') as f:
                json.dump(config, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.chmod(tmp_path, prev_mode)
            os.replace(tmp_path, str(config_file))
        except Exception:
            # Clean up the temp file if the swap didn't happen
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
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
