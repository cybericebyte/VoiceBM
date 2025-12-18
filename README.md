# VoiceBM

VoiceBM is a voice biometrics engine for Home Assistant. It identifies who is speaking, publishes identity signals via MQTT, and supports enrollment + blocklisting workflows.

> Scope note: VoiceBM is an engine. It exposes identity and controls; your UI/LLM/frontend decides how to use them.

## What it does
- Creates speaker embeddings and matches against an enrolled gallery
- Falls back to a virtual **user** identity for unknown speakers
- Publishes identity + status topics over MQTT (Home Assistant discovery-friendly)
- Per-identity blocklist switches (including **user**) to fail STT silently when blocked
- Room-aware collection, roomless identity (identity is global)

## What it does NOT do
- It’s not a full conversational UX
- It does not decide “what to say” or how to build assistants
- It doesn’t assume a specific frontend (Home Assistant, OpenWebUI, local LLM, etc.)

## Quick start (high level)
1. Install dependencies (see docs)
2. Configure MQTT + paths
3. Start services
4. Enroll voices
5. Verify identities in Home Assistant

## Configuration
This repo ships with example configs/templates. You must provide your own:
- MQTT broker host/user/password
- Local IPs / URLs
- Any secrets

**Never commit secrets** to GitHub.

## Docs
- See `/docs` for setup and Home Assistant entity details (if present)
- See `/systemd` for service examples (if present)

## GPT link
There will be a companion GPT for explanation/troubleshooting:
- Add link here once published:
```text
[<<img width="1920" height="1080" alt="image" src="https://github.com/user-attachments/assets/ed02e3a2-229b-4c16-92d4-cad6100e9be4" />
>
](https://chatgpt.com/g/g-68e55ecea6888191bb871536408fa73b-home-assistant-voicebm-voice-biometrics)
