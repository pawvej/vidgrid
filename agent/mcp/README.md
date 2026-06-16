# vidgrid-mcp

<!-- mcp-name: io.github.pawvej/vidgrid -->

MCP server that gives an AI assistant **eyes for video**. It wraps the
[vidgrid](https://vidgrid.site) render API: hand it a local video file and it
returns the numbered frame grid as image blocks (the model literally sees the
video) plus the transcript.

## Install & run

```bash
uvx vidgrid-mcp                        # zero-install (recommended)
# or: pip install vidgrid-mcp
export VIDGRID_API_KEY=vg_live_...     # get one at https://vidgrid.site/api
vidgrid-mcp
```

## Add to Claude Code

```bash
claude mcp add vidgrid -e VIDGRID_API_KEY=vg_live_... -- uvx vidgrid-mcp
```

## Tools

- **`render_video(file_path, grid?, transcribe?)`** — upload a local video file
  (mp4/mov/webm, ≤5 min, ≤200 MB); returns the grid PNG(s) + transcript. Costs 1
  credit; failed renders aren't charged. Does **not** fetch URLs — download a
  link to a file first.
- **`check_balance()`** — remaining render credits for the configured key.

Env: `VIDGRID_API_KEY` (required), `VIDGRID_API_BASE` (default
`https://api.vidgrid.site`).
