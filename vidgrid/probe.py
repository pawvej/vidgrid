"""Video probing via ffprobe.

Extracts the minimal metadata vidgrid needs: duration, dimensions, fps.
Uses subprocess against system ffprobe (no ffmpeg-python dependency).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from vidgrid.models import VideoInfo


class ProbeError(RuntimeError):
    """Raised when ffprobe fails or returns unexpected data."""


def probe(video_path: str) -> VideoInfo:
    """Run ffprobe against a video file and return structured metadata.

    Raises:
        FileNotFoundError: if the video file does not exist
        ProbeError: if ffprobe fails or the video has no video stream
    """
    path = Path(video_path)
    if not path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate,duration",
        "-show_entries", "format=duration",
        "-of", "json",
        str(path),
    ]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=True, timeout=30
        )
    except FileNotFoundError as e:
        raise ProbeError("ffprobe not found on PATH. Install ffmpeg.") from e
    except subprocess.CalledProcessError as e:
        raise ProbeError(f"ffprobe failed: {e.stderr.strip()}") from e
    except subprocess.TimeoutExpired as e:
        raise ProbeError(f"ffprobe timed out on {video_path}") from e

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise ProbeError(f"ffprobe output was not JSON: {result.stdout[:200]}") from e

    streams = data.get("streams") or []
    if not streams:
        raise ProbeError(f"No video stream found in {video_path}")

    stream = streams[0]
    fmt = data.get("format") or {}

    width = _require_int(stream, "width", video_path)
    height = _require_int(stream, "height", video_path)

    duration_ms = _parse_duration_ms(stream.get("duration"), fmt.get("duration"))
    if duration_ms is None:
        raise ProbeError(f"Could not determine duration for {video_path}")

    fps = _parse_fps(stream.get("r_frame_rate"))

    return VideoInfo(
        path=str(path.resolve()),
        duration_ms=duration_ms,
        width=width,
        height=height,
        fps=fps,
    )


def _require_int(stream: dict, key: str, video_path: str) -> int:
    value = stream.get(key)
    if value is None:
        raise ProbeError(f"Missing '{key}' in ffprobe output for {video_path}")
    try:
        return int(value)
    except (TypeError, ValueError) as e:
        raise ProbeError(f"Invalid '{key}' value: {value!r}") from e


def _parse_duration_ms(stream_duration, format_duration) -> int | None:
    for candidate in (stream_duration, format_duration):
        if candidate is None:
            continue
        try:
            seconds = float(candidate)
        except (TypeError, ValueError):
            continue
        if seconds > 0:
            return int(round(seconds * 1000))
    return None


def _parse_fps(r_frame_rate) -> float:
    """Parse ffprobe's 'r_frame_rate' like '30000/1001' into a float."""
    if not r_frame_rate:
        return 30.0  # sensible default
    try:
        if "/" in r_frame_rate:
            num, den = r_frame_rate.split("/", 1)
            n, d = float(num), float(den)
            if d == 0:
                return 30.0
            return n / d
        return float(r_frame_rate)
    except (TypeError, ValueError):
        return 30.0
