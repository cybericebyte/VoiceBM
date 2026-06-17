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
