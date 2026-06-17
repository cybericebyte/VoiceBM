# VoiceBM Active 2.0 — Changelog & Migration Guide

**Scope: the active / global side only.**

VoiceBM is split into two independently-deployable sides: the **active/global**
side (live STT, identity resolution, enrollment, MQTT discovery; deployed via
`deploy_global_services.sh`) and the **passive** side (per-node recorders,
embedders, scorers, clustering; deployed via `replicate_node.sh`). Either side
can be installed without the other.

Everything in this release is on the **active/global** side. The passive side is
unchanged and continues at its existing version; it will receive its own 2.0
revision when passive-side work is complete. This document versions the active
side as **Active 2.0**.

---

## 2.1 — STT Bridge & dashboard controls

Additive release on top of 2.0. No breaking changes; no migration required
beyond redeploying the updated files.

- **STT Bridge (new).** An OpenAI-compatible `/v1/audio/transcriptions` endpoint
  (`voicebm-stt-bridge.service`, port 8005) that runs client audio — e.g. from
  OpenWebUI — through the full active pipeline. Makes VoiceBM usable from
  platforms other than Home Assistant. Installed with the active side; its
  dependencies are wired by the setup wizard.
- **Transcript Preferred switch (new).** Per-utterance control over whether
  bridge-driven speech reaches `voicebm/transcript/preferred`. Bridge utterances
  are marked in-band (via the Wyoming `Transcribe` event), so suppression is
  decided before the publish and native satellite speech is never affected.
  State persists in `config.json` (`voicebm.transcript_preferred`).
- **ID Injection switch (restored).** Re-wired to `config.json` as the single
  source of truth, with HA discovery and dashboard control in sync.
- **Preferred-topic state model (fixed).** `state` now reflects reality —
  `user_transcript_ready` when a transcript is present, the ellipsis null when
  not — and the volatile timestamp was removed from the payload, so identical
  republishes are byte-identical no-ops and no longer trigger phantom automation
  runs.
- **Dashboard enrollment (fixed).** Pending-voice enroll and reject now publish
  to the existing `voicebm/pending_active/enroll` and `.../reject` topics
  instead of doing nothing, and the pending list renders correctly.

---

The remainder of this document covers **Active 2.0**, which contains three
breaking changes. Read the Breaking Changes section before upgrading a 1.0
install.

---

## Breaking Changes

### 1. Transcript topic renamed; gate-enforced topic added

1.0 published a single transcript topic. Every consuming automation was required
to perform its own identity tag-stripping and blocklist verification because the
topic made no delivery guarantees.

In 1.0, a blocked speaker caused an immediate return with an empty transcript
before STT ran — nothing was published. In 2.0, STT runs for all speakers
regardless of blocklist state. The gate operates on what gets published and what
gets forwarded to Wyoming, not on whether STT runs.

| Topic | Description | Use |
|-------|-------------|-----|
| `voicebm/transcript/debug` | Original raw broadcast, renamed. Published on every transcription, blocked or not. Carries the full identity-prepended JSON payload. No enforcement guarantees. | Diagnostics and legacy automation compatibility. |
| `voicebm/transcript/preferred` | **New in 2.0.** Gate-enforced output. Empty string payload when speaker is blocked; transcript text when speaker is allowed. No identity tag. | All new automations should consume this topic. |

**Required action on upgrade:** Any automation subscribed to the 1.0 transcript
topic must be repointed to `voicebm/transcript/debug` to retain identical
behavior, or to `voicebm/transcript/preferred` for gate-enforced output.

---

### 2. `current_speaker` topic corrected to global scope

In 1.0, `handler.py` published the current speaker to
`voicebm/living/current_speaker`. The active pipeline is satellite-agnostic;
that room-scoped topic was incorrect. In 2.0, `handler.py` publishes to
`voicebm/current_speaker`. The `voicebm_global_publisher.py` sensor has always
been registered to the global topic. The passive pipeline continues to publish
`voicebm/{room}/current_speaker` independently and is unaffected.

**Required action on upgrade:** Any consumer reading
`voicebm/living/current_speaker` as the active-pipeline current speaker must
repoint to `voicebm/current_speaker`.

---

### 3. `inject_identity` subscription corrected to global scope

In 1.0, `handler.py` subscribed to `voicebm/living/inject_identity`. That topic
was never published by any component — the global publisher and STT service both
used `voicebm/inject_identity` — so the injection toggle had no effect on
handler behavior in 1.0. In 2.0, `handler.py` subscribes to
`voicebm/inject_identity`, matching the published topic.

**Required action on upgrade:** None. This is a correction. The injection switch
in Home Assistant now controls handler behavior as intended.

---

## New Features

### Gallery rollover cap (per-person sample limit)

A configurable per-person ceiling on enrolled embeddings. When a new enrollment
would push a person over the cap, the oldest sample by `enrolled_at` is pruned —
its `.txt` embedding and `.wav` recording are deleted and the metadata is
updated.

- Exposed in Home Assistant as the **Gallery Max** number entity on the Voice
  Biometrics device.
- Command topic: `voicebm/gallery_max/set` — State topic: `voicebm/gallery_max` (retained).
- Default is **75** (the rolling FIFO cap); set to **0** to disable rollover
  entirely. The cap is read at enrollment time, so changes take effect
  immediately without a restart.
- Enforced on both enrollment paths: active pending-enroll in the STT service
  and the label/enroll path in the command listener. Each service maintains an
  independent implementation of the cap logic.

---

### Active-pipeline lead trim

The embedding step can strip a configurable number of milliseconds from the
front of the audio before embedding. This excludes a wake-word chime from the
sample presented to Sherpa for matching and enrollment.

- Applied at the embedding chokepoint in `create_embedding`: a trimmed temporary
  copy is embedded and discarded. **The stored WAV is never modified.** This
  single chokepoint covers both identity matching and pending enrollment.
- Configurable via `config.json` (`voicebm.active_lead_trim_ms`) and exposed in
  Home Assistant as the **Active Lead Trim** number entity.
  - Command topic: `voicebm/active/lead_trim/set` — State topic: `voicebm/active/lead_trim`.
  - A slider change persists immediately to `config.json` and takes effect on
    the next utterance without a restart.
- **Default is 0 (off).** Set to the approximate chime duration in milliseconds.

---

### Aggregate blocklist topic

1.0 published blocklist state only per identity under
`voicebm/blocklist/{person_id}`.

2.0 adds a single topic carrying the full blocklist state:

```
voicebm/blocklist_state
```

Published by `enrollment_watcher.py` as a `{person_id: blocked}` JSON object.
The Home Assistant sensor state shows the count of currently blocked identities;
the full map is available as sensor attributes. Per-person topics are unchanged.
The aggregate topic is outside the `voicebm/blocklist/+` wildcard to avoid
collision with per-person subscribers.

---

### Fallback identity display name standardized to `user`

The fallback display name for unmatched speakers is now **`user`** instead of
`Unknown`. `user` is the undefined identity by design — the error trap that
captures any voice not matched in the gallery. Standardizing on `user` removes
the special-casing `Unknown` required in automations and makes the fallback
behave identically to any enrolled identity from an automation perspective.

> The Detected / Unknown label on the voice-activity binary sensor describes
> whether speech was detected, not who spoke. It is unchanged.

---

## Summary table

| ID | Type | Item | Status |
|----|------|------|--------|
| B-01 | Breaking | Raw transcript renamed: `voicebm/transcript/debug` (was single unnamed topic); STT now runs for all speakers | Breaking — repoint consumers |
| B-02 | Breaking | `current_speaker` corrected to global: `voicebm/current_speaker` (was `voicebm/living/current_speaker`) | Breaking — repoint consumers |
| B-03 | Breaking | `inject_identity` subscription corrected: `voicebm/inject_identity` (was `voicebm/living/inject_identity`) | Breaking — no consumer action required |
| F-01 | Feature | `voicebm/transcript/preferred` — gate-enforced transcript feed | Added |
| F-02 | Feature | Gallery rollover cap (`voicebm/gallery_max`) | Added (default 75) |
| F-03 | Feature | Active-pipeline lead trim (`voicebm/active/lead_trim`) | Added (default off) |
| F-04 | Feature | Aggregate blocklist topic `voicebm/blocklist_state` | Added |
| F-05 | Feature | Fallback `display_name` standardized to `user` (was `Unknown`) | Added |

---

## Upgrade procedure (Active 1.0 → Active 2.0)

### Automated upgrade

Run the provided upgrade script from within the VoiceBM 2.0 package:

```bash
sudo ./scripts/upgrade_v1_to_v2.sh
```

The script backs up all affected files before making any changes, patches only
the components that changed, restarts affected services, and prints rollback
instructions. Your enrollment gallery, embeddings, recordings, and existing
configuration are not modified.

### Manual upgrade checklist

1. **Deploy updated service files.** Install the updated `handler.py` into the
   ONNX ASR Docker container via `docker cp` and restart the container. Deploy
   the updated host Python services (`voicebm_stt_service.py`,
   `voicebm_config.py`, `mqtt_commands.py`, `enrollment_watcher.py`) to your
   VoiceBM `bin/` directory and restart their systemd units.

2. **Repoint transcript consumers.** Automations on the 1.0 transcript topic:
   - To preserve existing behavior: repoint to `voicebm/transcript/debug`.
   - For gate-enforced output: repoint to `voicebm/transcript/preferred`.

3. **Repoint `current_speaker` consumers.** Any consumer reading
   `voicebm/living/current_speaker` as the active-pipeline current speaker must
   repoint to `voicebm/current_speaker`.

4. **Add voicebm tunables to config.json.** The upgrade script handles this
   automatically. To apply manually:
   ```json
   "voicebm": {
     "gallery_max": 75,
     "active_lead_trim_ms": 0
   }
   ```

5. **(Optional) Set Gallery Max** in Home Assistant. Default of 0 means no
   rollover; existing behavior is unchanged until a value is set.

6. **(Optional) Set Active Lead Trim** in Home Assistant. Default of 0 means no
   trimming. Set to the approximate chime duration in milliseconds.

7. **No action required** for the aggregate Blocklist State sensor, the corrected
   `inject_identity` behavior, or the `user` display-name change — these take
   effect automatically.

Fresh installs use `deploy_global_services.sh` and receive all of the above
without any migration steps.
