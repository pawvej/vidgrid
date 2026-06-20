"""Vidgrid MCP server — give a remote AI assistant (Claude.ai, ChatGPT,
Claude Desktop, Claude Code, Cursor, …) eyes for video.

Wraps the managed render API at api.vidgrid.site. The tool uploads a local
video file and returns the grid frames as image content blocks, so the host
model literally *sees* the video, plus the transcript as text.

Auth: set VIDGRID_API_KEY=vg_live_... in the environment. Get a key at
https://vidgrid.site/api (free starter credits with email, or buy with the
slider).

Run locally:
    pip install -e .          # or: pip install mcp[cli] httpx
    VIDGRID_API_KEY=vg_live_... vidgrid-mcp

Add to Claude Code:
    claude mcp add vidgrid -e VIDGRID_API_KEY=vg_live_... -- vidgrid-mcp
"""
from __future__ import annotations

import base64
import os
from pathlib import Path

import httpx
from mcp.server.fastmcp import FastMCP, Image

API_BASE = os.environ.get("VIDGRID_API_BASE", "https://api.vidgrid.site").rstrip("/")
MAX_UPLOAD_BYTES = 200 * 1024 * 1024
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}

mcp = FastMCP("vidgrid")


def _auth_headers() -> dict[str, str]:
    key = os.environ.get("VIDGRID_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "VIDGRID_API_KEY is not set. Get one free at https://vidgrid.site/api "
            "(enter an email, click the link) and export it before starting the server."
        )
    return {"Authorization": f"Bearer {key}"}


def _validated_video_path(file_path: str) -> Path:
    path = Path(file_path).expanduser()
    if not path.is_file():
        raise RuntimeError(f"File not found or not a regular file: {file_path}")
    size = path.stat().st_size
    if size == 0:
        raise RuntimeError(f"File is empty: {file_path}")
    if size > MAX_UPLOAD_BYTES:
        raise RuntimeError(
            f"File is too large: {file_path} ({size} bytes, max {MAX_UPLOAD_BYTES}). "
            "Trim or re-encode it first."
        )
    if path.suffix.lower() not in VIDEO_EXTENSIONS:
        allowed = ", ".join(sorted(VIDEO_EXTENSIONS))
        raise RuntimeError(
            f"Refusing to upload non-video-looking file: {file_path}. "
            f"Allowed extensions: {allowed}."
        )
    return path


@mcp.tool()
def render_video(file_path: str, grid: str | None = None, transcribe: bool = True) -> list:
    """Turn a local video FILE into numbered frame-grid images (+ transcript) you can read.

    Use this whenever you need to "watch" or analyze a video you can't otherwise
    see: summarize a talk, find the exact moment something happens, read
    on-screen text/UI, or rank clips. Returns one or more grid PNGs — cells are
    numbered globally and each is tagged with its timestamp — plus the spoken
    transcript. Reason over the frames + transcript to answer; reference any
    frame by its number.

    Args:
        file_path: Path to a local video file (mp4/mov/webm/…). Max 5 minutes, max 200 MB.
            This tool does not fetch URLs — if you have a link, download it first.
        grid: "2x2" | "3x3" | "4x4" | "5x5". Omit to auto-pick (recommended).
        transcribe: Include the Whisper transcript alongside the frames (default True).

    Costs 1 credit. Failed renders are not charged.
    """
    path = _validated_video_path(file_path)

    data: dict[str, str] = {"transcribe": str(transcribe).lower()}
    if grid:
        data["grid"] = grid

    try:
        with path.open("rb") as fh:
            files = {"file": (path.name, fh, "application/octet-stream")}
            r = httpx.post(
                f"{API_BASE}/v1/render",
                files=files,
                data=data,
                headers=_auth_headers(),
                timeout=180.0,
            )
    except httpx.RequestError as e:
        raise RuntimeError(f"Could not reach vidgrid API: {e}") from e

    if r.status_code == 401:
        raise RuntimeError("Invalid or missing VIDGRID_API_KEY.")
    if r.status_code == 402:
        raise RuntimeError("Out of render credits — top up at https://vidgrid.site/api")
    if r.status_code == 413:
        raise RuntimeError("File too large (max 200 MB). Trim or re-encode it first.")
    if r.status_code == 400:
        raise RuntimeError(f"Bad request: {r.text[:200]}")
    r.raise_for_status()

    data = r.json()
    out: list = []
    for b in data.get("boards", []):
        out.append(Image(data=base64.b64decode(b["png_base64"]), format="png"))

    transcript = data.get("transcript")
    if transcript:
        try:
            words = " ".join(w.get("text", "") for w in transcript)
        except (TypeError, AttributeError):
            words = str(transcript)
        out.append(f"Transcript:\n{words}")

    out.append(
        f"{len(data.get('boards', []))} board(s) · {data.get('duration_seconds')}s video · "
        f"credits remaining: {data.get('credits_remaining')}."
    )
    return out


@mcp.tool()
def check_balance() -> str:
    """Return the remaining Vidgrid render credits for the configured API key."""
    r = httpx.get(f"{API_BASE}/v1/usage", headers=_auth_headers(), timeout=30.0)
    r.raise_for_status()
    d = r.json()
    paid = (d.get("lifetime_cents_paid", 0) or 0) / 100.0
    return (
        f"Credits remaining: {d.get('credits_remaining')}. "
        f"Key: {d.get('key_prefix')}. Lifetime paid: ${paid:.2f}."
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
