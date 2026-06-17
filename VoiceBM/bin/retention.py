#!/usr/bin/env python3
"""
VoiceBM Retention Service - Clean up expired WAV and embedding files

RULES:
- Reads passive rooms from config.json rooms where recorder_enabled=true
- On startup: immediately sweep all rooms before entering loop
- Age-based: delete WAV+embedding pairs older than RETENTION_SECONDS
- Volume-based: if file count exceeds MAX_FILES, cycle out oldest regardless of age
- Enrolled files: WAV expires after 3 days, embedding stays PERMANENT (in enroll folder)

Files in recordings/{room} and embeddings/{room} are TEMPORARY.
Only files MOVED to enroll/{person}/ are permanent.
"""

import os
import json
import time
import datetime
import pathlib

CONFIG_FILE = "/home/user/voicebm/config.json"
META_LAB    = "/home/user/voicebm/meta/labeled"
ENROLL_DIR  = "/home/user/voicebm/enroll"

RETENTION_SECONDS = 3 * 24 * 3600  # 3 days
MAX_FILES         = 5000            # volume cap per room — matches recorder safety limit
SWEEP_INTERVAL    = 60              # seconds between sweeps


def load_config():
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)


def get_passive_rooms(config):
    """Return list of room names with recorder_enabled=true from config."""
    rooms = []
    for room_name, room_cfg in config.get("rooms", {}).items():
        if room_cfg.get("recorder_enabled", False):
            rooms.append(room_name)
    return rooms


def get_voicebm_base(config):
    return config.get("paths", {}).get("voicebm_base", "/home/user/voicebm")


def now():
    return int(time.time())


def parse_expire(sidecar):
    """Parse expiration timestamp from labeled sidecar JSON."""
    try:
        with open(sidecar, 'r') as f:
            j = json.load(f)
            expire_str = j.get("expire_at")
            if expire_str:
                return int(datetime.datetime.strptime(
                    expire_str, "%Y-%m-%dT%H:%M:%SZ").timestamp())
    except:
        pass
    return None


def is_enrolled(eid):
    """Check if an event ID has been enrolled to any person."""
    enroll_path = pathlib.Path(ENROLL_DIR)
    if not enroll_path.exists():
        return False
    for person_dir in enroll_path.iterdir():
        if not person_dir.is_dir():
            continue
        emb_file = person_dir / "embeddings" / f"{eid}.txt"
        if emb_file.exists():
            return True
    return False


def delete_file(path, file_type):
    """Delete a file and log result."""
    try:
        if os.path.exists(path):
            os.remove(path)
            print(f"  ✔ Deleted {file_type}: {os.path.basename(path)}")
            return True
    except Exception as e:
        print(f"  ✗ Failed to delete {file_type}: {e}")
    return False


def sweep_room(room, voicebm_base):
    """
    Sweep one room's recordings and embeddings.
    1. Delete age-expired unenrolled files.
    2. If file count still exceeds MAX_FILES, cycle out oldest until under limit.
    """
    rec_path = pathlib.Path(voicebm_base) / "recordings" / room
    emb_path = pathlib.Path(voicebm_base) / "embeddings" / room

    if not rec_path.exists():
        return

    emb_path.mkdir(parents=True, exist_ok=True)

    current      = now()
    deleted_wav  = 0
    deleted_emb  = 0

    # ── Pass 1: Age-based cleanup ─────────────────────────────────────────
    for wav in list(rec_path.glob("*.wav")):
        eid = wav.stem

        if is_enrolled(eid):
            continue

        sidecar      = os.path.join(META_LAB, f"{eid}.json")
        should_delete = False

        if os.path.exists(sidecar):
            exp = parse_expire(sidecar)
            if exp and current > exp:
                should_delete = True
        else:
            try:
                mtime = int(wav.stat().st_mtime)
                if current - mtime > RETENTION_SECONDS:
                    should_delete = True
            except:
                pass

        if should_delete:
            print(f"[{room}] Age expiry: {eid}")
            if delete_file(str(wav), "WAV"):
                deleted_wav += 1
            emb_file = emb_path / f"{eid}.txt"
            if delete_file(str(emb_file), "EMB"):
                deleted_emb += 1
            if os.path.exists(sidecar):
                delete_file(sidecar, "sidecar")

    # ── Pass 2: Volume cap — cycle out oldest until under MAX_FILES ───────
    wav_files = sorted(
        rec_path.glob("*.wav"),
        key=lambda f: f.stat().st_mtime
    )
    file_count = len(wav_files)

    TARGET_FILES = MAX_FILES // 2  # clean to half cap for breathing room
    if file_count >= MAX_FILES:
        overage = file_count - TARGET_FILES
        print(f"[{room}] Volume cap exceeded ({file_count}/{MAX_FILES}) — cycling out {overage} oldest files (target: {TARGET_FILES})")
        for wav in wav_files[:overage]:
            eid = wav.stem
            if is_enrolled(eid):
                continue
            print(f"[{room}] Volume evict: {eid}")
            if delete_file(str(wav), "WAV"):
                deleted_wav += 1
            emb_file = emb_path / f"{eid}.txt"
            if delete_file(str(emb_file), "EMB"):
                deleted_emb += 1
            sidecar = os.path.join(META_LAB, f"{eid}.json")
            if os.path.exists(sidecar):
                delete_file(sidecar, "sidecar")

    # ── Pass 3: Orphan embeddings (no matching WAV, old enough) ──────────
    if emb_path.exists():
        for emb in emb_path.glob("*.txt"):
            eid = emb.stem
            wav_file = rec_path / f"{eid}.wav"
            if is_enrolled(eid):
                continue
            if not wav_file.exists():
                try:
                    mtime = int(emb.stat().st_mtime)
                    if current - mtime > RETENTION_SECONDS:
                        print(f"[{room}] Orphan embedding: {eid}")
                        if delete_file(str(emb), "orphan EMB"):
                            deleted_emb += 1
                except:
                    pass

    if deleted_wav > 0 or deleted_emb > 0:
        print(f"[{room}] Sweep complete: {deleted_wav} WAVs, {deleted_emb} embeddings deleted")


def load_pending_ids(voicebm_base):
    """Return the set of pending IDs currently in the live pending.json buffer.
    These are surfaced-for-enrollment entries and must NOT be swept — they are
    waiting on the user to enroll or reject them. Any pending file NOT in this
    set is accumulated cruft (already enrolled, rejected, or aged out of the
    buffer) and is safe to age/volume-expire."""
    pending_json = pathlib.Path(voicebm_base) / "pending_active" / "pending.json"
    ids = set()
    try:
        if pending_json.exists():
            with open(pending_json, 'r') as f:
                data = json.load(f)
            # pending.json is a raw list of entries (each with an "id").
            entries = data if isinstance(data, list) else data.get("entries", [])
            for e in entries:
                if isinstance(e, dict) and e.get("id"):
                    ids.add(e["id"])
    except Exception as e:
        # On any read error, return empty — better to sweep nothing this cycle
        # than to risk deleting a buffered file we couldn't confirm.
        print(f"[pending] Could not read pending.json ({e}); skipping sweep this cycle")
        return None
    return ids


def sweep_pending(voicebm_base):
    """
    Sweep pending_active recordings and embeddings — same age + volume + orphan
    passes as sweep_room, but protects any file still in the live pending.json
    buffer. Pending files are flat (pending_active/recordings/{id}.wav,
    pending_active/embeddings/{id}.txt); there are no labeled sidecars here.
    """
    rec_path = pathlib.Path(voicebm_base) / "pending_active" / "recordings"
    emb_path = pathlib.Path(voicebm_base) / "pending_active" / "embeddings"

    if not rec_path.exists():
        return

    emb_path.mkdir(parents=True, exist_ok=True)

    # Buffer protection. If we can't read the buffer, skip this cycle entirely
    # rather than risk deleting a surfaced entry.
    buffered = load_pending_ids(voicebm_base)
    if buffered is None:
        return

    current     = now()
    deleted_wav = 0
    deleted_emb = 0

    # ── Pass 1: Age-based cleanup ─────────────────────────────────────────
    for wav in list(rec_path.glob("*.wav")):
        eid = wav.stem
        if eid in buffered:
            continue  # live in buffer — surfaced for enrollment, do not touch
        if is_enrolled(eid):
            continue
        try:
            mtime = int(wav.stat().st_mtime)
            if current - mtime > RETENTION_SECONDS:
                print(f"[pending] Age expiry: {eid}")
                if delete_file(str(wav), "WAV"):
                    deleted_wav += 1
                emb_file = emb_path / f"{eid}.txt"
                if delete_file(str(emb_file), "EMB"):
                    deleted_emb += 1
        except:
            pass

    # ── Pass 2: Volume cap — cycle out oldest until under MAX_FILES ───────
    wav_files = sorted(rec_path.glob("*.wav"), key=lambda f: f.stat().st_mtime)
    file_count = len(wav_files)
    TARGET_FILES = MAX_FILES // 2
    if file_count >= MAX_FILES:
        overage = file_count - TARGET_FILES
        print(f"[pending] Volume cap exceeded ({file_count}/{MAX_FILES}) — cycling out {overage} oldest files (target: {TARGET_FILES})")
        for wav in wav_files[:overage]:
            eid = wav.stem
            if eid in buffered:
                continue
            if is_enrolled(eid):
                continue
            print(f"[pending] Volume evict: {eid}")
            if delete_file(str(wav), "WAV"):
                deleted_wav += 1
            emb_file = emb_path / f"{eid}.txt"
            if delete_file(str(emb_file), "EMB"):
                deleted_emb += 1

    # ── Pass 3: Orphan embeddings (no matching WAV, old enough) ──────────
    if emb_path.exists():
        for emb in emb_path.glob("*.txt"):
            eid = emb.stem
            if eid in buffered:
                continue
            if is_enrolled(eid):
                continue
            wav_file = rec_path / f"{eid}.wav"
            if not wav_file.exists():
                try:
                    mtime = int(emb.stat().st_mtime)
                    if current - mtime > RETENTION_SECONDS:
                        print(f"[pending] Orphan embedding: {eid}")
                        if delete_file(str(emb), "orphan EMB"):
                            deleted_emb += 1
                except:
                    pass

    if deleted_wav > 0 or deleted_emb > 0:
        print(f"[pending] Sweep complete: {deleted_wav} WAVs, {deleted_emb} embeddings deleted")


def sweep_all(rooms, voicebm_base):
    for room in rooms:
        sweep_room(room, voicebm_base)
    # Active-side pending buffer files get the same retention treatment as nodes.
    sweep_pending(voicebm_base)


def main():
    config       = load_config()
    rooms        = get_passive_rooms(config)
    voicebm_base = get_voicebm_base(config)

    print("=" * 60)
    print("VoiceBM Retention Service")
    print("=" * 60)
    print(f"Base: {voicebm_base}")
    print(f"Rooms: {rooms}")
    print(f"Retention: {RETENTION_SECONDS // 3600} hours")
    print(f"Volume cap: {MAX_FILES} files per room")
    print(f"Pending active: swept with same retention (buffer-protected)")
    print("=" * 60)

    # Sweep immediately on startup
    print("Running startup sweep...")
    sweep_all(rooms, voicebm_base)
    print("Startup sweep complete — recorders will resume automatically once volume is clear.")

    print(f"Running retention sweep every {SWEEP_INTERVAL} seconds...")
    print("Press Ctrl+C to exit\n")

    while True:
        try:
            sweep_all(rooms, voicebm_base)
            time.sleep(SWEEP_INTERVAL)
        except KeyboardInterrupt:
            print("\nShutting down...")
            break
        except Exception as e:
            print(f"Error in sweep: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
