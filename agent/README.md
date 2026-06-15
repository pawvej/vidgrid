# vidgrid for agents

Three ways to give an AI agent eyes for video. All of them turn a **local video
file** into a numbered frame grid (+ transcript) a vision model can read. None
of them fetch URLs — if you have a link, download it to a file first.

| Surface | Install | Best for |
|---|---|---|
| **Skill** ([`SKILL.md`](SKILL.md)) | drop into a skills dir | Claude Code / agents that load skill files |
| **npm CLI** ([`cli/`](cli/)) | `npx @vidgrid/cli clip.mp4` | any agent that can run a shell command |
| **MCP server** ([`mcp/`](mcp/)) | `claude mcp add vidgrid …` | Claude Desktop / Cursor / MCP hosts |

All three call the managed render API (`POST https://api.vidgrid.site/v1/render`,
multipart file upload) and need a key:

```bash
export VIDGRID_API_KEY="vg_live_..."     # get one at https://vidgrid.site/api
```

1 render = 1 credit, credits never expire, failed renders are never charged.

Prefer fully local with no key and no upload? The open-source Python CLI renders
on your machine with ffmpeg: `uvx vidgrid clip.mp4 -o grid.png`.
