#!/usr/bin/env python3
"""Word-level transcript with faster-whisper (runs on CPU on macOS, Windows and Linux).

usage: transcribe.py VIDEO OUT.json [--lang es] [--model small]
  -> {"text", "words": [{"w", "t0", "t1"}], "segments": [[t0, t1, text]]}
Use it on the RAW video to pick the good takes (cut.py --keep), and cut.py calls it again on the cut.
The first run downloads the Whisper model (small ≈ 0.5 GB, medium ≈ 1.5 GB).
"""
import argparse
import subprocess

from common import need, save_json


def transcribe(video, out, lang="es", model="small", device="cpu"):
    import numpy as np
    from faster_whisper import WhisperModel
    # decode with ffmpeg ourselves (16 kHz mono float32): avoids PyAV version problems on every OS
    raw = subprocess.run([need("ffmpeg"), "-loglevel", "error", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    audio = np.frombuffer(raw, np.float32).copy()
    m = WhisperModel(model, device=device, compute_type="int8")
    segs, _ = m.transcribe(audio, language=lang, word_timestamps=True, vad_filter=False, condition_on_previous_text=False)
    segs = list(segs)
    words = [{"w": w.word.strip(), "t0": round(w.start, 3), "t1": round(w.end, 3)} for s in segs for w in (s.words or []) if w.word.strip()]
    data = {"text": " ".join(s.text.strip() for s in segs), "words": words,
            "segments": [[round(s.start, 2), round(s.end, 2), s.text.strip()] for s in segs]}
    save_json(out, data)
    return data


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("video"); ap.add_argument("out")
    ap.add_argument("--lang", default="es"); ap.add_argument("--model", default="small"); ap.add_argument("--device", default="cpu")
    a = ap.parse_args()
    d = transcribe(a.video, a.out, a.lang, a.model, a.device)
    for t0, t1, txt in d["segments"]:
        print(f"{t0:7.2f}-{t1:7.2f}  {txt}")
