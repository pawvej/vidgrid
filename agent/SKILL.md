---
name: vidgrid
description: Give an AI agent eyes for video. Turn a local video file (MP4, MOV, WebM) into a numbered grid of frames plus a transcript that a vision model can read — so you can summarize a talk, find the exact moment something happens, read on-screen text or UI, or rank clips. Use whenever you need to watch, analyze, or understand a video file you can't directly see.
homepage: https://vidgrid.site
metadata:
  api_base: https://api.vidgrid.site
---

# vidgrid — let an AI watch a video

LLMs can't watch video, but they can read a single image. `vidgrid` samples one
frame per second from a video file, tiles them into a **numbered storyboard**
with timestamps, and (optionally) returns the spoken transcript. The result is
close to "my model just watched a video" for the price of a few image uploads.

Each cell is numbered **globally** (1, 2, 3…) and tagged with its timestamp, so
you can point at an exact moment ("the dialog appears at frame 14, ~0:14").

> Input is a **local video file you provide**. vidgrid does not fetch URLs — if
> you have a link, download it yourself first, then hand the file to vidgrid.

## When to use this

- Summarize a talk / meeting / lecture without anyone watching it
- Find the moment something happens in a screen recording or bug repro
- Read on-screen text, UI state, or slides from a video
- Rank or reject a batch of clips against a shot list
- Any task where you have a video file and need to reason about its content

## Setup (one time)

You need a Vidgrid API key. The user can get one in ~20 seconds at
**https://vidgrid.site/api** (enter an email → click the link → a key
`vg_live_…` with starter credits arrives by email; or buy credits with the
slider). Then:

```bash
export VIDGRID_API_KEY="vg_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

Credits never expire. **1 render = 1 credit.** Failed renders are never charged.

## Fastest path — the CLI (zero-install)

```bash
npx @vidgrid/cli clip.mp4                 # → grid.png (+ grid-transcript.txt), prints credits left
npx @vidgrid/cli talk.mp4 --grid 4x4 --out talk
npx @vidgrid/cli screen.mov --no-transcribe
```

`npx @vidgrid/cli <file>` uploads the file to the render API and writes the numbered
grid PNG(s) next to you. Read the PNG(s) to "watch" the video; combine with the
transcript to answer. Needs `VIDGRID_API_KEY` in the environment.

## Or call the API directly

`POST https://api.vidgrid.site/v1/render` — **multipart file upload**:

```bash
curl -X POST https://api.vidgrid.site/v1/render \
  -H "Authorization: Bearer $VIDGRID_API_KEY" \
  -F file=@clip.mp4 \
  -F transcribe=true
```

Form fields:

| field | type | default | notes |
|---|---|---|---|
| `file` | file (required) | — | The video. **Max 5 minutes, max 200 MB.** |
| `grid` | string | auto | `"2x2"`, `"3x3"`, `"4x4"`, `"5x5"`. Omit to auto-pick the most legible grid that fits in ≤10 boards. |
| `transcribe` | bool | `true` | Return the Whisper transcript alongside the frames. |

Response (`200`):

```json
{
  "boards": [{ "index": 0, "layout": "3x3", "png_base64": "iVBORw0KGgo..." }],
  "transcript": [ { "text": "hello", "startMs": 0, "endMs": 500 } ],
  "duration_seconds": 19.0,
  "source": { "width": 640, "height": 480, "fps": 30.0 },
  "render_ms": 4200,
  "credits_remaining": 99,
  "render_id": "a1b2c3..."
}
```

Decode each `boards[].png_base64` and look at it — the numbered cells ARE the
video, one cell per second. Correlate with the `transcript` via the timestamps
on each cell. Long videos return several boards; cells stay numbered
continuously across them (board 1 = cells 1–9, board 2 = cells 10–18, …).

### Errors

| status | `error` | meaning |
|---|---|---|
| 400 | `empty_file` / `invalid_grid` | No file, or a bad grid value. |
| 400 | `video_too_long` | Over the 5-minute cap. Trim first: `ffmpeg -ss 0 -t 300 in.mp4 out.mp4`. |
| 413 | `file_too_large` | Over 200 MB. Re-encode smaller or trim. |
| 401 | `missing_key` / `invalid_key` | Set/refresh `VIDGRID_API_KEY`. |
| 402 | `insufficient_credits` | Top up at https://vidgrid.site/api. |
| 429 | `rate_limited` | Back off; honor `Retry-After`. |

Check remaining credits anytime: `GET /v1/usage` with the same Bearer key.

## Fully local alternative — the open-source CLI (free, no key, no upload)

If you have `ffmpeg` and want to render locally without the API:

```bash
uvx vidgrid clip.mp4 -o grid.png                 # zero-install (uv)
# or: pip install vidgrid && vidgrid clip.mp4 -o grid.png
vidgrid talk.mp4 --transcribe --ask "list the decisions and who owns each"
```

The Python CLI (MIT, on PyPI) renders entirely on your machine — use it when you
have ffmpeg; use `npx @vidgrid/cli` / the API when you want server-side rendering.

## Notes for agents

- Prefer **auto** grid; only override when the user needs more seconds per image.
- The API/CLI does not call an LLM — it returns frames + transcript and *you*
  (the model reading this) do the analysis.
- One render covers one ≤5-min video. For a long video, trim into ≤5-min chunks
  and render each; cite frames by chunk.
