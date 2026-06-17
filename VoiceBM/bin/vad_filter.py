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
