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
