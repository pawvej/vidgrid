"""Caption loading, writing, phrase windowing, and optional Whisper transcription.

Captions are represented internally as a list of Remotion-style dicts:
    [{"text": " word", "startMs": int, "endMs": int, "timestampMs": int, "confidence": float}, ...]

vidgrid can read and write three on-disk formats:

1. **json** (default, Remotion-compatible)
   Verbose but preserves word-level timing and confidence. Required by the
   indiehacker-news pipeline because Remotion reads this exact shape.

2. **srt** (SubRip subtitle, industry standard)
   Every video editor understands it. One entry per word. Easy to share,
   easy to edit in a text editor.

3. **txt** (plain timestamped text)
   The simplest possible format. One word per line, prefixed by its start
   time in seconds. Trivial to parse, smallest file on disk.

Auto-detection on load uses the file extension. Writes either use an
explicit format argument or infer from the output path's extension.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List, Optional

from vidgrid.models import CaptionPhrase

SUPPORTED_FORMATS = ("json", "srt", "txt")


# ---------- loading ----------

def load_captions(captions_path: str) -> List[dict]:
    """Load captions from disk. Auto-detects format from file extension.

    Supported: .json, .srt, .txt. Anything else is treated as JSON.
    Returns an empty list on missing file or parse failure.
    """
    path = Path(captions_path)
    if not path.exists():
        return []

    ext = path.suffix.lower().lstrip(".")
    content = path.read_text(errors="replace")

    if ext == "srt":
        return _parse_srt(content)
    if ext == "txt":
        return _parse_txt(content)
    return _parse_json(content)


def _parse_json(content: str) -> List[dict]:
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return data


_SRT_TIME_RE = re.compile(
    r"(\d{1,2}):(\d{2}):(\d{2})[,\.](\d{1,3})\s*-->\s*"
    r"(\d{1,2}):(\d{2}):(\d{2})[,\.](\d{1,3})"
)


def _parse_srt(content: str) -> List[dict]:
    """Parse an SRT file into the internal caption dict format."""
    blocks = re.split(r"\n\s*\n", content.strip())
    captions: List[dict] = []
    for block in blocks:
        lines = [ln for ln in block.strip().splitlines() if ln.strip()]
        if len(lines) < 2:
            continue
        # First line is usually an index, but some SRT files skip it
        if lines[0].isdigit():
            time_line = lines[1] if len(lines) >= 3 else None
            text_lines = lines[2:]
        else:
            time_line = lines[0]
            text_lines = lines[1:]

        if not time_line:
            continue
        match = _SRT_TIME_RE.search(time_line)
        if not match:
            continue
        h1, m1, s1, ms1, h2, m2, s2, ms2 = (int(x) for x in match.groups())
        start_ms = h1 * 3600_000 + m1 * 60_000 + s1 * 1000 + ms1
        end_ms = h2 * 3600_000 + m2 * 60_000 + s2 * 1000 + ms2
        text = " ".join(text_lines).strip()
        if not text:
            continue
        captions.append(
            {
                "text": f" {text}" if captions else text,
                "startMs": start_ms,
                "endMs": end_ms,
                "timestampMs": start_ms,
                "confidence": 1.0,
            }
        )
    return captions


def _parse_txt(content: str) -> List[dict]:
    """Parse plain timestamped text (`<seconds> <word>` per line).

    Each line looks like:
        0.00 hello
        0.50 world

    The end timestamp of word N is set to the start of word N+1 (or
    start + 500ms for the last word).
    """
    captions: List[dict] = []
    for raw in content.splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) < 2:
            continue
        try:
            start_s = float(parts[0])
        except ValueError:
            continue
        text = parts[1]
        start_ms = int(round(start_s * 1000))
        captions.append(
            {
                "text": f" {text}" if captions else text,
                "startMs": start_ms,
                "endMs": start_ms,  # fixed below
                "timestampMs": start_ms,
                "confidence": 1.0,
            }
        )
    # Fill in endMs by using the next word's start, last word gets +500ms
    for i in range(len(captions) - 1):
        captions[i]["endMs"] = captions[i + 1]["startMs"]
    if captions:
        captions[-1]["endMs"] = captions[-1]["startMs"] + 500
    return captions


# ---------- writing ----------

def write_captions(
    captions: List[dict],
    output_path: str,
    format: Optional[str] = None,
) -> str:
    """Write captions to disk in the requested format.

    If `format` is None, infer from the output_path's extension. Returns
    the resolved output path (unchanged from input).
    """
    path = Path(output_path)
    if format is None:
        ext = path.suffix.lower().lstrip(".")
        format = ext if ext in SUPPORTED_FORMATS else "json"

    if format == "json":
        path.write_text(json.dumps(captions, indent=2))
    elif format == "srt":
        path.write_text(_to_srt(captions))
    elif format == "txt":
        path.write_text(_to_txt(captions))
    else:
        raise ValueError(
            f"Unknown caption format '{format}'. "
            f"Supported: {', '.join(SUPPORTED_FORMATS)}"
        )

    return str(path)


def _ms_to_srt_time(ms: int) -> str:
    """Convert milliseconds to SRT time format HH:MM:SS,mmm."""
    ms = max(0, int(ms))
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _to_srt(captions: List[dict]) -> str:
    lines: List[str] = []
    for i, cap in enumerate(captions, start=1):
        start = _ms_to_srt_time(cap.get("startMs", 0))
        end = _ms_to_srt_time(cap.get("endMs", cap.get("startMs", 0) + 500))
        text = str(cap.get("text", "")).strip()
        if not text:
            continue
        lines.append(str(i))
        lines.append(f"{start} --> {end}")
        lines.append(text)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _to_txt(captions: List[dict]) -> str:
    lines: List[str] = []
    for cap in captions:
        text = str(cap.get("text", "")).strip()
        if not text:
            continue
        seconds = cap.get("startMs", 0) / 1000.0
        lines.append(f"{seconds:.2f} {text}")
    return "\n".join(lines) + ("\n" if lines else "")


# ---------- phrase windowing ----------

def phrase_for_timestamp(
    captions: List[dict],
    t_ms: int,
    *,
    before_ms: int = 900,
    after_ms: int = 1400,
    max_words: int = 12,
    max_chars: int = 80,
) -> Optional[CaptionPhrase]:
    """Return a phrase window centered on a frame timestamp.

    Single isolated words look terrible under cells. Instead, we grab the
    words that fall inside a window around the frame's timestamp and trim to
    a reasonable word/char count so the caption strip stays legible.
    """
    if not captions:
        return None

    window_start = t_ms - before_ms
    window_end = t_ms + after_ms

    in_window: List[dict] = []
    for cap in captions:
        start = cap.get("startMs", 0)
        end = cap.get("endMs", start)
        if end >= window_start and start <= window_end:
            in_window.append(cap)

    if not in_window:
        return None

    words = [str(cap.get("text", "")).strip() for cap in in_window if cap.get("text")]
    if not words:
        return None

    if len(words) > max_words:
        words = words[:max_words]
        ellipsis = "…"
    else:
        ellipsis = ""

    text = " ".join(words).strip()
    if len(text) > max_chars:
        text = text[: max_chars - 1].rstrip() + "…"
    elif ellipsis:
        text = text + ellipsis

    return CaptionPhrase(
        text=text,
        start_ms=in_window[0].get("startMs", 0),
        end_ms=in_window[-1].get("endMs", 0),
    )


# ---------- optional: transcribe a video directly ----------

def transcribe_video(
    video_path: str,
    output_path: Optional[str] = None,
    format: Optional[str] = None,
) -> List[dict]:
    """Transcribe a video's audio with faster-whisper.

    Returns the captions list. If `output_path` is provided, also writes
    the captions there in the chosen format (auto-detected from the path
    extension if `format` is None).

    Raises:
        ImportError: if faster-whisper is not installed
        RuntimeError: if transcription fails
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise ImportError(
            "faster-whisper is required for --transcribe. "
            "Install with: pip install vidgrid[transcribe]"
        ) from e

    model = WhisperModel("base", compute_type="int8")
    try:
        segments, _ = model.transcribe(video_path, word_timestamps=True)
    except Exception as e:
        raise RuntimeError(f"Whisper transcription failed: {e}") from e

    captions: List[dict] = []
    for segment in segments:
        if not segment.words:
            continue
        for word_info in segment.words:
            word_text = word_info.word.strip()
            if not word_text:
                continue
            caption_text = f" {word_text}" if captions else word_text
            captions.append(
                {
                    "text": caption_text,
                    "startMs": round(word_info.start * 1000),
                    "endMs": round(word_info.end * 1000),
                    "timestampMs": round(word_info.start * 1000),
                    "confidence": float(
                        getattr(word_info, "probability", 1.0) or 1.0
                    ),
                }
            )

    if output_path:
        write_captions(captions, output_path, format=format)

    return captions


def captions_to_prompt_text(captions: List[dict]) -> str:
    """Format captions as a plain-text transcript for LLM prompts.

    Groups words into short lines with timestamps at the start of each line.
    Example:
        [0:00] we just hit three hundred thousand in MRR
        [0:05] and we still have no funding
    """
    if not captions:
        return ""

    lines: List[str] = []
    current_words: List[str] = []
    current_start_ms: Optional[int] = None
    line_char_cap = 80

    def flush():
        nonlocal current_words, current_start_ms
        if not current_words:
            return
        ts_s = (current_start_ms or 0) // 1000
        m, s = divmod(ts_s, 60)
        prefix = f"[{m}:{s:02d}] "
        lines.append(prefix + " ".join(current_words).strip())
        current_words = []
        current_start_ms = None

    for cap in captions:
        text = str(cap.get("text", "")).strip()
        if not text:
            continue
        if current_start_ms is None:
            current_start_ms = cap.get("startMs", 0)
        current_words.append(text)
        running = " ".join(current_words)
        if len(running) >= line_char_cap or text.endswith((".", "!", "?")):
            flush()

    flush()
    return "\n".join(lines)
