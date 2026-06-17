#!/usr/bin/env python3
"""
VoiceBM Recording Cleanup - Delete expired WAV files after 3-day retention period

PURPOSE:
- WAV files take up space, keep them for 3 days for manual review
- After 3 days, delete the WAV but keep the embedding
- Embeddings stay forever (small files, needed for recognition)

BEHAVIOR:
- Scans all person folders in /enroll/
- Reads metadata.json for each person
- Checks expire_at timestamp for each sample
- Deletes WAV if past expiration
- Updates metadata to mark recording as deleted
- Keeps embedding file

RUN AS:
- Systemd timer (daily)
- Or cron job: 0 2 * * * /home/user/voicebm/bin/cleanup_recordings.py
"""

import os
import json
import datetime
from pathlib import Path

ENROLL_DIR = "/home/user/voicebm/enroll"


def cleanup_expired_recordings():
    """
    Delete WAV files past their 3-day retention period.
    Keep embeddings forever.
    """
    enroll_path = Path(ENROLL_DIR)
    
    if not enroll_path.exists():
        print(f"Enrollment directory not found: {ENROLL_DIR}")
        return
    
    total_deleted = 0
    total_kept = 0
    
    print(f"Starting cleanup scan: {datetime.datetime.now().isoformat()}")
    print(f"Scanning: {ENROLL_DIR}\n")
    
    # Scan each person folder
    for person_dir in enroll_path.iterdir():
        if not person_dir.is_dir():
            continue
        
        person_id = person_dir.name
        metadata_file = person_dir / 'metadata.json'
        
        if not metadata_file.exists():
            print(f"âš  No metadata for {person_id}, skipping")
            continue
        
        # Load metadata
        try:
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)
        except Exception as e:
            print(f"âœ— Failed to load metadata for {person_id}: {e}")
            continue
        
        samples = metadata.get('samples', [])
        if not samples:
            continue
        
        print(f"Checking {person_id} ({len(samples)} samples)...")
        
        updated_samples = []
        person_deleted = 0
        person_kept = 0
        
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        
        for sample in samples:
            expire_at = sample.get('expire_at')
            recording_path = sample.get('recording')
            
            # If already marked as deleted, keep as-is
            if recording_path is None:
                updated_samples.append(sample)
                continue
            
            # If no expiration, keep forever
            if not expire_at:
                updated_samples.append(sample)
                person_kept += 1
                continue
            
            # Parse expiration timestamp
            try:
                # Handle ISO format with 'Z' suffix
                expire_dt = datetime.datetime.fromisoformat(expire_at.replace('Z', '+00:00'))
            except Exception as e:
                print(f"  âš  Invalid expire_at for {sample['event_id']}: {e}")
                updated_samples.append(sample)
                person_kept += 1
                continue
            
            # Check if expired
            if now_utc > expire_dt:
                # Delete WAV file
                wav_file = person_dir / recording_path
                
                if wav_file.exists():
                    try:
                        wav_file.unlink()
                        print(f"  âœ“ Deleted: {wav_file.name}")
                        person_deleted += 1
                    except Exception as e:
                        print(f"  âœ— Failed to delete {wav_file.name}: {e}")
                        updated_samples.append(sample)
                        person_kept += 1
                        continue
                else:
                    print(f"  âš  Already gone: {wav_file.name}")
                    person_deleted += 1
                
                # Update sample to mark recording as deleted
                sample['recording'] = None
                sample['recording_deleted_at'] = now_utc.isoformat()
                updated_samples.append(sample)
            else:
                # Not expired yet, keep it
                time_left = expire_dt - now_utc
                days_left = time_left.days
                # Don't print for every file, just count
                updated_samples.append(sample)
                person_kept += 1
        
        if person_deleted > 0:
            print(f"  Deleted {person_deleted} recording(s), kept {person_kept}")
        
        # Save updated metadata
        metadata['samples'] = updated_samples
        metadata['last_cleanup'] = now_utc.isoformat()
        
        try:
            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)
        except Exception as e:
            print(f"  âœ— Failed to save metadata: {e}")
        
        total_deleted += person_deleted
        total_kept += person_kept
    
    print(f"\nCleanup complete:")
    print(f"  Deleted: {total_deleted} recording(s)")
    print(f"  Kept: {total_kept} recording(s)")
    print(f"  Time: {datetime.datetime.now().isoformat()}")


if __name__ == "__main__":
    cleanup_expired_recordings()
