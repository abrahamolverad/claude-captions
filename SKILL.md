---
name: captions
description: |
  Edit a talking-head video into a finished vertical Reel/TikTok/Short with minimalist "Helvetica" captions: lowercase bold
  words that pop in one by one, one big key word per phrase, the hook's big word BEHIND the speaker's head, plus optional
  B-roll (news screenshots or footage with hand-drawn red circles and handwritten notes, full screen or split screen),
  floating country maps that pass behind/in front of the speaker, and an animated checklist.
  Use when the user drops a video and asks to "add captions", "edit this video", "subtítulos", "edita este video",
  "pon captions", "hazlo como Reel", "text behind my head", "split screen", "mapas de países", or similar.
---

# captions · Helvetica captions + B-roll for vertical videos

Everything is rendered locally with Python + ffmpeg. Scripts live in `scripts/`; run them with the skill's own Python:
- macOS/Linux: `<skill>/.venv/bin/python <skill>/scripts/<script>.py …`
- Windows: `<skill>\.venv\Scripts\python.exe <skill>\scripts\<script>.py …`
(`<skill>` is this folder, usually `~/.claude/skills/captions`.) Keep every working file in a `work/` folder next to the user's video.

## 0. First run (once)
If `<skill>/.venv` does not exist:
1. Check `ffmpeg -version`. Missing → macOS `brew install ffmpeg`, Windows `winget install Gyan.FFmpeg` (then a new terminal).
2. Run setup with Python 3.10–3.12: macOS `python3.12 <skill>/scripts/setup.py` (or 3.11/3.10), Windows `py -3.12 <skill>\scripts\setup.py`.
   If no such Python exists, ask the user to install Python 3.12 (python.org) and stop.
3. The first transcription downloads the Whisper model (~0.5 GB). Tell the user it is a one-time wait.

## 1. Pick the good takes
`transcribe.py RAW.mp4 work/raw_words.json --lang es` (use the video's language). Read the segments. Repeated lines, false starts
and mistakes are common: keep the LAST complete take of each line unless an earlier one is clearly better. Build the list of ranges.

## 2. Cut
`cut.py RAW.mp4 work --keep a-b --keep c-d …` (or `--drop` for single bad parts; `--protect` keeps a deliberate pause).
Output: `work/talk.mp4` (1080x1920, 30 fps, -16 LUFS), `work/words.json`. Read the printed transcript and check nothing is missing.
Fix whisper mistakes later with `replace` in the plan; never invent words the person did not say.

## 3. Person mask (for text/maps behind the head)
`mask.py work/talk.mp4 work/mask.raw` → prints where the top of the head is. Apple Vision on macOS, MediaPipe elsewhere.

## 4. Hook (on screen from the very first frame)
Three lines: small (≈80 px) above the head, BIG (180–260 px) whose baseline sits 60–90 px below the head top so the head covers
the lower part of the letters, small (≈80 px) on the chest (y ≈ 1330). Keep every line ≤ 880 px wide.
It must stop the scroll AND be true to what the video shows (no promises the video doesn't deliver).
Set `hook.end` to the start of the next spoken phrase and add the same range to `no_captions`.

## 5. Optional B-roll — `broll.py work/broll.json`
- Screenshots (articles, posts, dashboards) or footage the user owns or has rights to. Credit sources in the post caption.
- Get circle/notes coordinates in source pixels: `grid.py shot.png work/shot_grid.jpg` (zoom with `--crop`).
- `"size": "split"` → clips 1080x960 for the top half (speaker shown below, captions on the seam); `"full"` → whole screen.
- Use `focus` for a quick push-in on a box, or explicit `cam` keys. Circles appear when the word is said; notes 0.4–0.8 s later.
- Blur private data (names, emails, faces of private people, balances) with `blur`.
- Place each clip in `plan.json` → `broll`, with `at` = time of the word where it starts (from `words.json`), `dur` until the phrase ends.
- A `checklist` clip ticks items at given times: perfect for the "what to do" part.

## 6. Optional floating maps — `maps.py work/maps "Spain=españa" "Japan=japón" …`
English Natural Earth names; simple flags are filled in, others are white. Add them as `floaters` timed to the moment each
country is said: drift across ~2.5 s, `behind: true` to pass behind the head (needs the mask). Hide word captions during a
spoken list of countries (`no_captions`): the maps carry the names.

## 7. Plan + render
Write `work/plan.json` (see `examples/plan.example.json`): `emphasis` = the 1 key word per phrase that should be big
(numbers, the keyword, the emotional word), `keep_caps` for acronyms, `keep_together` for pairs that must not split.
Run `render.py work/plan.json` → `work/final.mp4`.

## 8. Check before handing over
`frames.py work/final.mp4 work/check.jpg <times>` with the hook, every B-roll, close-ups, the end. Look at the image and fix:
- caption covering the mouth → raise `style.body_y` (chest is ~1340); captions over busy screenshots → B-roll needs its dark bottom
  (`shade`, default on);
- hook letters fully hidden by the head → move the big line up 30–40 px;
- circle not around the right words → fix the box from `grid.py`.
Re-render after each fix. Then tell the user where `final.mp4` is, what was cut, and anything you could not verify.

## Style rules (what makes it look good)
- lowercase everywhere except acronyms; white, no boxes, no colours; at most ONE big word per block;
- captions never over the mouth; nothing outside x 100–980 or below y 1600 (Instagram/TikTok buttons and captions);
- music: leave it out; the user adds a licensed song in the app.
