#!/usr/bin/python3
"""
VoiceBM Emote Edition — pre-alpha
SenseVoice emotion inference worker. Standalone, runs under vb Python.
Per-call: loads model, runs inference, writes JSON result to output file, exits.
Called by ser_infer.sh which is called by voicebm_emote.py thread.

Usage: ser_worker.py --wav <path> --out <json_path>

Output JSON: {"emotion": "neutral", "scores": {"neutral": 0.72, "sad": 0.24, ...}}

Scores are real normalized probabilities derived from CTC logits,
not one-hot. Dominant emotion is the highest-scoring class.

Real emotion classes (from model.emo_dict, unk excluded):
  happy, sad, angry, neutral
"""

import sys
import argparse
import json
import math

MODEL_ID = 'FunAudioLLM/SenseVoiceSmall'


def run_ser(wav_path, output_path):
    try:
        import torch
        import soundfile as sf
        from funasr import AutoModel
        from funasr.utils.load_utils import load_audio_text_image_video, extract_fbank

        # ── Load model ────────────────────────────────────────────────────
        auto = AutoModel(
            model=MODEL_ID,
            hub='hf',
            device='cpu',
            disable_update=True,
        )
        m         = auto.model
        tokenizer = auto.kwargs['tokenizer']
        frontend  = auto.kwargs['frontend']

        # ── Prepare audio input ───────────────────────────────────────────
        audio_sample_list = load_audio_text_image_video(
            wav_path,
            fs=frontend.fs,
            audio_fs=16000,
            data_type='sound',
            tokenizer=tokenizer,
        )
        speech, speech_lengths = extract_fbank(
            audio_sample_list,
            data_type='sound',
            frontend=frontend,
        )

        # ── Build input sequence (mirrors inference() internals) ──────────
        # Prepend language, textnorm, and event+emotion query embeddings
        # exactly as the model expects before the encoder sees the audio.
        language_query = m.embed(
            torch.LongTensor([[m.lid_dict['en']]]).to('cpu')
        ).repeat(speech.size(0), 1, 1)

        textnorm_query = m.embed(
            torch.LongTensor([[m.textnorm_dict['woitn']]]).to('cpu')
        ).repeat(speech.size(0), 1, 1)

        speech = torch.cat((textnorm_query, speech), dim=1)
        speech_lengths += 1

        event_emo_query = m.embed(
            torch.LongTensor([[1, 2]]).to('cpu')
        ).repeat(speech.size(0), 1, 1)

        input_query = torch.cat((language_query, event_emo_query), dim=1)
        speech = torch.cat((input_query, speech), dim=1)
        speech_lengths += 3

        # ── Encoder + CTC logits ──────────────────────────────────────────
        with torch.no_grad():
            encoder_out, encoder_out_lens = m.encoder(speech, speech_lengths)
            if isinstance(encoder_out, tuple):
                encoder_out = encoder_out[0]
            # Shape: [1, frames, vocab_size] — log probabilities
            ctc_logits = m.ctc.log_softmax(encoder_out)

        # ── Extract emotion scores ────────────────────────────────────────
        # emo_dict: {'unk': 25009, 'happy': 25001, 'sad': 25002,
        #            'angry': 25003, 'neutral': 25004}
        # Take max log-prob across all frames for each emotion token.
        # unk is excluded (mirrors ban_emo_unk=True in generate()).
        valid_frames = encoder_out_lens[0].item()
        log_scores = {}
        for label, tok_id in m.emo_dict.items():
            if label == 'unk':
                continue
            frame_log_probs = ctc_logits[0, :valid_frames, tok_id]
            log_scores[label] = frame_log_probs.max().item()

        # ── Normalize to probability distribution ─────────────────────────
        raw_probs = {k: math.exp(v) for k, v in log_scores.items()}
        total     = sum(raw_probs.values())
        scores    = {k: round(v / total, 4) for k, v in raw_probs.items()}

        # ── Dominant emotion = highest normalized score ───────────────────
        emotion = max(scores, key=scores.get)

        print(f"[ser_worker] emotion={emotion} scores={scores}", file=sys.stderr)

        result = {'emotion': emotion, 'scores': scores}
        with open(output_path, 'w') as f:
            json.dump(result, f)

        return True

    except ImportError as e:
        print(f"ERROR: import failed: {e}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"ERROR: SER inference failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SenseVoice emotion inference worker")
    parser.add_argument("--wav", required=True, help="Input WAV file")
    parser.add_argument("--out", required=True, help="Output JSON file")
    args = parser.parse_args()
    success = run_ser(args.wav, args.out)
    sys.exit(0 if success else 1)
