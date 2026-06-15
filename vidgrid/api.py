"""Public Python API.

Integration scripts and other packages should import from here:

    from vidgrid import render

    storyboard = render(
        input_path="clip.mp4",
        output_path="grid.png",
        grid="3x3",  # or "2x2", "4x4", "5x5", or None for auto
    )
    print(storyboard.board_paths)
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import List, Optional

from vidgrid.captions import (
    SUPPORTED_FORMATS,
    load_captions,
    phrase_for_timestamp,
    transcribe_video,
    write_captions,
)
from vidgrid.models import Board, Cell, Storyboard
from vidgrid.output import write_boards, write_sidecar
from vidgrid.presets import DEFAULT_MAX_BOARDS, MAX_DURATION_SECONDS, preset_for
from vidgrid.probe import probe
from vidgrid.sample import sample_video

DEFAULT_TRANSCRIPT_FORMAT = "json"


def render(
    input_path: str,
    *,
    output_path: Optional[str] = None,
    grid: Optional[str] = None,
    fps: Optional[float] = None,
    max_boards: int = DEFAULT_MAX_BOARDS,
    max_duration_seconds: int = MAX_DURATION_SECONDS,
    captions_path: Optional[str] = None,
    transcribe: bool = False,
    burn_captions: bool = False,
    transcript_format: str = DEFAULT_TRANSCRIPT_FORMAT,
    work_dir: Optional[str] = None,
    cleanup_work_dir: bool = True,
) -> Storyboard:
    """Render a video into one or more annotated storyboards.

    Each cell represents exactly 1 second of video. Longer videos produce
    more boards, not denser grids.

    Args:
        input_path: path to the source video file
        output_path: where to write the PNG. Pass None to skip writing and
            only get the in-memory Storyboard.
        grid: '2x2', '3x3', '4x4', '5x5', or None for auto (<= 4s → 2x2,
            otherwise → 3x3).
        max_duration_seconds: reject videos longer than this. Default 300
            (5 min). Raise max_duration_seconds explicitly to override.
        captions_path: path to a Whisper captions JSON for burn-in or
            transcript correlation.
        transcribe: run faster-whisper on the video's audio to generate
            captions automatically.
        burn_captions: render a caption strip below each cell (one-layer mode).
        transcript_format: 'json' (default, Remotion-compatible), 'srt', or
            'txt'. Controls the extension and format of the transcript
            sidecar file.
        work_dir: directory for intermediate frames. A temp dir is created
            if not supplied.
        cleanup_work_dir: delete the work dir after rendering.

    Returns:
        Storyboard describing the result. board.png_path is populated if
        output_path was provided.
    """
    video = probe(input_path)
    preset = preset_for(
        video,
        grid=grid,
        fps=fps,
        max_boards=max_boards,
        max_duration_seconds=max_duration_seconds,
    )

    if transcript_format not in SUPPORTED_FORMATS:
        raise ValueError(
            f"Unknown transcript format '{transcript_format}'. "
            f"Supported: {', '.join(SUPPORTED_FORMATS)}"
        )

    # --- captions ---
    captions_data: List[dict] = []
    transcript_out_path: Optional[str] = None

    if transcribe and captions_path:
        raise ValueError("Use either --transcribe or --captions, not both")

    if transcribe:
        if output_path:
            transcript_out_path = str(
                Path(output_path).with_name(
                    Path(output_path).stem + f"-transcript.{transcript_format}"
                )
            )
        captions_data = transcribe_video(
            input_path,
            output_path=transcript_out_path,
            format=transcript_format,
        )
    elif captions_path:
        captions_data = load_captions(captions_path)
        if output_path and captions_data:
            dest = Path(output_path).with_name(
                Path(output_path).stem + f"-transcript.{transcript_format}"
            )
            write_captions(captions_data, str(dest), format=transcript_format)
            transcript_out_path = str(dest)

    # --- frame extraction ---
    managed_work_dir = work_dir is None
    if managed_work_dir:
        work_dir = tempfile.mkdtemp(prefix="vidgrid-")
    else:
        Path(work_dir).mkdir(parents=True, exist_ok=True)

    try:
        per_board_samples = sample_video(video, preset, work_dir)

        # --- assemble Storyboard ---
        boards: List[Board] = []
        for i, samples in enumerate(per_board_samples, start=1):
            cells: List[Cell] = []
            for sample in samples:
                phrase = None
                if captions_data:
                    phrase = phrase_for_timestamp(
                        captions_data, sample.timestamp_ms
                    )
                cells.append(Cell(sample=sample, caption=phrase))
            boards.append(
                Board(index=i, layout=preset.layout, cells=cells)
            )

        storyboard = Storyboard(
            source=video,
            preset=preset,
            boards=boards,
            transcript_path=transcript_out_path,
        )

        if output_path:
            write_boards(
                storyboard, output_path, burn_captions=burn_captions
            )
            write_sidecar(storyboard, output_path)

        return storyboard
    finally:
        if managed_work_dir and cleanup_work_dir and work_dir:
            shutil.rmtree(work_dir, ignore_errors=True)
