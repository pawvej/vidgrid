"""Command-line entry point for vidgrid.

Core rule: each cell is exactly 1 second of video. Grid size determines how
many seconds fit in one photo. Longer videos produce more photos.

Usage:
    vidgrid clip.mp4 -o grid.png
    vidgrid clip.mp4 -o grid.png --grid 4x4
    vidgrid clip.mp4 -o grid.png --transcribe
    vidgrid clip.mp4 --ask "describe what happens" --model claude-opus-4-7
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from vidgrid import __version__
from vidgrid.api import render
from vidgrid.captions import captions_to_prompt_text, load_captions
from vidgrid.llm import DEFAULT_CLAUDE_MODEL, LLMError, call
from vidgrid.presets import DEFAULT_MAX_BOARDS, MAX_DURATION_SECONDS, VideoTooLong


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vidgrid",
        description=(
            "Convert video clips into annotated image grids for vision LLM "
            "analysis. Each cell is 1 second of video. Grid size determines "
            "how many seconds fit in one photo."
        ),
        epilog=(
            "Grid sizes and cell counts:\n"
            "  2x2 =  4 cells (best for 2-4s clips)\n"
            "  3x3 =  9 cells (DEFAULT, best overall readability)\n"
            "  4x4 = 16 cells (smaller cells, acceptable for most content)\n"
            "  5x5 = 25 cells (experimental, cells become small and hard\n"
            "                  to read — expect lower LLM accuracy)\n\n"
            "Rule of thumb: bigger grids fit more seconds per photo but\n"
            "each cell gets smaller, which hurts detail and LLM comprehension.\n"
            "Stick to 3x3 unless you specifically need to compress more time.\n\n"
            "Max video length: 5 minutes by default. Longer videos are\n"
            "rejected — chop them up first with ffmpeg."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("input", help="Path to the source video file")
    parser.add_argument(
        "-o", "--output",
        help=(
            "Output PNG path. Multi-board output writes <stem>-1.png, "
            "<stem>-2.png, etc. Optional when using only --ask."
        ),
    )
    parser.add_argument(
        "--grid",
        choices=["2x2", "3x3", "4x4", "5x5"],
        default=None,
        help=(
            "Grid size. Default: auto — picks the smallest grid (biggest "
            "cells) that fits within --max-boards."
        ),
    )
    parser.add_argument(
        "--fps",
        type=float,
        default=None,
        help=(
            "Sampling rate in frames per second. Default: auto (1fps for "
            "short videos, reduced for longer ones to stay within "
            "--max-boards)."
        ),
    )
    parser.add_argument(
        "--max-boards",
        type=int,
        default=DEFAULT_MAX_BOARDS,
        help=(
            f"Maximum number of board images to produce. The auto-picker "
            f"chooses the smallest grid that stays within this limit. "
            f"Default: {DEFAULT_MAX_BOARDS}."
        ),
    )
    parser.add_argument(
        "--max-duration",
        type=int,
        default=MAX_DURATION_SECONDS,
        help=(
            f"Reject videos longer than this many seconds. "
            f"Default: {MAX_DURATION_SECONDS} (5 min)."
        ),
    )
    parser.add_argument(
        "--transcribe",
        action="store_true",
        help="Run faster-whisper on the video's audio for captions",
    )
    parser.add_argument(
        "--captions",
        help=(
            "Path to an existing captions file. Format is auto-detected "
            "from the extension: .json (Remotion), .srt, or .txt."
        ),
    )
    parser.add_argument(
        "--transcript-format",
        choices=["json", "srt", "txt"],
        default="json",
        help=(
            "Format for the transcript sidecar written alongside the grid. "
            "json = Remotion-compatible (default, verbose), "
            "srt = SubRip subtitles, "
            "txt = plain timestamped text (smallest)."
        ),
    )
    parser.add_argument(
        "--burn-captions",
        action="store_true",
        help="Render a caption strip below each cell (one-layer mode)",
    )
    parser.add_argument(
        "--ask",
        help="Prompt to send to a vision LLM with the rendered grid(s)",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_CLAUDE_MODEL,
        help=f"LLM model name (default: {DEFAULT_CLAUDE_MODEL})",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress progress output",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"vidgrid {__version__}",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.transcribe and args.captions:
        parser.error("Use either --transcribe or --captions, not both")

    if not args.output and not args.ask:
        parser.error("Provide -o/--output or --ask (or both)")

    input_path = Path(args.input)
    if not input_path.exists():
        parser.error(f"Input video not found: {args.input}")

    output_path = args.output
    using_temp_output = False
    if not output_path:
        import tempfile
        tmp_dir = tempfile.mkdtemp(prefix="vidgrid-out-")
        output_path = str(Path(tmp_dir) / f"{input_path.stem}.png")
        using_temp_output = True

    log = (lambda *a, **k: None) if args.quiet else _log

    log(f"Probing {args.input}...")
    try:
        storyboard = render(
            input_path=str(input_path),
            output_path=output_path,
            grid=args.grid,
            fps=args.fps,
            max_boards=args.max_boards,
            max_duration_seconds=args.max_duration,
            captions_path=args.captions,
            transcribe=args.transcribe,
            burn_captions=args.burn_captions,
            transcript_format=args.transcript_format,
        )
    except VideoTooLong as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    log(
        f"Rendered {len(storyboard.boards)} board(s), "
        f"{sum(len(b.cells) for b in storyboard.boards)} cells total "
        f"(grid: {storyboard.preset.layout.label})"
    )
    for path in storyboard.board_paths:
        log(f"  -> {path}")
    if storyboard.sidecar_path:
        log(f"  -> {storyboard.sidecar_path}")
    if storyboard.transcript_path:
        log(f"  -> {storyboard.transcript_path}")

    if args.ask:
        log(f"Sending to {args.model}...")

        transcript_text = None
        if storyboard.transcript_path:
            transcript_captions = load_captions(storyboard.transcript_path)
            transcript_text = captions_to_prompt_text(transcript_captions) or None

        try:
            response = call(
                image_paths=storyboard.board_paths,
                prompt=args.ask,
                transcript=transcript_text,
                model=args.model,
            )
        except LLMError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2

        print(response)

        if using_temp_output:
            log(f"(temporary output at {output_path})")

    return 0


def _log(*args, **kwargs) -> None:
    print(*args, file=sys.stderr, **kwargs)


if __name__ == "__main__":
    raise SystemExit(main())
