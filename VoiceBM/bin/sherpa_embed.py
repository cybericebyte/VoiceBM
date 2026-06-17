#!/usr/bin/env python3
import sys, wave, numpy as np
import sherpa_onnx

def load_wav_f32(path):
    with wave.open(path, "rb") as w:
        ch = w.getnchannels()
        sr = w.getframerate()
        sw = w.getsampwidth()
        n = w.getnframes()
        raw = w.readframes(n)

    # Supported widths: 16-bit or 32-bit PCM
    if sw == 2:
        pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif sw == 4:
        pcm = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        raise RuntimeError(f"Unsupported sample width: {sw} bytes")

    # Convert stereo → mono
    if ch > 1:
        pcm = pcm.reshape(-1, ch).mean(axis=1)

    return sr, pcm

def main():
    args = sys.argv
    model = args[args.index("--model")+1]
    wav   = args[args.index("--wav")+1]
    out   = args[args.index("--out")+1]

    sr, pcm = load_wav_f32(wav)

    cfg = sherpa_onnx.SpeakerEmbeddingExtractorConfig(
        model=model,
        num_threads=1,
        debug=False
    )
    extractor = sherpa_onnx.SpeakerEmbeddingExtractor(cfg)

    stream = extractor.create_stream()
    stream.accept_waveform(sr, pcm)
    stream.input_finished()

    emb = extractor.compute(stream)

    with open(out, "w") as f:
        f.write(" ".join(str(x) for x in emb))

if __name__ == "__main__":
    main()
