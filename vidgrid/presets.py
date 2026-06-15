"""Grid presets and duration-aware auto-configuration.

vidgrid's core model: each cell represents a sampled moment from the video.
The auto-picker maximises cell size (readability) by preferring smaller grids
with more boards. Only when the board count would exceed MAX_BOARDS does it
step up to a denser grid or reduce the sampling rate.

Supported grid sizes:
    - 2x2 (4 cells): largest cells, best readability
    - 3x3 (9 cells): good balance
    - 4x4 (16 cells): compact, acceptable readability
    - 5x5 (25 cells): dense, cells get small

Auto-pick priority (when the user doesn't pass --grid):
    1. Try 2x2 — if boards needed <= MAX_BOARDS, use it
    2. Try 3x3 — if boards needed <= MAX_BOARDS, use it
    3. Try 4x4 — if boards needed <= MAX_BOARDS, use it
    4. Use 4x4 and reduce sampling rate to fit MAX_BOARDS

Videos longer than MAX_DURATION_SECONDS (default 300s / 5 min) are rejected.
"""

from __future__ import annotations

import math

from vidgrid.models import GridLayout, Preset, VideoInfo

LAYOUT_2x2 = GridLayout(cols=2, rows=2)
LAYOUT_3x3 = GridLayout(cols=3, rows=3)
LAYOUT_4x4 = GridLayout(cols=4, rows=4)
LAYOUT_5x5 = GridLayout(cols=5, rows=5)

LAYOUTS: dict[str, GridLayout] = {
    "2x2": LAYOUT_2x2,
    "3x3": LAYOUT_3x3,
    "4x4": LAYOUT_4x4,
    "5x5": LAYOUT_5x5,
}

# Prefer smaller grids (bigger cells) first.
LAYOUT_PREFERENCE = [LAYOUT_2x2, LAYOUT_3x3, LAYOUT_4x4]

# Hard cap on video length. Longer → error.
MAX_DURATION_SECONDS = 300  # 5 minutes

# Maximum boards to produce. Modern vision LLMs handle 10+ images well.
DEFAULT_MAX_BOARDS = 10


class VideoTooLong(ValueError):
    """Raised when a video exceeds the max duration cap."""


def parse_grid_flag(value: str) -> GridLayout:
    """Parse '--grid 3x3' style flags into a GridLayout."""
    if value is None:
        raise ValueError("Grid value is required")
    v = value.strip().lower().replace("*", "x").replace("×", "x")
    if v not in LAYOUTS:
        raise ValueError(
            f"Unsupported grid '{value}'. Choose from: {', '.join(LAYOUTS)}"
        )
    return LAYOUTS[v]


def boards_needed(duration_ms: int, layout: GridLayout, interval_s: float = 1.0) -> int:
    """How many boards we need to cover the video at the given sampling interval."""
    duration_s = duration_ms / 1000.0
    total_cells = math.ceil(duration_s / interval_s)
    if total_cells == 0:
        return 0
    return max(1, math.ceil(total_cells / layout.cells))


def validate_duration(
    video: VideoInfo, max_duration_seconds: int = MAX_DURATION_SECONDS
) -> None:
    """Raise VideoTooLong if the video exceeds the cap."""
    duration_s = video.duration_ms / 1000.0
    if duration_s > max_duration_seconds:
        raise VideoTooLong(
            f"Video is {duration_s:.1f}s, exceeds max of {max_duration_seconds}s "
            f"({max_duration_seconds // 60}min). Chop the video into shorter "
            f"pieces and process them separately."
        )


def auto_pick(
    duration_ms: int, max_boards: int = DEFAULT_MAX_BOARDS
) -> tuple[GridLayout, float]:
    """Pick the best grid layout and sampling interval for a given duration.

    Strategy: prefer the smallest grid (biggest cells) whose board count
    stays within max_boards at 1fps. If no grid fits, use 4x4 and reduce
    the sampling rate to fit.

    Returns:
        (layout, sample_interval_s)
    """
    duration_s = duration_ms / 1000.0
    if duration_s <= 0:
        return LAYOUT_2x2, 1.0

    # Try each layout in preference order (smallest first = biggest cells)
    for layout in LAYOUT_PREFERENCE:
        boards = boards_needed(duration_ms, layout, interval_s=1.0)
        if boards <= max_boards:
            return layout, 1.0

    # No grid fits at 1fps — use 4x4 and reduce sampling rate
    layout = LAYOUT_4x4
    total_cells = max_boards * layout.cells
    interval = duration_s / total_cells
    return layout, interval


def preset_for(
    video: VideoInfo,
    *,
    grid: str | None = None,
    fps: float | None = None,
    max_boards: int = DEFAULT_MAX_BOARDS,
    max_duration_seconds: int = MAX_DURATION_SECONDS,
) -> Preset:
    """Resolve a preset for a given video.

    If grid is None, auto-pick based on duration to maximise cell readability.
    If fps is provided, it overrides the auto-calculated sampling interval.
    """
    validate_duration(video, max_duration_seconds=max_duration_seconds)

    if grid is not None:
        # User chose a specific grid — honour it
        layout = parse_grid_flag(grid)
        interval = 1.0 / fps if fps else 1.0
        boards = boards_needed(video.duration_ms, layout, interval_s=interval)
        return Preset(
            name=layout.label,
            layout=layout,
            max_boards=boards,
            sample_interval_s=interval,
        )

    if fps is not None:
        # User chose a specific fps but no grid — auto-pick grid
        interval = 1.0 / fps
        layout, _ = auto_pick(video.duration_ms, max_boards=max_boards)
        boards = boards_needed(video.duration_ms, layout, interval_s=interval)
        return Preset(
            name="auto",
            layout=layout,
            max_boards=boards,
            sample_interval_s=interval,
        )

    # Full auto: pick grid and interval based on duration
    layout, interval = auto_pick(video.duration_ms, max_boards=max_boards)
    boards = boards_needed(video.duration_ms, layout, interval_s=interval)
    return Preset(
        name="auto",
        layout=layout,
        max_boards=boards,
        sample_interval_s=interval,
    )
