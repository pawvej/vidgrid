"""PNG + sidecar JSON writing.

Takes a fully-composed Storyboard and writes:
    - grid.png (single-board) or grid-1.png, grid-2.png, ... (multi-board)
    - grid.json sidecar describing the layout, samples, and timestamps
    - grid-transcript.json if a transcript was produced
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

from PIL import Image

from vidgrid import __version__
from vidgrid.compose import compose_board
from vidgrid.models import Board, Storyboard


def write_boards(
    storyboard: Storyboard,
    output_path: str,
    *,
    burn_captions: bool = False,
) -> List[str]:
    """Render and save all boards in a storyboard.

    For single-board output, writes directly to output_path.
    For multi-board output, writes grid-1.png, grid-2.png, ... next to it.

    Returns the list of PNG paths written.
    """
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    source_w = storyboard.source.width
    source_h = storyboard.source.height

    written: List[str] = []

    if len(storyboard.boards) == 1:
        board = storyboard.boards[0]
        img = compose_board(board, source_w, source_h, burn_captions=burn_captions)
        img.convert("RGB").save(out_path, "PNG", optimize=True)
        board.png_path = str(out_path)
        written.append(str(out_path))
    else:
        stem = out_path.stem
        suffix = out_path.suffix or ".png"
        parent = out_path.parent
        for board in storyboard.boards:
            board_path = parent / f"{stem}-{board.index}{suffix}"
            img = compose_board(
                board, source_w, source_h, burn_captions=burn_captions
            )
            img.convert("RGB").save(board_path, "PNG", optimize=True)
            board.png_path = str(board_path)
            written.append(str(board_path))

    return written


def write_sidecar(
    storyboard: Storyboard,
    output_path: str,
) -> str:
    """Write the sidecar JSON describing the storyboard.

    Placed next to the PNG with the same stem and .json extension.
    """
    out_path = Path(output_path)
    sidecar_path = out_path.with_suffix(".json")

    data = {
        "version": __version__,
        "source": storyboard.source.path,
        "duration_ms": storyboard.source.duration_ms,
        "width": storyboard.source.width,
        "height": storyboard.source.height,
        "preset": storyboard.preset.name,
        "layout": [storyboard.preset.layout.cols, storyboard.preset.layout.rows],
        "boards": [_board_to_dict(b) for b in storyboard.boards],
    }
    if storyboard.transcript_path:
        data["transcript_path"] = storyboard.transcript_path

    sidecar_path.write_text(json.dumps(data, indent=2))
    storyboard.sidecar_path = str(sidecar_path)
    return str(sidecar_path)


def _board_to_dict(board: Board) -> dict:
    return {
        "index": board.index,
        "path": board.png_path,
        "layout": [board.layout.cols, board.layout.rows],
        "cells": [
            {
                "index": cell.sample.index,
                "timestamp_ms": cell.sample.timestamp_ms,
                "deduped": cell.sample.deduped,
                "caption": cell.caption.text if cell.caption else None,
            }
            for cell in board.cells
        ],
    }
