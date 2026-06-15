"""Frame sampling with configurable interval.

Each cell is sampled at the midpoint of its interval slot. For 1fps (the
default for short videos), cell N is at (N - 0.5) seconds. For slower
sampling rates, the interval widens proportionally.

The offset of 0.5 × interval keeps us away from slot boundaries (often
fade-ins or cuts) while staying representative of each slot.
"""

from __future__ import annotations

import math
import shutil
import subprocess
from pathlib import Path
from typing import List

from vidgrid.models import Preset, Sample, VideoInfo


class SampleError(RuntimeError):
    """Raised when frame extraction fails."""


# Sample at the midpoint of each slot to avoid fade-ins at slot start
# and frame-boundary edge cases at slot end.
SLOT_MID = 0.5


def plan_timestamps(preset: Preset, duration_ms: int) -> List[List[int]]:
    """Produce per-board lists of timestamps in ms.

    Each cell is sampled at the midpoint of its interval slot. For a 1s
    interval the timestamps are 0.5s, 1.5s, 2.5s, etc. For a 2s interval
    they are 1.0s, 3.0s, 5.0s, etc.

    Cells whose timestamp would exceed the video duration are omitted.
    """
    interval = preset.sample_interval_s
    cells_per_board = preset.layout.cells
    duration_s = duration_ms / 1000.0
    max_cells = preset.max_boards * cells_per_board

    all_ts: List[int] = []
    for i in range(max_cells):
        ts_s = (i + SLOT_MID) * interval
        ts_ms = int(round(ts_s * 1000))
        if ts_ms >= duration_ms:
            break
        all_ts.append(ts_ms)

    # Chunk into boards
    per_board: List[List[int]] = []
    for start in range(0, len(all_ts), cells_per_board):
        per_board.append(all_ts[start : start + cells_per_board])

    # Pad with empty lists if needed
    while len(per_board) < preset.max_boards:
        per_board.append([])

    return per_board[: preset.max_boards]


# ---------- ffmpeg frame extraction ----------

def extract_frame(
    video_path: str, timestamp_ms: int, output_path: str
) -> None:
    """Extract a single frame at the given timestamp using ffmpeg."""
    if shutil.which("ffmpeg") is None:
        raise SampleError("ffmpeg not found on PATH. Install ffmpeg.")

    seconds = timestamp_ms / 1000.0
    cmd = [
        "ffmpeg",
        "-y",
        "-ss", f"{seconds:.3f}",
        "-i", video_path,
        "-frames:v", "1",
        "-q:v", "3",
        "-loglevel", "error",
        output_path,
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=30)
    except subprocess.CalledProcessError as e:
        raise SampleError(
            f"ffmpeg failed at {timestamp_ms}ms: "
            f"{e.stderr.decode(errors='ignore').strip()}"
        ) from e
    except subprocess.TimeoutExpired as e:
        raise SampleError(f"ffmpeg timed out at {timestamp_ms}ms") from e

    if not Path(output_path).exists():
        raise SampleError(
            f"ffmpeg reported success but no frame was written at {timestamp_ms}ms"
        )


def sample_video(
    video: VideoInfo, preset: Preset, work_dir: str
) -> List[List[Sample]]:
    """Extract all frames and return per-board Sample lists.

    Boards may have fewer cells than layout.cells if the video ends mid-board.
    The caller (compose.py) handles blank cells for any missing positions.
    """
    Path(work_dir).mkdir(parents=True, exist_ok=True)
    per_board_ts = plan_timestamps(preset, video.duration_ms)

    per_board: List[List[Sample]] = []
    global_index = 1

    for board_idx, ts_list in enumerate(per_board_ts):
        samples: List[Sample] = []
        for cell_idx, ts_ms in enumerate(ts_list):
            frame_path = str(
                Path(work_dir) / f"board{board_idx + 1}_cell{cell_idx + 1}_{ts_ms}.jpg"
            )
            extract_frame(video.path, ts_ms, frame_path)
            samples.append(
                Sample(
                    index=global_index,
                    timestamp_ms=ts_ms,
                    frame_path=frame_path,
                    deduped=False,
                )
            )
            global_index += 1
        per_board.append(samples)

    return per_board
