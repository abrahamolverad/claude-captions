#!/usr/bin/env python3
"""Person masks for every frame (lets text and maps pass BEHIND the speaker).

usage: mask.py TALK.mp4 OUT.raw [--engine auto|apple|mediapipe]
-> one 540x960 8-bit mask per frame (person = 255), concatenated.
auto: Apple Vision on macOS when the `swift` command exists (best edges), otherwise MediaPipe Selfie Segmenter.
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

from common import ASSETS, IS_MAC, ROOT, need, video_size

MW, MH = 540, 960


def apple(video, out):
    r = subprocess.run(["swift", str(ROOT / "scripts" / "mask_macos.swift"), str(video), str(out), str(MW), str(MH)],
                       capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr[-800:])
    print(r.stdout.strip())


def mediapipe(video, out):
    import mediapipe as mp
    from mediapipe.tasks import python as mpt
    from mediapipe.tasks.python import vision
    opts = vision.ImageSegmenterOptions(base_options=mpt.BaseOptions(model_asset_path=str(ASSETS / "models" / "selfie_segmenter.tflite")),
                                        running_mode=vision.RunningMode.VIDEO, output_confidence_masks=True, output_category_mask=False)
    seg = vision.ImageSegmenter.create_from_options(opts)
    w, h = MW, MH
    dec = subprocess.Popen([need("ffmpeg"), "-loglevel", "error", "-i", str(video), "-vf", f"scale={w}:{h}", "-f", "rawvideo",
                            "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    n = 0
    with open(out, "wb") as fh:
        while True:
            buf = dec.stdout.read(w * h * 3)
            if len(buf) < w * h * 3:
                break
            frame = np.frombuffer(buf, np.uint8).reshape(h, w, 3)
            res = seg.segment_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(frame)), int(n * 1000 / 30))
            conf = np.squeeze(res.confidence_masks[0].numpy_view())
            m = np.clip(conf * 255, 0, 255).astype(np.uint8)
            if m.shape != (h, w):
                from PIL import Image
                m = np.asarray(Image.fromarray(m).resize((w, h)))
            fh.write(m.tobytes()); n += 1
    print(f"frames {n} mask {w}x{h} (mediapipe)")


def head_top(out, seconds=4.0):
    """y of the top of the head (1080x1920 frame) over the first seconds: put the hook's big line's baseline ~60-90 px below it"""
    m = np.memmap(out, dtype=np.uint8, mode="r").reshape(-1, MH, MW)
    tops = []
    for i in range(0, min(len(m), int(seconds * 30)), 5):
        rows = np.where(m[i].max(axis=1) > 128)[0]
        if len(rows):
            tops.append(int(rows.min() * 1920 / MH))
    if tops:
        print(f"head top over the first {seconds:.0f}s: min {min(tops)}, median {int(np.median(tops))}, max {max(tops)} (frame px)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("video"); ap.add_argument("out"); ap.add_argument("--engine", default="auto", choices=["auto", "apple", "mediapipe"])
    a = ap.parse_args()
    engine = a.engine
    if engine == "auto":
        engine = "apple" if IS_MAC and shutil.which("swift") else "mediapipe"
    if engine == "apple":
        try:
            apple(a.video, a.out)
            head_top(a.out)
            sys.exit(0)
        except Exception as e:                       # e.g. no Xcode command line tools
            print("Apple Vision failed, using MediaPipe:", str(e)[:200])
    mediapipe(a.video, a.out)
    head_top(a.out)
