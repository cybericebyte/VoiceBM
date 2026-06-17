#!/usr/bin/env python3
"""
VoiceBM Ambient Edition — Passive Context Soft Hooks (pre-alpha)

Joins ambient speech detection with identity resolution and emotion in a
single per-room topic. Real-time: a fresh embedding is created from the
exact WAV slice that triggered the ambient speech event — never relies on
the passive pipeline's embedder cycle.

Plug-in contract:
  Install:  drop this file in /home/user/voicebm/bin/, restart ambient
  Remove:   delete this file, restart — ambient unaffected
  Broken:   soft import in voicebm_ambient.py no-ops

Hook activation (checked at runtime, per capability):
  Identity: vb python + sherpa_embed.py + titanet model + enroll/ exist
  Emote:    ser_infer.sh exists (optional — omitted from payload if absent)
  No identity capability -> nothing publishes; ambient runs as before.

Publishes (per room, retained):
  voicebm/{room}/passive_context
    {
      "ts":       ISO timestamp (first — David's spec: ts, speech, identity, emote),
      "room":     room,
      "source":   stream name,
      "speech":   {"state": ..., "prob": ...},
      "identity": {"speaker_id", "display_name", "confidence", "decision"},
      "emote":    {"state": ..., "scores": {...}}        # only if Emote installed
    }

HA discovery: one sensor per room, attached to the room's existing
Voice Biometrics device (identifiers ["voicebm_{room}"]). MQTT discovery
merges onto the device if the passive side already created it, or creates
it if not. Never duplicates.

Identity follows the VoiceBM identity state model: speech occurred and the
voice did not match the gallery -> identity is "user". Threshold is the
PASSIVE threshold (out/thresholds.json MATCH_T) — this is passive ambient
context, not live STT injection.

Threading: one daemon thread per speech event, guarded by a non-blocking
in-flight lock — if a context job is still running, the new event is
skipped and logged. Protects the host from stacked CPU inference.
"""

import os
import json
import time
import shutil
import tempfile
import threading
import subprocess

import numpy as np
from pathlib import Path

# ── Fixed paths (canonical VoiceBM layout — overridable via config.json) ──────
SHERPA_PYTHON = '/home/user/miniforge3/envs/vb/bin/python3'
SHERPA_WORKER = '/home/user/.local/bin/sherpa_embed.py'
SHERPA_MODEL  = '/home/user/sherpa_models/nemo_en_titanet_small.onnx'
SER_SCRIPT    = '/home/user/voicebm/bin/ser_infer.sh'
ENROLL_DIR    = '/home/user/voicebm/enroll'
THR_FILE      = '/home/user/voicebm/out/thresholds.json'
CONFIG_FILE   = '/home/user/voicebm/config.json'

DISCOVERY_PREFIX = 'homeassistant'


def _hook_config():
    """Tunables from config.json with safe fallbacks:
    paths.sherpa_model, voicebm.embed_timeout_s, emote.ser_timeout_s,
    emote.ser_script."""
    model, embed_t, ser_script, ser_t = SHERPA_MODEL, 30, SER_SCRIPT, 60
    try:
        with open(CONFIG_FILE, 'r') as f:
            cfg = json.load(f)
        model      = cfg.get('paths', {}).get('sherpa_model', model)
        embed_t    = float(cfg.get('voicebm', {}).get('embed_timeout_s', embed_t))
        ser_script = cfg.get('emote', {}).get('ser_script', ser_script)
        ser_t      = float(cfg.get('emote', {}).get('ser_timeout_s', ser_t))
    except Exception:
        pass
    return model, embed_t, ser_script, ser_t

# In-flight guard — one context job at a time
_inflight = threading.Lock()


def _child_env():
    """
    Subprocess env mirroring the active pipeline's invocation conditions.
    The ambient service runs with PYTHONNOUSERSITE=1 (required for AST),
    but sherpa_onnx lives in user site-packages — the workers must see it,
    exactly as they do when called from voicebm-stt.service.
    """
    env = os.environ.copy()
    env.pop('PYTHONNOUSERSITE', None)
    return env


# ─────────────────────────────────────────────────────────────────────────────
# Capability checks
# ─────────────────────────────────────────────────────────────────────────────
def identity_available():
    model, _, _, _ = _hook_config()
    return (os.path.exists(SHERPA_PYTHON)
            and os.path.exists(SHERPA_WORKER)
            and os.path.exists(model)
            and os.path.isdir(ENROLL_DIR))


def emote_available():
    _, _, ser_script, _ = _hook_config()
    return os.path.exists(ser_script)


# ─────────────────────────────────────────────────────────────────────────────
# Gallery (mirrors publish_identity_living.py exactly)
# ─────────────────────────────────────────────────────────────────────────────
def load_gallery():
    """Load enrolled speakers from /enroll/. Returns {(person_id, display_name): centroid}."""
    people = {}
    enroll_path = Path(ENROLL_DIR)

    if not enroll_path.exists():
        return {}

    try:
        for person_dir in enroll_path.iterdir():
            if not person_dir.is_dir():
                continue

            person_id      = person_dir.name
            embeddings_dir = person_dir / 'embeddings'
            metadata_file  = person_dir / 'metadata.json'

            if metadata_file.exists():
                try:
                    with open(metadata_file, 'r') as f:
                        metadata = json.load(f)
                        display_name = metadata.get('display_name', person_id.replace('_', ' ').title())
                except Exception:
                    display_name = person_id.replace('_', ' ').title()
            else:
                display_name = person_id.replace('_', ' ').title()

            if not embeddings_dir.exists():
                continue

            vectors = []
            for emb_file in embeddings_dir.glob('*.txt'):
                try:
                    v = np.loadtxt(emb_file)
                    if v is not None and len(v) > 0:
                        vectors.append(v)
                except Exception:
                    pass

            if vectors:
                people[(person_id, display_name)] = vectors

    except Exception as e:
        print(f'[ambient-hooks] gallery load error: {e}')
        return {}

    cents = {}
    for (sid, name), vecs in people.items():
        cents[(sid, name)] = np.mean(vecs, axis=0)
    return cents


def cos(a, b):
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def passive_threshold():
    try:
        with open(THR_FILE, 'r') as f:
            thr = json.load(f)
            return float(thr.get('MATCH_T', 0.22))
    except Exception:
        return 0.22


def ambient_thresholds():
    """
    Dedicated decision knobs for ambient-probe identity.
    Far-field camera audio is its own domain — neither the passive nor the
    active pipeline threshold fits it. config.json -> thresholds:
      ambient_context — absolute floor for acceptance (default 0.18)
      ambient_margin  — best must beat runner-up by this gap (default 0.05)
    Falls back to the passive MATCH_T if ambient_context is not configured.
    """
    try:
        with open('/home/user/voicebm/config.json', 'r') as f:
            thr = json.load(f).get('thresholds', {})
        match_t = float(thr.get('ambient_context', passive_threshold()))
        margin  = float(thr.get('ambient_margin', 0.05))
        return match_t, margin
    except Exception:
        return passive_threshold(), 0.05


# ─────────────────────────────────────────────────────────────────────────────
# Workers
# ─────────────────────────────────────────────────────────────────────────────
def _embed(wav_path):
    """Run sherpa embedding on wav_path. Returns vector or None."""
    emb_path = None
    try:
        model, embed_t, _, _ = _hook_config()

        with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as tmp:
            emb_path = tmp.name

        result = subprocess.run(
            [SHERPA_PYTHON, SHERPA_WORKER,
             '--model', model,
             '--wav', wav_path,
             '--out', emb_path],
            capture_output=True,
            text=True,
            timeout=embed_t,
            env=_child_env(),
        )
        if result.returncode != 0:
            print(f'[ambient-hooks] embed failed (rc={result.returncode}): {result.stderr.strip()}')
            return None

        v = np.loadtxt(emb_path)
        if v is None or len(v) == 0:
            return None
        return v

    except subprocess.TimeoutExpired:
        print('[ambient-hooks] embed timed out — skipping')
        return None
    except Exception as e:
        print(f'[ambient-hooks] embed error: {e}')
        return None
    finally:
        if emb_path:
            try:
                os.unlink(emb_path)
            except OSError:
                pass


def _resolve_identity(wav_path):
    """
    Fresh embedding -> gallery match -> identity.

    Decision rule (ambient-probe domain):
      accept iff best >= ambient_context threshold
               AND best beats the runner-up by ambient_margin.
    A best-vs-runner-up gap inside the margin is a coin flip, not a match —
    coin flips resolve to 'user' (the error trap doing its job).
    Speech occurred: no acceptance means 'user' (VoiceBM identity state model).
    """
    v = _embed(wav_path)
    if v is None:
        return None

    cents           = load_gallery()
    match_t, margin = ambient_thresholds()

    best_sid, best_name, best_sim = None, None, -1.0
    second_sid, second_sim        = None, -1.0
    for (psid, pname), cent in cents.items():
        sim = cos(v, cent)
        if sim > best_sim:
            second_sid, second_sim = best_sid, best_sim
            best_sid, best_name, best_sim = psid, pname, sim
        elif sim > second_sim:
            second_sid, second_sim = psid, sim

    gap = best_sim - second_sim if second_sid is not None else None
    print(f'[ambient-hooks] resolve: best={best_sid}({best_sim:.4f}) '
          f'2nd={second_sid}({second_sim:.4f}) '
          f'thr={match_t} margin={margin}'
          if second_sid is not None else
          f'[ambient-hooks] resolve: best={best_sid}({best_sim:.4f}) thr={match_t}')

    accepted = bool(cents) and best_sim >= match_t and (gap is None or gap >= margin)

    if accepted:
        return {
            'speaker_id':   best_sid,
            'display_name': best_name,
            'confidence':   round(best_sim, 4),
            'decision':     'accepted',
        }

    return {
        'speaker_id':   'user',
        'display_name': 'user',
        'confidence':   round(max(best_sim, 0.0), 4),
        'decision':     'unknown',
    }


def _resolve_emote(wav_path):
    """Run SER on wav_path. Returns {'state', 'scores'} or None."""
    result_path = None
    try:
        _, _, ser_script, ser_t = _hook_config()

        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as tmp:
            result_path = tmp.name

        result = subprocess.run(
            [ser_script, wav_path, result_path],
            capture_output=True,
            text=True,
            timeout=ser_t,
            env=_child_env(),
        )
        if result.returncode != 0:
            print(f'[ambient-hooks] SER failed (rc={result.returncode}): {result.stderr.strip()}')
            return None

        with open(result_path, 'r') as f:
            data = json.load(f)

        return {
            'state':  data.get('emotion', 'unknown'),
            'scores': data.get('scores', {}),
        }

    except subprocess.TimeoutExpired:
        print('[ambient-hooks] SER timed out — skipping')
        return None
    except Exception as e:
        print(f'[ambient-hooks] SER error: {e}')
        return None
    finally:
        if result_path:
            try:
                os.unlink(result_path)
            except OSError:
                pass


# ─────────────────────────────────────────────────────────────────────────────
# Public API — called from voicebm_ambient.py
# ─────────────────────────────────────────────────────────────────────────────
def publish_context_discovery(client, sources):
    """
    One Passive Context sensor per room, attached to the room's
    Voice Biometrics device. Discovery merges onto the existing device
    (identifiers ["voicebm_{room}"]) or creates it — never duplicates.
    Called once on MQTT connect. Retained.
    """
    if not identity_available():
        print('[ambient-hooks] identity capability missing — passive context inactive')
        return

    for source in sources:
        room = source['room']
        uid  = room.replace(' ', '_').lower()
        nice = source.get('friendly_name', room.replace('_', ' ').title())

        device = {
            'identifiers': [f'voicebm_{uid}'],
            'name': f'Voice Biometrics {nice}',
            'manufacturer': 'David M. Dryver Sr.',
            'model': 'Home Assistant Voice Biometrics',
            'sw_version': '2.0',
        }

        config = {
            'name': 'Passive Context',
            'unique_id': f'voicebm_{uid}_passive_context',
            'state_topic': f'voicebm/{room}/passive_context',
            'value_template': "{{ value_json.identity.display_name if value_json.identity else 'none' }}",
            'json_attributes_topic': f'voicebm/{room}/passive_context',
            'icon': 'mdi:account-eye',
            'device': device,
        }
        client.publish(
            f'{DISCOVERY_PREFIX}/sensor/voicebm_{uid}_passive_context/config',
            json.dumps(config),
            qos=1,
            retain=True,
        )

    print(f'[ambient-hooks] passive context discovery published ({len(sources)} rooms)')


def run_passive_context(client, source, state, prob, wav_path):
    """
    Fire-and-forget passive context resolution for one ambient speech event.

    Copies the WAV synchronously (the ambient tmp WAV is overwritten next
    cycle), then resolves identity + emote in a daemon thread and publishes
    the combined payload. Non-blocking — ambient loop is never held up.

    One job at a time: if a previous context job is still running, this
    event is skipped.
    """
    if not identity_available():
        return

    if not _inflight.acquire(blocking=False):
        print('[ambient-hooks] context job in flight — skipping event')
        return

    # Snapshot the WAV before the ambient loop can overwrite it
    try:
        fd, wav_copy = tempfile.mkstemp(suffix='.wav')
        os.close(fd)
        shutil.copy2(wav_path, wav_copy)
    except Exception as e:
        print(f'[ambient-hooks] WAV snapshot failed: {e}')
        _inflight.release()
        return

    room        = source['room']
    source_name = source['name']
    ts          = time.strftime('%Y-%m-%dT%H:%M:%SZ')

    def _job():
        try:
            identity = _resolve_identity(wav_copy)
            if identity is None:
                print('[ambient-hooks] identity unresolved — no publish')
                return

            payload = {
                'ts':     ts,
                'room':   room,
                'source': source_name,
                'speech': {'state': state, 'prob': prob},
                'identity': identity,
            }

            if emote_available():
                emote = _resolve_emote(wav_copy)
                if emote is not None:
                    payload['emote'] = emote

            client.publish(
                f'voicebm/{room}/passive_context',
                json.dumps(payload),
                qos=1,
                retain=True,
            )
            print(f'[ambient-hooks] context: {room} -> '
                  f'{identity["display_name"]} ({identity["decision"]}, '
                  f'{identity["confidence"]:.4f})'
                  + (f' emote={payload["emote"]["state"]}' if 'emote' in payload else ''))

        except Exception as e:
            print(f'[ambient-hooks] context job failed: {e}')
        finally:
            try:
                os.unlink(wav_copy)
            except OSError:
                pass
            _inflight.release()

    threading.Thread(target=_job, daemon=True).start()
