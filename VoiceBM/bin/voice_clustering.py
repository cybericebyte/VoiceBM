#!/usr/bin/env python3
"""Voice Clustering - Groups similar unprocessed voice embeddings for batch enrollment"""

import os
import json
import numpy as np
from pathlib import Path
from collections import defaultdict
from typing import List, Dict, Tuple

# Configuration
LOGS_FILE = Path("/home/user/voicebm/meta/logs.jsonl")
EMB_DIR = Path("/home/user/voicebm/embeddings/living")
META_LAB = Path("/home/user/voicebm/meta/labeled")
PROCESSED_FILE = Path("/home/user/voicebm/meta/processed.txt")
CLUSTER_CACHE = Path("/home/user/voicebm/meta/clusters.json")

# Clustering parameters
SIMILARITY_THRESHOLD = 0.70  # Voices above this similarity are clustered together
MIN_CLUSTER_SIZE = 3         # Minimum samples to form a cluster
MAX_CLUSTER_SIZE = 50        # Maximum samples in one cluster (prevents overwhelming UI)


def get_processed_ids():
    """Get set of already processed event IDs"""
    processed = set()
    
    # Check labeled folder
    if META_LAB.exists():
        for f in META_LAB.glob("*.json"):
            processed.add(f.stem)
    
    # Check processed tracking file
    if PROCESSED_FILE.exists():
        with open(PROCESSED_FILE, 'r') as f:
            processed.update(line.strip() for line in f if line.strip())
    
    return processed


def load_embedding(emb_path: Path) -> np.ndarray:
    """Load embedding vector from file"""
    try:
        return np.loadtxt(emb_path)
    except Exception as e:
        print(f"Error loading {emb_path}: {e}")
        return None


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors"""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def get_enrolled_persons() -> Dict[str, Dict]:
    """
    Load enrolled persons and their embeddings.
    Returns dict of person_id -> {display_name, embeddings}
    """
    enroll_dir = Path("/home/user/voicebm/enroll")
    persons = {}
    
    if not enroll_dir.exists():
        return persons
    
    for person_dir in enroll_dir.iterdir():
        if not person_dir.is_dir():
            continue
        
        person_id = person_dir.name
        
        # Load metadata for display name
        metadata_file = person_dir / 'metadata.json'
        display_name = person_id
        if metadata_file.exists():
            try:
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
                    display_name = metadata.get('display_name', person_id)
            except:
                pass
        
        # Load embeddings (Sherpa format: .txt files in embeddings/ subdirectory)
        embeddings_dir = person_dir / 'embeddings'
        if not embeddings_dir.exists():
            continue
        
        embeddings = []
        for emb_file in embeddings_dir.glob('*.txt'):
            emb = load_embedding(emb_file)
            if emb is not None:
                embeddings.append(emb)
        
        if embeddings:
            persons[person_id] = {
                'display_name': display_name,
                'embeddings': embeddings
            }
    
    return persons


def find_likely_person_match(cluster_centroid: np.ndarray, enrolled_persons: Dict) -> Tuple[str, str, float]:
    """
    Compare cluster centroid against enrolled persons.
    
    Returns:
        (person_id, display_name, confidence) or (None, None, 0.0) if no good match
    """
    if not enrolled_persons:
        return None, None, 0.0
    
    best_match = None
    best_confidence = 0.0
    best_name = None
    
    for person_id, person_data in enrolled_persons.items():
        # Compute centroid of person's embeddings
        person_centroid = np.mean(person_data['embeddings'], axis=0)
        
        # Compare with cluster centroid
        similarity = cosine_similarity(cluster_centroid, person_centroid)
        
        if similarity > best_confidence:
            best_confidence = similarity
            best_match = person_id
            best_name = person_data['display_name']
    
    # Only return match if confidence is reasonable (>0.50)
    if best_confidence > 0.50:
        return best_match, best_name, best_confidence
    
    return None, None, 0.0


def get_unprocessed_samples() -> List[Dict]:
    """Get all unprocessed audio samples with their embeddings"""
    if not LOGS_FILE.exists():
        return []
    
    processed = get_processed_ids()
    samples = []
    
    with open(LOGS_FILE, 'r') as f:
        for line in f:
            if not line.strip():
                continue
            
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            
            wav_path = event.get('wav', '')
            emb_path = event.get('emb', '')
            
            if not wav_path or not emb_path:
                continue
            
            eid = Path(wav_path).stem
            
            # Skip if already processed
            if eid in processed:
                continue
            
            # Skip if files don't exist
            if not Path(wav_path).exists() or not Path(emb_path).exists():
                continue
            
            # Load embedding
            emb = load_embedding(Path(emb_path))
            if emb is None:
                continue
            
            samples.append({
                'id': eid,
                'wav': wav_path,
                'emb_path': emb_path,
                'embedding': emb,
                'timestamp': event.get('ts_iso', '')
            })
    
    return samples


def cluster_voices(samples: List[Dict]) -> List[List[Dict]]:
    """
    Cluster voice samples by similarity using simple threshold-based clustering.
    Similar to how Frigate groups similar faces.
    """
    if not samples:
        return []
    
    clusters = []
    remaining = samples.copy()
    
    while remaining:
        # Start new cluster with first remaining sample
        seed = remaining.pop(0)
        cluster = [seed]
        
        # Find all samples similar to this cluster
        to_remove = []
        for i, sample in enumerate(remaining):
            # Compare against cluster centroid
            cluster_embeddings = [s['embedding'] for s in cluster]
            centroid = np.mean(cluster_embeddings, axis=0)
            
            similarity = cosine_similarity(sample['embedding'], centroid)
            
            if similarity >= SIMILARITY_THRESHOLD:
                cluster.append(sample)
                to_remove.append(i)
                
                # Stop if cluster is getting too large
                if len(cluster) >= MAX_CLUSTER_SIZE:
                    break
        
        # Remove clustered samples from remaining
        for i in reversed(to_remove):
            remaining.pop(i)
        
        # Only keep clusters that meet minimum size
        if len(cluster) >= MIN_CLUSTER_SIZE:
            clusters.append(cluster)
    
    return clusters


def compute_cluster_stats(cluster: List[Dict]) -> Dict:
    """Compute statistics for a cluster"""
    embeddings = [s['embedding'] for s in cluster]
    centroid = np.mean(embeddings, axis=0)
    
    # Compute average similarity within cluster
    similarities = []
    for i, emb1 in enumerate(embeddings):
        for emb2 in embeddings[i+1:]:
            similarities.append(cosine_similarity(emb1, emb2))
    
    avg_similarity = np.mean(similarities) if similarities else 0.0
    
    # Get time range
    timestamps = [s['timestamp'] for s in cluster if s['timestamp']]
    time_range = {
        'start': min(timestamps) if timestamps else None,
        'end': max(timestamps) if timestamps else None
    }
    
    return {
        'count': len(cluster),
        'avg_similarity': float(avg_similarity),
        'time_range': time_range
    }


def generate_clusters(force_refresh: bool = False) -> List[Dict]:
    """
    Generate voice clusters for batch enrollment.
    Returns list of clusters with metadata.
    """
    # Check cache if not forcing refresh
    if not force_refresh and CLUSTER_CACHE.exists():
        try:
            cache_age = (Path.cwd().stat().st_mtime - CLUSTER_CACHE.stat().st_mtime)
            if cache_age < 300:  # Cache valid for 5 minutes
                with open(CLUSTER_CACHE, 'r') as f:
                    return json.load(f)
        except:
            pass
    
    print("Loading unprocessed samples...")
    samples = get_unprocessed_samples()
    print(f"Found {len(samples)} unprocessed samples")
    
    if not samples:
        return []
    
    print("Clustering voices by similarity...")
    clusters = cluster_voices(samples)
    print(f"Generated {len(clusters)} clusters")
    
    # Load enrolled persons for matching
    print("Loading enrolled persons for matching...")
    enrolled_persons = get_enrolled_persons()
    print(f"Found {len(enrolled_persons)} enrolled persons")
    
    # Convert clusters to serializable format
    cluster_data = []
    for i, cluster in enumerate(clusters):
        # Compute cluster centroid for person matching
        cluster_embeddings = [s['embedding'] for s in cluster]
        centroid = np.mean(cluster_embeddings, axis=0)
        
        # Find likely person match
        person_id, display_name, confidence = find_likely_person_match(centroid, enrolled_persons)
        
        # Remove embeddings from sample data (too large for JSON)
        # BUT keep emb_path for enrollment
        samples_data = [
            {
                'id': s['id'],
                'wav': s['wav'],
                'emb_path': s['emb_path'],  # CRITICAL: Needed for enrollment
                'timestamp': s['timestamp']
            }
            for s in cluster
        ]
        
        stats = compute_cluster_stats(cluster)
        
        cluster_data.append({
            'cluster_id': i,
            'samples': samples_data,
            'stats': stats,
            'likely_match': {
                'person_id': person_id,
                'display_name': display_name,
                'confidence': float(confidence) if confidence else 0.0
            } if person_id else None
        })
    
    # Cache results
    CLUSTER_CACHE.parent.mkdir(exist_ok=True)
    with open(CLUSTER_CACHE, 'w') as f:
        json.dump(cluster_data, f, indent=2)
    
    return cluster_data


def get_cluster_by_id(cluster_id: int) -> Dict:
    """Get specific cluster by ID"""
    clusters = generate_clusters()
    for cluster in clusters:
        if cluster['cluster_id'] == cluster_id:
            return cluster
    return None


if __name__ == "__main__":
    # Test clustering
    print("Generating voice clusters...")
    clusters = generate_clusters(force_refresh=True)
    
    print(f"\nFound {len(clusters)} clusters:")
    for c in clusters:
        print(f"  Cluster {c['cluster_id']}: "
              f"{c['stats']['count']} samples, "
              f"avg similarity: {c['stats']['avg_similarity']:.3f}")
