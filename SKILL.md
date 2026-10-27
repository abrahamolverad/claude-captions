---
name: captions
description: |
  Edit a talking-head video into a finished vertical Reel/TikTok/Short with minimalist "Helvetica" captions: lowercase bold
  words that pop in one by one, one big key word per phrase, the hook's big word BEHIND the speaker's head, plus optional
  B-roll (news screenshots or footage with hand-drawn red circles and handwritten notes, full screen or split screen),
  floating country maps that pass behind/in front of the speaker, and an animated checklist.
  Use when the user drops a video and asks to "add captions", "edit this video", "subtítulos", "edita este video",
  "pon captions", "hazlo como Reel", "text behind my head", "split screen", "mapas de países", or similar.
  Also the DICTATION mode: the person records the edit commands ON CAMERA ("ponle captions", "pon el color azul",
  "haz un close in", "subtítulos en japonés", "pon la bandera de México aquí", "corta la escena", "blanco y negro",
  "pon música", "un millón de followers") and Claude cuts the hesitations and executes each command at the moment it is said.
  Use it when the user says "dictado", "sigue las instrucciones del video", "haz lo que digo en el video", "dictation",
  "follow the commands in the video", "edit it the way I say it".
---

# captions · Helvetica captions + B-roll for vertical videos

Everything is rendered locally with Python + ffmpeg. Scripts live in `scripts/`; run them with the skill's own Python:
- macOS/Linux: `<skill>/.venv/bin/python <skill>/scripts/<script>.py …`
- Windows: `<skill>\.venv\Scripts\python.exe <skill>\scripts\<script>.py …`
(`<skill>` is this folder, usually `~/.claude/skills/captions`.) Keep every working file in a `work/` folder next to the user's video.

## Quick commands (`/captions <command> …`)
The user may type one of these right after `/captions` (Spanish or English word). Each one is a complete job:
run the steps below that it needs (0 → 3 always: setup if missing, cut, transcribe, mask), add its effect, render, check frames,
and hand back `work/final.mp4`. Without a command (`/captions video.mp4` or plain words) do the full edit: cut + captions + hook.

| Command | What to make |
|---|---|
| `/captions VIDEO` | Full edit: drop mistakes and repeated takes, word-by-word captions, a hook written from what the video says. |
| `/captions hook VIDEO "small / BIG / small"` (`gancho`) | That exact 3-line hook from frame 0, the BIG word behind the head. |
| `/captions maps VIDEO País 1, País 2, …` (`mapas`) | Each country's map floats past (behind the head when possible) at the moment it is said; no word captions during the list. |
| `/captions split VIDEO IMAGE "words to circle"` (`dividida`) | Split screen: the image on top (1080x960) while the related phrase is said, red circle around those words, captions on the seam. |
| `/captions circle VIDEO IMAGE "words to circle" ["note"]` (`circulo`) | Full-screen image with a push-in, red circle and an optional handwritten note, over the matching phrase. |
| `/captions checklist VIDEO step 1; step 2; step 3` | Animated checklist (split screen) that ticks each step when it is said, or every ~1.2 s if the steps are not spoken. |
| `/captions behind VIDEO "WORD"` (`detras`) | One big word behind the speaker's head at the most important moment (not only the hook). |
| `/captions dictado VIDEO` (`dictation`) | The person dictates the edit on camera: cut the hesitations, keep the last take of each command and execute every command where it is said (section "Dictation mode"). |

Find words to circle in an image with `grid.py` (or ask the user if they are not visible). If a file is missing, ask for it.

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

## Dictation mode (`/captions dictado VIDEO`)
The person talks to the camera and SAYS the edit: every sentence is either content or a command, and a command applies from
the moment its key word is spoken. The video is usually improvised: cut every hesitation, false start and "ok / no / wait".
1. `transcribe.py` the raw file. Read it as a script: list each command with its time, and mark retakes (the same command said
   twice → keep the LAST complete one; "pon música… pon una música motivacional" → keep the second). Drop fillers ("ok",
   "eso", "no", "lo voy a dejar así") and anything after the final call to action. Keep the person's speed: `--keep` ranges
   tight, `--protect` only where a command needs a beat to land (music starts, a flag pops).
2. `cut.py` with those ranges → `work/talk.mp4`, `work/words.json`. Read the cut transcript: whisper often mangles command
   words ("close in" → "closing", "hindi" → "indie"): fix them with `replace` in the plan (never invent words).
3. Build the timeline from `words.json` (cut timeline) and map each command to its effect:

| What they say (es / en) | Effect | Where |
|---|---|---|
| «ponle captions», «todos estos captions» | word-by-word captions as always | plan.json |
| «pon el color azul / amarillo / naranja» | that caption WORD in that colour (`colors`), the picture stays normal | plan.json `colors` |
| «haz un close in» / «close out» (zoom in / out) | punch-in 1.3 at the word, back out at "close out" | fx.json `zoom` |
| «subtítulos en japonés, hindi e inglés» | translated subtitle lines under the captions, each one appearing when its language is named, and still translating the NEXT sentence | overlay.json `subtitles` |
| «la bandera de México aquí … Estados Unidos acá» | flag emoji where the person points (look at the frame: left or right, top) | overlay.json `stickers` (emoji) |
| «corta la escena» (cut) | 5–6 black frames right after the sentence + an impact SFX | fx.json `black`, plan `sfx` |
| «hazme en blanco y negro» | B&W from the word "negro" until the next command that brightens the mood ("música alegre") or the end | fx.json `bw` |
| «pon música», «música motivacional», «cambia la música», «música alegre» | a track from the user's `music/` folder at that word, swapped at the next music command, low (gain 0.12–0.2) under the voice | overlay.json `music` |
| «pon números…», «un millón de followers», «125 mil habitantes» | counter that counts up above the head with the label | overlay.json `counters` |
| «ponle un icono de gente» | icon next to that counter (`icon: "people"`, any emoji, or an image) | overlay.json `counters.icon` |
| «el hook que diga…», «agrega la mascota / este sticker» | hook words placed AROUND the person (`floaters` of word PNGs, the big one `behind`) and the image as a sticker from frame 0; `remove_white` strips a white background | plan `floaters` / overlay `stickers` |

   Commands the table does not cover: do the nearest thing with the same tools and say so. Music only from files the user
   gives (licensed); with no files, leave the music out and tell them.
4. Order of the render: `fx.py` on `talk.mp4` → `talk_fx.mp4` (zoom, B&W, black, tint) → `mask.py` on `talk.mp4` (the hook is
   never zoomed) → `render.py` with `"video": "talk_fx.mp4"` (captions, colours, hook, floaters, SFX) → `overlay.py`
   (subtitles, stickers, counters, music) → `work/final.mp4`.
5. Check frames at every command (`frames.py`): the colour is on the right word, the zoom lands on the word, flags sit where
   the hand points, counters never cover the face, subtitles stay above y 1750. Tell the user what was cut and every judgment
   call you made (which sentence the subtitles translate, when colour came back after B&W, which track went where).

Hook in this mode: if the person asks for a phrase ("Claude, el mejor editor de videos") render each word group as a PNG
(`word_sprite` in overlay.py or `sprite` in render.py) and place them around the head with `floaters` (`t0` slightly negative so
all are complete at frame 0; the big word `behind: true`); a mascot or logo goes in as a sticker next to them.

## Style rules (what makes it look good)
- lowercase everywhere except acronyms; white, no boxes; colour only when the person asks for it on a word (`colors`); at most ONE big word per block;
- captions never over the mouth; nothing outside x 100–980 or below y 1600 (Instagram/TikTok buttons and captions);
- music: leave it out; the user adds a licensed song in the app.
