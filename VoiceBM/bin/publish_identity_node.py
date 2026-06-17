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
