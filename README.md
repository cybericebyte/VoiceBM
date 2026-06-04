# VoiceBM

**Local, open-source voice biometrics for Home Assistant.**

VoiceBM resolves speaker identity from live audio — entirely on-premises, with
no cloud dependency — and publishes the result to Home Assistant via MQTT
discovery. It runs alongside the Wyoming ONNX ASR pipeline and uses
Sherpa-ONNX for speaker embedding.

---

## What it does

VoiceBM answers one question: **who is speaking?**

It operates as a set of independent primitives. Each primitive has one job and
exposes its output as an MQTT topic or Home Assistant entity. How those
primitives are consumed — in automations, LLM pipelines, or access control
logic — is entirely up to the integrator.

**Active pipeline** — request-driven, triggered per utterance:
- Resolves speaker identity against the enrollment gallery before STT runs
- Publishes identity, confidence, and decision to Home Assistant
- Gates transcript output: `voicebm/transcript/preferred` carries only
  allowed-speaker transcripts; `voicebm/transcript/debug` carries everything
- Maintains a pending buffer of recent utterances for enrollment review

**Passive pipeline** — continuous, per room:
- Records ambient audio via RTSP
- Filters non-speech with VAD
- Embeds and scores against the enrolled gallery in the background
- Publishes passive identity scoring and clustering data for gallery building

---

## Requirements

- Linux host with systemd (tested on NVIDIA Jetson, x86)
- [Miniforge](https://github.com/conda-forge/miniforge) or compatible conda distribution
- `vb` conda environment with `paho-mqtt` and `sherpa-onnx`
- [Sherpa-ONNX](https://github.com/k2-fsa/sherpa-onnx) `nemo_en_titanet_small.onnx` speaker model
- [Wyoming ONNX ASR](https://github.com/rhasspy/wyoming-onnx-asr) running in Docker
- MQTT broker (Mosquitto or compatible)
- Home Assistant with MQTT integration enabled
- FFmpeg (passive pipeline recorder)

---

## Installation

### 1. Prepare prerequisites

Install Miniforge, create the `vb` conda environment, install dependencies, and
download the Sherpa-ONNX speaker model. Refer to the Sherpa-ONNX documentation
for model setup.

### 2. Configure

```bash
tar -xzf VoiceBM_v2.0_Complete.tar.gz
cd VoiceBM_v2.0_Complete
cp config.json.sample config.json
```

Edit `config.json` with your values:

```json
{
  "mqtt": {
    "broker": "your-ha-host",
    "port": 1883,
    "user": "your-mqtt-user",
    "password": "your-mqtt-password"
  },
  "paths": {
    "voicebm_base": "/path/to/voicebm",
    "sherpa_bin": "/path/to/sherpa_embed.py",
    "sherpa_model": "/path/to/nemo_en_titanet_small.onnx",
    "conda_path": "/path/to/miniforge3",
    "onnx_asr_source": "/path/to/onnx-asr-addon/onnx-asr"
  },
  "audio_server": {
    "host": "your-voicebm-host",
    "port": 9090
  },
  "rooms": {
    "living": {
      "rtsp_url": "rtsp://user:pass@camera-ip/stream"
    }
  }
}
```

### 3. Create install directory and copy config

```bash
mkdir -p /path/to/voicebm
cp config.json /path/to/voicebm/
```

### 4. Deploy global services

```bash
cd scripts
sudo ./deploy_global_services.sh
```

This renders all templates against your config, installs systemd services,
deploys `handler.py` into the Wyoming ONNX ASR Docker container, and starts
everything.

### 5. Deploy passive nodes (optional)

```bash
# One command per room defined in config.json
sudo ./replicate_node.sh living
sudo ./replicate_node.sh bedroom
```

### 6. Verify

```bash
sudo systemctl status voicebm-stt.service
sudo journalctl -u voicebm-stt.service -n 50 --no-pager
```

Check Home Assistant for the **Voice Biometrics** device under Settings →
Devices & Services → MQTT.

---

## Upgrading from v1.0.x

```bash
sudo ./upgrade_v1_to_v2.sh
```

The upgrade script backs up all affected files before making any changes and
prints rollback instructions on completion. See `CHANGELOG_ACTIVE_2_0.md` for
the full list of breaking changes and migration steps.

---

## Architecture overview

```
Microphone / RTSP stream
        │
        ▼
Wyoming ONNX ASR (Docker)
  handler.py
        │ identity request (MQTT)
        ▼
voicebm_stt_service.py  ──── Sherpa-ONNX embedding
        │                           │
        │ identity response          ▼
        │                    gallery match
        ▼
  transcript streams
  voicebm/transcript/preferred   (gate-enforced)
  voicebm/transcript/debug       (raw)
        │
        ▼
  Home Assistant automations
```

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
`handler.py` is deployed via `docker cp` — the container (`nifty_grothendieck`)
is never rebuilt. If the deploy script completed without error, check the
container logs: `docker logs nifty_grothendieck`.

---

## License

MIT License — see `LICENSE` for details.

---

**Author:** David M. Dryver Sr.  
**Repository:** https://github.com/cybericebyte/VoiceBM  
**Version:** 2.0
