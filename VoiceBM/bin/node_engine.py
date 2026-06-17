#!/usr/bin/env python3
"""
VoiceBM Node Engine - Node Identity Transformation
Renames a node's friendly_name (mutable display context) while node_id
(the immutable identity) never changes.

node_id is the node's biology: it lives in topics, directories, and device
identifiers, and never changes. friendly_name is display context for HA and
the LLM. This engine mutates ONLY friendly_name in config.json, then
delegates republish to the services that own the node's entities.

LLM Voice Biometrics by David M. Dryver Sr.
"""

import sys
import json
import time
import datetime
import subprocess
import re
from pathlib import Path
import paho.mqtt.client as mqtt

# Load configuration
sys.path.insert(0, '/home/user/voicebm')
from voicebm_config import get_mqtt_config

# ============================================================================
# CONFIGURATION
# ============================================================================

VOICEBM_BASE = Path("/home/user/voicebm")
CONFIG_FILE = VOICEBM_BASE / "config.json"
LOGS_DIR = VOICEBM_BASE / "logs"
NODE_LOG = LOGS_DIR / "node_engine.log"

mqtt_config = get_mqtt_config()
MQTT_BROKER = mqtt_config['broker']
MQTT_PORT = mqtt_config['port']

# MQTT Topics
TOPIC_TRANSFORM_PREFIX = "voicebm/node/transform"      # .../{node_id}/name(/set), .../{node_id}/execute
TOPIC_STATUS = "voicebm/node/transform/status"          # retained JSON status (MQTT topic, no HA sensor)

DISCOVERY_PREFIX = "homeassistant"

# First-run detection marker
DISCOVERY_INITIALIZED_FILE = VOICEBM_BASE / "meta" / "discovery_initialized_node_engine"

# Staged names: node_id -> new friendly_name (set by text input, used by button)
transform_names = {}


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
    print("  Marked Node Engine discovery as initialized")


def log_operation(operation: str, details: dict):
    """Log Node Engine operations to file"""
    LOGS_DIR.mkdir(exist_ok=True)

    log_entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "operation": operation,
        **details
    }

    with open(NODE_LOG, 'a') as f:
        f.write(json.dumps(log_entry) + "\n")

    print(f"[NODE ENGINE] {operation}: {details}")


def validate_friendly_name(name: str) -> tuple[bool, str]:
    """
    Validate a friendly name. Same grammar as the Thing Engine's validator:
    letters, digits, spaces, hyphens, underscores; starts and ends with a letter.
    """
    if not name:
        return False, "Name cannot be empty"

    if len(name) > 100:
        return False, "Name too long (max 100 characters)"

    if not name[0].isalpha():
        return False, "Name must start with a letter"
    if not name[-1].isalpha():
        return False, "Name must end with a letter"

    if not re.match(r'^[A-Za-z][A-Za-z0-9\s\-_]*[A-Za-z]$', name):
        return False, "Name can only contain letters, digits, spaces, hyphens, and underscores"

    return True, ""


def load_config() -> dict:
    """Load config.json (single source of truth)."""
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)


def write_config_atomic(cfg: dict):
    """
    Atomic config.json write: temp file in the same directory, then replace.
    A crash mid-write can never leave a truncated config behind.
    """
    tmp = CONFIG_FILE.with_suffix('.json.tmp')
    with open(tmp, 'w') as f:
        json.dump(cfg, f, indent=2)
        f.write('\n')
    tmp.replace(CONFIG_FILE)


def get_nodes() -> dict:
    """nodes block from config.json: node_id -> node settings."""
    try:
        return load_config().get('nodes', {}) or {}
    except Exception as e:
        print(f"[NODE ENGINE] Failed to read config.json: {e}")
        return {}


def node_friendly(node: dict, node_id: str) -> str:
    """Display name for a node, with the same fallback the publishers use."""
    return node.get('friendly_name', node_id.replace('_', ' ').title())


def restart_service(unit: str) -> bool:
    """
    Restart one systemd unit so it republishes discovery with the new name.
    Same delegation pattern (and tolerance) as the Thing Engine's
    enrollment_watcher restart.
    """
    try:
        result = subprocess.run(
            ['systemctl', 'restart', unit],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            print(f"[NODE ENGINE] ✓ Restarted {unit}")
            return True
        print(f"[NODE ENGINE] ⚠️  Failed to restart {unit}: {result.stderr.strip()}")
        return False
    except subprocess.TimeoutExpired:
        print(f"[NODE ENGINE] ⚠️  Restart timed out: {unit}")
        return False
    except Exception as e:
        print(f"[NODE ENGINE] ⚠️  Error restarting {unit}: {e}")
        return False


def owning_units_for(node_id: str) -> list:
    """
    The services that publish this node's device and must republish after a
    rename. Ambient owns device configs for every ambient node; recorder
    nodes additionally have a per-node passive publisher and cluster entities.
    Only units that actually exist on the box are returned.
    """
    units = []
    candidates = [
        f"voicebm-publisher-{node_id}.service",
        "voicebm-cluster-publisher.service",
        "voicebm-ambient.service",
    ]
    # cluster publisher only matters when this node has a passive publisher
    has_publisher = Path(f"/etc/systemd/system/voicebm-publisher-{node_id}.service").exists()
    for unit in candidates:
        if unit == "voicebm-cluster-publisher.service" and not has_publisher:
            continue
        if Path(f"/etc/systemd/system/{unit}").exists():
            units.append(unit)
    return units


def publish_status(client, payload: dict):
    payload["timestamp"] = datetime.datetime.now().isoformat()
    client.publish(TOPIC_STATUS, json.dumps(payload), qos=1, retain=True)


# ============================================================================
# TRANSFORM OPERATION (Rename Node)
# ============================================================================

def transform_node(client, node_id: str, new_friendly_name: str) -> tuple[bool, str]:
    """
    Rename a node's friendly_name. node_id never changes.

    Steps:
    1. Validate node exists and name is valid
    2. Update nodes.{node_id}.friendly_name in config.json (atomic)
    3. Restart the services that own this node's entities (they read
       friendly_name from config at startup and republish discovery)
    4. Republish this engine's own entities with the new device name
    5. Log operation
    """
    print(f"\n[TRANSFORM] Renaming node '{node_id}' to '{new_friendly_name}'")

    nodes = get_nodes()
    if node_id not in nodes:
        error = f"Node '{node_id}' does not exist in config.json"
        log_operation("transform_failed", {"node_id": node_id, "new_name": new_friendly_name, "error": error})
        return False, error

    is_valid, error_msg = validate_friendly_name(new_friendly_name)
    if not is_valid:
        log_operation("transform_failed", {"node_id": node_id, "new_name": new_friendly_name, "error": error_msg})
        return False, error_msg

    old_friendly = node_friendly(nodes[node_id], node_id)
    if new_friendly_name == old_friendly:
        message = f"Node '{node_id}' is already named '{old_friendly}' — nothing to do"
        log_operation("transform_noop", {"node_id": node_id, "name": old_friendly})
        return True, message

    try:
        # 1. Mutate exactly one key in config.json, atomically
        cfg = load_config()
        cfg['nodes'][node_id]['friendly_name'] = new_friendly_name
        write_config_atomic(cfg)
        print(f"  ✓ config.json: nodes.{node_id}.friendly_name = '{new_friendly_name}'")

        # 2. Delegate republish to the owning services
        restarted = []
        for unit in owning_units_for(node_id):
            if restart_service(unit):
                restarted.append(unit)
        if restarted:
            time.sleep(3)  # give them time to republish device configs

        # 3. Republish this engine's own entities with the corrected device name
        publish_node_engine_entities(client, node_id, new_friendly_name)

        log_operation("transform_success", {
            "node_id": node_id,
            "old_name": old_friendly,
            "new_name": new_friendly_name,
            "restarted": restarted
        })

        print(f"  ✓ Transform complete: '{old_friendly}' -> '{new_friendly_name}' (node_id '{node_id}' unchanged)")
        return True, f"Renamed to '{new_friendly_name}'"

    except Exception as e:
        error = f"Transform failed: {str(e)}"
        log_operation("transform_error", {"node_id": node_id, "new_name": new_friendly_name, "error": str(e)})
        return False, error


# ============================================================================
# MQTT HANDLERS
# ============================================================================

def handle_transform_name_input(client, userdata, msg):
    """Stage a new name for a node (text input). Nothing executes here."""
    global transform_names

    try:
        # Topic: voicebm/node/transform/{node_id}/name/set
        parts = msg.topic.split('/')
        node_id = parts[3]
        new_name = msg.payload.decode('utf-8').strip()

        transform_names[node_id] = new_name

        # Echo back to state topic
        client.publish(f"{TOPIC_TRANSFORM_PREFIX}/{node_id}/name", new_name, qos=1, retain=True)
        print(f"[TRANSFORM NAME] {node_id} -> {new_name}")

    except Exception as e:
        print(f"[TRANSFORM NAME] Error: {e}")


def handle_transform_execute(client, userdata, msg):
    """Execute the rename using the staged name (button press)."""
    global transform_names

    try:
        # Topic: voicebm/node/transform/{node_id}/execute
        parts = msg.topic.split('/')
        node_id = parts[3]

        new_friendly_name = transform_names.get(node_id, "").strip()

        if not new_friendly_name:
            print(f"[TRANSFORM] No name staged for {node_id}")
            publish_status(client, {
                "operation": "node_transform",
                "node_id": node_id,
                "success": False,
                "message": "Please enter a new name first"
            })
            return

        success, message = transform_node(client, node_id, new_friendly_name)

        # Clear staged name on success
        if success:
            transform_names.pop(node_id, None)
            client.publish(f"{TOPIC_TRANSFORM_PREFIX}/{node_id}/name", "", qos=1, retain=True)

        publish_status(client, {
            "operation": "node_transform",
            "node_id": node_id,
            "success": success,
            "message": message
        })

    except Exception as e:
        print(f"[TRANSFORM EXECUTE] Error: {e}")


# ============================================================================
# DISCOVERY
# ============================================================================

def publish_node_engine_entities(client, node_id: str, friendly: str):
    """
    Publish the rename controls for one node, attached to the node's EXISTING
    device. The device block matches publish_identity_node exactly
    (identifiers ["voicebm_{node_id}"]) so these entities appear inside the
    node's own device area — never under the global device.
    """
    device = {
        "identifiers": [f"voicebm_{node_id}"],
        "name": f"Voice Biometrics {friendly}",
        "manufacturer": "David M. Dryver Sr.",
        "model": "Home Assistant Voice Biometrics",
        "sw_version": "2.0"
    }

    # New Node Name text input
    name_config = {
        "name": "New Node Name",
        "unique_id": f"voicebm_{node_id}_transform_name",
        "command_topic": f"{TOPIC_TRANSFORM_PREFIX}/{node_id}/name/set",
        "state_topic": f"{TOPIC_TRANSFORM_PREFIX}/{node_id}/name",
        "mode": "text",
        "icon": "mdi:rename-box",
        "device": device
    }
    client.publish(
        f"{DISCOVERY_PREFIX}/text/voicebm_{node_id}_transform_name/config",
        json.dumps(name_config),
        qos=1,
        retain=True
    )

    # Rename Node button
    button_config = {
        "name": "Rename Node",
        "unique_id": f"voicebm_{node_id}_transform_execute",
        "command_topic": f"{TOPIC_TRANSFORM_PREFIX}/{node_id}/execute",
        "payload_press": "PRESS",
        "icon": "mdi:home-edit",
        "device": device
    }
    client.publish(
        f"{DISCOVERY_PREFIX}/button/voicebm_{node_id}_transform_execute/config",
        json.dumps(button_config),
        qos=1,
        retain=True
    )


def scan_and_publish_node_entities(client, first_run: bool):
    """Publish rename controls for every node in config.json."""
    nodes = get_nodes()
    if not nodes:
        print("[NODE ENGINE] No nodes found in config.json")
        return

    for node_id, node in nodes.items():
        friendly = node_friendly(node, node_id)
        publish_node_engine_entities(client, node_id, friendly)
        # Initialize name state only on first run; afterwards respect retained state
        if first_run:
            client.publish(f"{TOPIC_TRANSFORM_PREFIX}/{node_id}/name", "", qos=1, retain=True)
        print(f"[NODE ENGINE] ✓ Published rename controls for: {friendly} ({node_id})")

    print(f"[NODE ENGINE] Published entities for {len(nodes)} nodes")


def on_connect(client, userdata, flags, reason_code, properties):
    """MQTT connection callback"""
    if reason_code == 0:
        print("[NODE ENGINE] Connected to MQTT broker")

        # Subscribe to command topics
        client.subscribe(f"{TOPIC_TRANSFORM_PREFIX}/+/name/set")
        client.subscribe(f"{TOPIC_TRANSFORM_PREFIX}/+/execute")

        first_run = is_first_run()
        if first_run:
            print("[NODE ENGINE] First run detected - will publish initial states")
            publish_status(client, {"status": "ready", "message": "Ready"})
        else:
            print("[NODE ENGINE] Subsequent run - respecting HA state")

        scan_and_publish_node_entities(client, first_run)

        if first_run:
            mark_initialized()

        print("[NODE ENGINE] Subscriptions active")
        print(f"  - Name inputs:  {TOPIC_TRANSFORM_PREFIX}/+/name/set")
        print(f"  - Rename buttons: {TOPIC_TRANSFORM_PREFIX}/+/execute")
    else:
        print(f"[NODE ENGINE] Connection failed with reason code {reason_code}")


def on_message(client, userdata, msg):
    """MQTT message router"""
    try:
        topic = msg.topic

        if topic.startswith(TOPIC_TRANSFORM_PREFIX) and topic.endswith("/name/set"):
            handle_transform_name_input(client, userdata, msg)
        elif topic.startswith(TOPIC_TRANSFORM_PREFIX) and topic.endswith("/execute"):
            handle_transform_execute(client, userdata, msg)
    except Exception as e:
        print(f"[NODE ENGINE] Message handler error: {e}")


# ============================================================================
# MAIN
# ============================================================================

def main():
    """Main Node Engine service loop"""
    print("=" * 70)
    print("VoiceBM Node Engine - Node Identity Transformation")
    print("LLM Voice Biometrics by David M. Dryver Sr.")
    print("=" * 70)
    print(f"Config: {CONFIG_FILE}")
    print(f"Logs directory: {LOGS_DIR}")
    print(f"MQTT Broker: {MQTT_BROKER}:{MQTT_PORT}")
    print()

    LOGS_DIR.mkdir(exist_ok=True)

    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    if mqtt_config.get('user') and mqtt_config.get('password'):
        client.username_pw_set(mqtt_config['user'], mqtt_config['password'])
    client.on_connect = on_connect
    client.on_message = on_message

    print(f"Connecting to MQTT broker at {MQTT_BROKER}:{MQTT_PORT}...")
    client.connect(MQTT_BROKER, MQTT_PORT, 60)

    print("Node Engine running. Press Ctrl+C to stop.")
    print()

    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print("\n[NODE ENGINE] Shutting down...")
        client.disconnect()


if __name__ == "__main__":
    main()
