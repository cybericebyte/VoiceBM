# VoiceBM

**Local, open-source voice biometrics.**

VoiceBM resolves speaker identity from live audio — entirely on-premises, with
no cloud dependency — and publishes the result over MQTT. Home Assistant is the
reference integration and MQTT discovery is built in, but the output is plain
MQTT: anything that can read a topic can consume it. It runs alongside the
Wyoming ONNX ASR pipeline and uses Sherpa-ONNX for speaker embedding.

---

## What it does

VoiceBM answers one question: **who is speaking?**

It's a set of independent primitives that publish over MQTT. Each has one job;
how its output is consumed — automations, an LLM pipeline, access-control logic —
is the integrator's decision. Home Assistant is the reference integration (MQTT
discovery is built in), but anything that reads MQTT can consume VoiceBM.

## Components

VoiceBM is modular — run only the parts you want. Each is independent, and the
two add-ons sit on the core side they extend.

**VoiceBM 2.0** — the engine: identity resolution, enrollment, and the MQTT contract.

- **Active 2.0** — request-driven, per utterance. Resolves speaker identity
  against the enrollment gallery before STT runs; publishes identity, confidence,
  and decision; gates transcript output (`voicebm/transcript/preferred` = allowed
  speakers only, `voicebm/transcript/debug` = everything); keeps a pending buffer
  of recent utterances for enrollment review.
- **Passive 2.0** — continuous, per node. Records audio from an RTSP audio source,
  filters non-speech with VAD, and embeds/scores against the gallery in the
  background to build and review your roster over time.
- **Global 2.0** — the system-wide control layer: the global "Voice Biometrics"
  device, identity injection control, blocklist, and settings that aren't tied to
  a single node or person.

**Optional add-ons** — each extends the side it rides on:

- **Emote 1.0 beta** — speech emotion recognition on the **active** side.
  Estimates emotional tone per utterance and publishes it alongside the identity.
  CPU-only.
- **Ambient 1.0 beta** — audio event detection on the **passive** side. Recognizes
  environmental sounds (glass, a dog, a vehicle, and so on) on a continuous
  background listener. CPU-only.

Everything is optional. The two editions track their own release path
(pre-alpha → beta → 1.0), separate from the 2.0 core.

---

## Requirements

**Compute baseline is CPU — no GPU or CUDA required.** VoiceBM is an orchestrator: it coordinates swappable components, none of which it depends on. Identity, passive, and ambient run on ONNX Runtime (sherpa-onnx) on CPU; the active path uses the ONNX ASR container; Emote (SER) pulls torch for FunASR/SenseVoice-Small but runs CPU-only (`device='cpu'`). No component touches CUDA or the GPU. GPU acceleration is an optional upgrade you wire into a component yourself — it is never assumed.

- Linux host with systemd (ARM64 or x86_64)
- A Python environment for the dependencies — conda, a venv, or an interpreter you already manage. Conda is optional: it's a way to keep these deps off your base system if you want that, not a requirement.
- `paho-mqtt` and `sherpa-onnx` available to that interpreter
- [Sherpa-ONNX](https://github.com/k2-fsa/sherpa-onnx) `nemo_en_titanet_small.onnx` speaker model
- [Wyoming ONNX ASR](https://github.com/rhasspy/wyoming-onnx-asr) running in Docker
- MQTT broker (Mosquitto or compatible)
- Home Assistant with MQTT integration enabled
- FFmpeg (passive pipeline recorder)

---

## Installation

```bash
tar -xzf VoiceBM_v2.0_Complete.tar.gz
cd VoiceBM_v2.0_Complete
./setup_voicebm.sh
```

`setup_voicebm.sh` is the install path. It walks you through component selection,
sets up the Python environment of your choice (conda, a venv, or an interpreter
you manage), installs the dependencies and the speaker model, takes your node
details, **writes `config.json` for you**, and then offers to run the deploy.
You never hand-write configuration — the wizard builds it from your answers.
It only uses `sudo` for the final systemd step.

### After the wizard

If you declined the deploy step at the end of the wizard, run it any time:

```bash
sudo ./scripts/deploy_global_services.sh
```

Add a passive node service for each node you defined (nodes are RTSP **audio**
sources — a Pi or anything serving an RTSP audio stream, not a camera):

```bash
sudo ./scripts/replicate_node.sh living
sudo ./scripts/replicate_node.sh bedroom
```

Verify:

```bash
sudo systemctl status voicebm-stt.service
sudo journalctl -u voicebm-stt.service -n 50 --no-pager
```

Check Home Assistant for the **Voice Biometrics** device under Settings →
Devices & Services → MQTT.

---

## Upgrading from v1.0.x

```bash
cd scripts
sudo ./upgrade_v1_to_v2.sh
```

The upgrade script backs up all affected files before making any changes and
prints rollback instructions on completion. See `CHANGELOG_ACTIVE_2_0.md` for
the full list of breaking changes and migration steps.

---

## Architecture overview

```
             ACTIVE                                          PASSIVE
    (request-driven, per utterance)                   (continuous, per node)

    Voice satellite / assist audio                    RTSP audio node
            │                                               │
            ▼                                               ▼
    Wyoming ONNX ASR (Docker)                         rec_node.sh      RTSP -> WAV
    handler.py                                              │
        │  ▲                                                ▼
        ▼  │                                          vad_filter.py    drop non-speech
    voicebm_stt_service.py                                  │
       Sherpa embed                                         ▼
            │                                         embed_node.sh    Sherpa embed
            │                                               │
            └──────────►  ┌───────────────┐  ◄─────────────┘
              match /     │    GALLERY     │    match /
              enroll      │   enrolled     │    enroll/cluster
                          │  voiceprints   │
                          │   (Sherpa)     │
                          └───────────────┘
              -- both sides contribute to it · both match off it --
            │                                                   │
            ▼                                                   ▼
    handler.py gates, publishes:                       publish_identity_node.py
      transcript/preferred (gate-enforced)             voicebm/{node}/identity ·
      transcript/debug     (raw)                         person_id · score · accepted
      current_speaker                                         │
            │                                                 ▼
            ▼                                          Home Assistant (roster review)
    Home Assistant / LLM
```

The two sides are independent but not isolated: both embed with Sherpa, both
write to the same gallery, and both match against it. That shared gallery is the
bridge — strip either side and the other still stands.

Identity primitives published per utterance:
- `voicebm/active/identity` — speaker ID, display name, confidence, decision
- `{person_id}/voice` — binary sensor (ON during utterance)
- `voicebm/current_speaker` — display name of current enrollment-grade sample
- `voicebm/pending_active` — buffer of recent unidentified utterances for review

---

## Enrollment

Speakers are enrolled through the pending active buffer. When an unknown speaker
is detected, the utterance is held in `voicebm/pending_active`. The Home
Assistant **Voice Biometrics** device exposes controls to listen to the sample,
assign a name, and enroll it into the gallery. Enrolled speakers are immediately
active — no restart required.

---

## Troubleshooting

**Services not starting:**
```bash
sudo journalctl -u voicebm-stt.service -n 50 --no-pager
sudo journalctl -u voicebm-enrollment-watcher.service -n 50 --no-pager
```

**Identity always resolving to `user`:**  
Check that the enrollment gallery exists and that the active threshold slider in
Home Assistant is set appropriately for your environment.

**Docker container not updating:**  
`handler.py` is deployed via `docker cp` — the container (`your-asr-container`)
is never rebuilt. If the deploy script completed without error, check the
container logs: `docker logs your-asr-container`.

---

## License

MIT License — see `LICENSE` for details.

---

**Author:** David M. Dryver Sr.  
**Repository:** https://github.com/cybericebyte/VoiceBM  
**Version:** 2.0
