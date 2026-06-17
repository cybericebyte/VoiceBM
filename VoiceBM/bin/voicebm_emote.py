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
