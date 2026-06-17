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
