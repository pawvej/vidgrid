# vidgrid (npm CLI)

Turn a local video file into a numbered frame grid an AI can read. Thin,
zero-dependency client for the [vidgrid](https://vidgrid.site) render API.

```bash
export VIDGRID_API_KEY="vg_live_..."        # get one at https://vidgrid.site/api
npx vidgrid clip.mp4                          # → grid.png (+ grid-transcript.txt)
npx vidgrid talk.mp4 --grid 4x4 --out talk
npx vidgrid screen.mov --no-transcribe
```

It uploads the file to `POST /v1/render`, writes the grid PNG(s) and transcript
next to you, and prints your remaining credits. Requires Node 18+.

| Option | Meaning |
|---|---|
| `--grid 2x2\|3x3\|4x4\|5x5` | Force a grid size (default: auto). |
| `--no-transcribe` | Skip the Whisper transcript. |
| `--out <name>` | Output prefix (default: `grid`). |

Env: `VIDGRID_API_KEY` (required), `VIDGRID_API_BASE` (default
`https://api.vidgrid.site`).

Prefer fully local, no key, no upload? Use the open-source Python CLI:
`uvx vidgrid clip.mp4 -o grid.png`.
