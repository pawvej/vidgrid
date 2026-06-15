"""Tests for PIL composition helpers including partial-grid rendering."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from vidgrid.compose import (
    TARGET_LONG_EDGE,
    _compute_cell_dims,
    _fit_frame,
    _format_timestamp,
    compose_board,
)
from vidgrid.models import Board, Cell, CaptionPhrase, GridLayout, Sample


@pytest.fixture
def tiny_jpeg(tmp_path: Path) -> str:
    """A 100x100 solid-color image on disk."""
    path = tmp_path / "fixture.jpg"
    Image.new("RGB", (100, 100), (128, 64, 32)).save(path, "JPEG")
    return str(path)


def _make_board(
    tiny_jpeg: str, cols: int, rows: int, *, cells: int | None = None, with_caption: bool = False
) -> Board:
    layout = GridLayout(cols=cols, rows=rows)
    count = cells if cells is not None else cols * rows
    cell_list = []
    for i in range(count):
        sample = Sample(
            index=i + 1,
            timestamp_ms=(i + 1) * 1000,
            frame_path=tiny_jpeg,
        )
        caption = (
            CaptionPhrase(text=f"caption for cell {i+1}", start_ms=0, end_ms=1000)
            if with_caption
            else None
        )
        cell_list.append(Cell(sample=sample, caption=caption))
    return Board(index=1, layout=layout, cells=cell_list)


class TestFormatTimestamp:
    def test_under_minute(self):
        assert _format_timestamp(5000) == "0:05"

    def test_over_minute(self):
        assert _format_timestamp(65000) == "1:05"

    def test_zero(self):
        assert _format_timestamp(0) == "0:00"


class TestComputeCellDims:
    def test_landscape_3x3(self):
        board_w, board_h, cell_w, cell_h = _compute_cell_dims(
            GridLayout(3, 3), 1920, 1080, burn_captions=False
        )
        assert abs(board_w - TARGET_LONG_EDGE) <= 10
        assert cell_w > cell_h  # landscape cell aspect

    def test_portrait_3x3(self):
        board_w, board_h, cell_w, cell_h = _compute_cell_dims(
            GridLayout(3, 3), 1080, 1920, burn_captions=False
        )
        assert abs(board_h - TARGET_LONG_EDGE) <= 10
        assert cell_h > cell_w  # portrait cell aspect

    def test_5x5_landscape_fits_long_edge(self):
        board_w, board_h, cell_w, cell_h = _compute_cell_dims(
            GridLayout(5, 5), 1920, 1080, burn_captions=False
        )
        assert abs(board_w - TARGET_LONG_EDGE) <= 10

    def test_caption_strip_adds_cell_height(self):
        _, _, _, cell_h_plain = _compute_cell_dims(
            GridLayout(3, 3), 1920, 1080, burn_captions=False
        )
        _, _, _, cell_h_captions = _compute_cell_dims(
            GridLayout(3, 3), 1920, 1080, burn_captions=True
        )
        assert cell_h_captions > cell_h_plain


class TestFitFrame:
    def test_exact_size_returns_same_dims(self):
        src = Image.new("RGB", (200, 100), "red")
        fitted = _fit_frame(src, 200, 100)
        assert fitted.size == (200, 100)

    def test_letterboxes_wide_source(self):
        src = Image.new("RGB", (400, 100), "red")
        fitted = _fit_frame(src, 200, 200)
        assert fitted.size == (200, 200)

    def test_pillarboxes_tall_source(self):
        src = Image.new("RGB", (100, 400), "blue")
        fitted = _fit_frame(src, 200, 200)
        assert fitted.size == (200, 200)


class TestComposeBoardEachGrid:
    def test_2x2_landscape(self, tiny_jpeg):
        board = _make_board(tiny_jpeg, 2, 2)
        img = compose_board(board, 1920, 1080, burn_captions=False)
        assert abs(img.size[0] - TARGET_LONG_EDGE) <= 10
        assert img.mode == "RGBA"

    def test_2x2_portrait(self, tiny_jpeg):
        board = _make_board(tiny_jpeg, 2, 2)
        img = compose_board(board, 1080, 1920, burn_captions=False)
        assert abs(img.size[1] - TARGET_LONG_EDGE) <= 10

    def test_3x3_landscape(self, tiny_jpeg):
        board = _make_board(tiny_jpeg, 3, 3)
        img = compose_board(board, 1920, 1080)
        assert abs(img.size[0] - TARGET_LONG_EDGE) <= 10

    def test_3x3_portrait(self, tiny_jpeg):
        board = _make_board(tiny_jpeg, 3, 3)
        img = compose_board(board, 1080, 1920)
        assert abs(img.size[1] - TARGET_LONG_EDGE) <= 10

    def test_4x4_landscape(self, tiny_jpeg):
        board = _make_board(tiny_jpeg, 4, 4)
        img = compose_board(board, 1920, 1080)
        assert abs(img.size[0] - TARGET_LONG_EDGE) <= 10

    def test_4x4_portrait(self, tiny_jpeg):
        board = _make_board(tiny_jpeg, 4, 4)
        img = compose_board(board, 1080, 1920)
        assert abs(img.size[1] - TARGET_LONG_EDGE) <= 10

    def test_5x5_landscape(self, tiny_jpeg):
        board = _make_board(tiny_jpeg, 5, 5)
        img = compose_board(board, 1920, 1080)
        assert abs(img.size[0] - TARGET_LONG_EDGE) <= 10

    def test_5x5_portrait(self, tiny_jpeg):
        board = _make_board(tiny_jpeg, 5, 5)
        img = compose_board(board, 1080, 1920)
        assert abs(img.size[1] - TARGET_LONG_EDGE) <= 10


class TestPartialGrid:
    def test_partial_last_board_renders(self, tiny_jpeg):
        # 3x3 grid with only 3 cells — represents the end of a 3s clip
        board = _make_board(tiny_jpeg, 3, 3, cells=3)
        img = compose_board(board, 1920, 1080)
        assert abs(img.size[0] - TARGET_LONG_EDGE) <= 10
        # Should render without error; the 6 missing cells become dark placeholders

    def test_single_cell_partial(self, tiny_jpeg):
        # Edge case: only 1 cell in a 3x3 (happens when 10s video ends on board 2)
        board = _make_board(tiny_jpeg, 3, 3, cells=1)
        img = compose_board(board, 1920, 1080)
        assert img is not None


class TestComposeBoardWithCaptions:
    def test_burn_captions_makes_board_taller(self, tiny_jpeg):
        plain = compose_board(
            _make_board(tiny_jpeg, 3, 3), 1920, 1080, burn_captions=False
        )
        captioned = compose_board(
            _make_board(tiny_jpeg, 3, 3, with_caption=True),
            1920,
            1080,
            burn_captions=True,
        )
        assert captioned.size[1] > plain.size[1]

    def test_missing_frame_renders_placeholder(self, tmp_path):
        layout = GridLayout(2, 2)
        cells = [
            Cell(
                sample=Sample(
                    index=i + 1,
                    timestamp_ms=(i + 1) * 1000,
                    frame_path=str(tmp_path / "nonexistent.jpg"),
                ),
            )
            for i in range(4)
        ]
        board = Board(index=1, layout=layout, cells=cells)
        img = compose_board(board, 1920, 1080)
        assert img is not None
