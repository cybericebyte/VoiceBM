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
