"""Pure data shapes used across the vidgrid pipeline.

Dataclasses only. No logic, no I/O. Kept import-light so every other module
can depend on this without cycles.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass(frozen=True)
class VideoInfo:
    """Metadata about a source video, returned by probe.py."""

    path: str
    duration_ms: int
    width: int
    height: int
    fps: float

    @property
    def orientation(self) -> str:
        """'landscape', 'portrait', or 'square' based on dimensions."""
        if self.width > self.height:
            return "landscape"
        if self.height > self.width:
            return "portrait"
        return "square"

    @property
    def aspect_ratio(self) -> float:
        return self.width / self.height if self.height else 1.0


@dataclass(frozen=True)
class GridLayout:
    """A single board's row/col count and human-readable label."""

    cols: int
    rows: int

    @property
    def cells(self) -> int:
        return self.cols * self.rows

    @property
    def label(self) -> str:
        return f"{self.cols}x{self.rows}"


@dataclass(frozen=True)
class Preset:
    """Named configuration for how a video becomes one or more boards."""

    name: str
    layout: GridLayout
    max_boards: int = 1
    sample_interval_s: float = 1.0  # seconds between sampled frames

    @property
    def total_cells(self) -> int:
        return self.layout.cells * self.max_boards


@dataclass
class Sample:
    """One frame extracted from the video.

    Mutable because dedupe may mark a sample as replaced during processing.
    """

    index: int  # global index across all boards, 1-based
    timestamp_ms: int
    frame_path: str  # path to extracted JPEG on disk
    deduped: bool = False  # True if this sample replaced a near-duplicate


@dataclass(frozen=True)
class CaptionPhrase:
    """Phrase window extracted from a Whisper transcript for one frame."""

    text: str
    start_ms: int
    end_ms: int


@dataclass
class Cell:
    """A rendered cell ready for composition."""

    sample: Sample
    caption: Optional[CaptionPhrase] = None


@dataclass
class Board:
    """One PNG output with its cells."""

    index: int  # 1-based
    layout: GridLayout
    cells: List[Cell]
    png_path: Optional[str] = None  # set after output.py writes the file


@dataclass
class Storyboard:
    """The full result of rendering a video.

    This is also the public API return type from vidgrid.render().
    """

    source: VideoInfo
    preset: Preset
    boards: List[Board]
    transcript_path: Optional[str] = None  # sidecar transcript JSON if any
    sidecar_path: Optional[str] = None  # sidecar grid JSON

    @property
    def board_paths(self) -> List[str]:
        return [b.png_path for b in self.boards if b.png_path]

    @property
    def all_samples(self) -> List[Sample]:
        out: List[Sample] = []
        for board in self.boards:
            for cell in board.cells:
                out.append(cell.sample)
        return out
