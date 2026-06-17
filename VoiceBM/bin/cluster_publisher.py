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
