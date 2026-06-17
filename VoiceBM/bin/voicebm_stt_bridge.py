#!/usr/bin/env python3
"""
voicebm_stt_bridge.py — VoiceBM STT Bridge
OpenAI-compatible /v1/audio/transcriptions endpoint (part of VoiceBM)
Bridges OpenWebUI → Wyoming protocol → wyoming-onnx-asr (asr_container:10300)

Wyoming wire protocol:
  SEND:    header_json\n + data_bytes + payload_bytes
  RECEIVE: header_json\n + data_bytes + payload_bytes
  header has data_length and payload_length — data is NOT inline in header.
"""
import io
import json
import os
import sys
import socket
import wave
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
import uvicorn
import soundfile as sf
import numpy as np
import requests

# --- settings ---
WYOMING_HOST   = os.environ.get("WYOMING_HOST", "127.0.0.1")
WYOMING_PORT   = int(os.environ.get("WYOMING_PORT", "10300"))
SAMPLE_RATE    = 16000
BIOMETRICS_URL  = os.environ.get("BIOMETRICS_URL", "")
BIOMETRICS_AUTH = os.environ.get("BIOMETRICS_AUTH", "")


app = FastAPI()


def _to_16k_mono_pcm(file: UploadFile) -> tuple:
    """
    Read any audio OpenWebUI sends, convert to 16k mono PCM.
    Returns (pcm_bytes, rate, width, channels)
    """
    raw = file.file.read()
    data, sr = sf.read(io.BytesIO(raw), always_2d=True)
    if data.shape[1] > 1:
        data = data.mean(axis=1, keepdims=True)
    if sr != SAMPLE_RATE:
        import math
        n_src = data.shape[0]
        n_dst = int(math.ceil(n_src * SAMPLE_RATE / sr))
        t_src = np.linspace(0, 1, n_src, endpoint=False)
        t_dst = np.linspace(0, 1, n_dst, endpoint=False)
        data = np.interp(t_dst, t_src, data[:, 0]).astype(np.float32).reshape(-1, 1)
    buf = io.BytesIO()
    sf.write(buf, data, SAMPLE_RATE, subtype="PCM_16", format="WAV")
    wav_bytes = buf.getvalue()
    with wave.open(io.BytesIO(wav_bytes)) as wf:
        rate     = wf.getframerate()
        width    = wf.getsampwidth()
        channels = wf.getnchannels()
        pcm      = wf.readframes(wf.getnframes())
    return pcm, rate, width, channels


def _wyoming_transcribe(pcm: bytes, rate: int, width: int, channels: int) -> str:
    """
    Send PCM audio over Wyoming wire protocol to wyoming-onnx-asr.
    Returns transcript text.

    Wyoming wire format per event:
      header_json_line\n
      [data_length bytes of JSON data]
      [payload_length bytes of binary]
    Data is a SEPARATE block — never inline in the header JSON.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.connect((WYOMING_HOST, WYOMING_PORT))
        sock.settimeout(60)

        def send_event(event_type: str, data: dict = None, payload: bytes = b""):
            data_bytes = json.dumps(data).encode() if data else b""
            header = json.dumps({
                "type": event_type,
                "data_length": len(data_bytes),
                "payload_length": len(payload)
            }) + "\n"
            sock.sendall(header.encode())
            if data_bytes:
                sock.sendall(data_bytes)
            if payload:
                sock.sendall(payload)

        def recv_exact(n: int) -> bytes:
            """Read exactly n bytes from socket into buf accumulator."""
            out = b""
            while len(out) < n:
                try:
                    chunk = sock.recv(n - len(out))
                except socket.timeout:
                    break
                if not chunk:
                    break
                out += chunk
            return out

        # Mark this connection as bridge-origin IN-BAND, before any audio. The
        # handler reads this off the Transcribe event onto a per-utterance flag, so
        # it is known before the preferred gate runs — no MQTT, no race, every run.
        send_event("transcribe", {"name": "bridge"})

        # Send audio events
        send_event("audio-start", {"rate": rate, "width": width, "channels": channels})

        chunk_size = 4096
        for i in range(0, len(pcm), chunk_size):
            chunk = pcm[i:i + chunk_size]
            send_event("audio-chunk", {"rate": rate, "width": width, "channels": channels}, chunk)

        send_event("audio-stop", {})

        # Read Wyoming responses — data is in separate block after header newline
        buf = b""
        while True:
            try:
                incoming = sock.recv(4096)
            except socket.timeout:
                break
            if not incoming:
                break
            buf += incoming

            while b"\n" in buf:
                header_line, buf = buf.split(b"\n", 1)
                header_line = header_line.strip()
                if not header_line:
                    continue
                try:
                    header = json.loads(header_line.decode())
                except json.JSONDecodeError:
                    continue

                # Read separate JSON data block
                data_len = header.get("data_length", 0)
                event_data = {}
                if data_len > 0:
                    # Pull from buf first, then socket
                    while len(buf) < data_len:
                        try:
                            more = sock.recv(4096)
                        except socket.timeout:
                            more = b""
                        if not more:
                            break
                        buf += more
                    if len(buf) >= data_len:
                        try:
                            event_data = json.loads(buf[:data_len].decode())
                        except json.JSONDecodeError:
                            pass
                        buf = buf[data_len:]

                # Consume binary payload
                payload_len = header.get("payload_length", 0)
                if payload_len > 0:
                    while len(buf) < payload_len:
                        try:
                            more = sock.recv(4096)
                        except socket.timeout:
                            more = b""
                        if not more:
                            break
                        buf += more
                    buf = buf[payload_len:]

                if header.get("type") == "transcript":
                    return event_data.get("text", "")

    return ""


def _maybe_forward_biometrics(wav_bytes: bytes):
    if not BIOMETRICS_URL:
        return
    headers = {}
    if BIOMETRICS_AUTH:
        headers["Authorization"] = BIOMETRICS_AUTH
    files = {"file": ("utterance.wav", wav_bytes, "audio/wav")}
    try:
        requests.post(BIOMETRICS_URL, files=files, headers=headers, timeout=5)
    except Exception:
        pass


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/v1/audio/transcriptions")
async def transcribe(
    file: UploadFile = File(...),
    model: str = Form(...),
    prompt: Optional[str] = Form(None),
    language: Optional[str] = Form(None)
):
    try:
        pcm, rate, width, channels = _to_16k_mono_pcm(file)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read/convert audio: {e}")

    if BIOMETRICS_URL:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(width)
            wf.setframerate(rate)
            wf.writeframes(pcm)
        _maybe_forward_biometrics(buf.getvalue())

    try:
        text = _wyoming_transcribe(pcm, rate, width, channels)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Wyoming ASR error: {e}")

    return JSONResponse({"text": text})


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8005")))
