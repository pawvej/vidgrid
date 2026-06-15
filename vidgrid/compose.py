"""Grid composition via PIL.

Takes a list of Cells and produces a single PNG per board with:
    - Source frames (contain, not crop)
    - Numbered badges in top-left (for LLM reference)
    - Timestamp pills in top-right (MM:SS)
    - Optional caption strip below each cell

No business logic here, only layout and drawing.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

from vidgrid.models import Board, Cell, GridLayout

# ---------- visual constants ----------

TARGET_LONG_EDGE = 1568  # matches Claude's image scaling threshold
BOARD_PADDING = 12
CELL_GAP = 10
FRAME_BG = (10, 12, 16)  # #0a0c10 for letterbox
BOARD_BG = (16, 18, 24)
CAPTION_STRIP_BG = (17, 19, 24)  # #111318
CAPTION_TEXT_COLOR = (245, 247, 250)  # #F5F7FA
BADGE_BG = (0, 0, 0, 192)  # rgba(0,0,0,0.75)
BADGE_TEXT_COLOR = (245, 247, 250)
TIMESTAMP_BG = (0, 0, 0, 166)  # rgba(0,0,0,0.65)
TIMESTAMP_TEXT_COLOR = (245, 247, 250)
CAPTION_STRIP_RATIO = 0.20


# ---------- font loading ----------

_font_cache: dict[int, ImageFont.FreeTypeFont] = {}


def _font(size: int) -> ImageFont.FreeTypeFont:
    """Load the bundled SemiBold font at a given pixel size."""
    if size in _font_cache:
        return _font_cache[size]
    # Use importlib.resources to find the bundled TTF
    try:
        font_ref = resources.files("vidgrid").joinpath(
            "assets/fonts/SourceSans3-Semibold.ttf"
        )
        with resources.as_file(font_ref) as font_path:
            font = ImageFont.truetype(str(font_path), size=size)
    except (FileNotFoundError, OSError):
        font = ImageFont.load_default()
    _font_cache[size] = font
    return font


# ---------- layout math ----------

def _compute_cell_dims(
    layout: GridLayout,
    source_width: int,
    source_height: int,
    *,
    burn_captions: bool,
) -> Tuple[int, int, int, int]:
    """Return (board_w, board_h, cell_w, cell_h) for a given layout.

    Cell aspect ratio matches the source. Caption strips extend the cell
    height when burned captions are enabled.
    """
    source_aspect = source_width / source_height if source_height else 16 / 9

    # Start by sizing cells so the board's long edge hits TARGET_LONG_EDGE
    if source_aspect >= 1:
        # Landscape or square source: board width is the long edge
        board_w = TARGET_LONG_EDGE
        avail_w = board_w - 2 * BOARD_PADDING - (layout.cols - 1) * CELL_GAP
        cell_w = avail_w // layout.cols
        frame_h = int(cell_w / source_aspect)
    else:
        # Portrait source: board height is the long edge
        board_h = TARGET_LONG_EDGE
        avail_h_for_cells = board_h - 2 * BOARD_PADDING - (layout.rows - 1) * CELL_GAP
        if burn_captions:
            cell_h_with_strip = avail_h_for_cells // layout.rows
            frame_h = int(cell_h_with_strip / (1 + CAPTION_STRIP_RATIO))
        else:
            frame_h = avail_h_for_cells // layout.rows
        cell_w = int(frame_h * source_aspect)

    strip_h = int(frame_h * CAPTION_STRIP_RATIO) if burn_captions else 0
    cell_h = frame_h + strip_h

    board_w = cell_w * layout.cols + (layout.cols - 1) * CELL_GAP + 2 * BOARD_PADDING
    board_h = cell_h * layout.rows + (layout.rows - 1) * CELL_GAP + 2 * BOARD_PADDING

    return board_w, board_h, cell_w, cell_h


def _fit_frame(frame_img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """Fit a frame into target dimensions while preserving aspect (contain).

    Returns an RGB image of exactly target_w x target_h with letterbox/pillarbox.
    """
    canvas = Image.new("RGB", (target_w, target_h), FRAME_BG)
    src_w, src_h = frame_img.size
    if src_w == 0 or src_h == 0:
        return canvas

    scale = min(target_w / src_w, target_h / src_h)
    new_w = max(1, int(src_w * scale))
    new_h = max(1, int(src_h * scale))
    resized = frame_img.resize((new_w, new_h), Image.LANCZOS)

    offset = ((target_w - new_w) // 2, (target_h - new_h) // 2)
    canvas.paste(resized, offset)
    return canvas


# ---------- drawing helpers ----------

def _format_timestamp(ms: int) -> str:
    total_s = ms // 1000
    m, s = divmod(total_s, 60)
    return f"{m}:{s:02d}"


def _draw_rounded_rect(
    draw: ImageDraw.ImageDraw,
    bounds: Tuple[int, int, int, int],
    radius: int,
    fill,
) -> None:
    draw.rounded_rectangle(bounds, radius=radius, fill=fill)


def _draw_pill(
    base: Image.Image,
    text: str,
    *,
    cell_w: int,
    frame_origin: Tuple[int, int],
    position: str,
    size_ratio: float,
    min_size: int,
    max_size: int,
    pad_x: int = 10,
    pad_y: int = 5,
    radius: int = 8,
    fill: tuple = BADGE_BG,
    text_color: tuple = BADGE_TEXT_COLOR,
) -> None:
    """Draw a pill-style badge in a corner of a cell's frame area.

    Used for both numbered cell badges and timestamp pills. Call with
    different size ratios to distinguish them visually.
    """
    font_size = max(min_size, min(max_size, int(cell_w * size_ratio)))
    font = _font(font_size)

    tmp = Image.new("RGBA", (10, 10))
    tmp_draw = ImageDraw.Draw(tmp)
    bbox = tmp_draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    badge_w = text_w + 2 * pad_x
    badge_h = text_h + 2 * pad_y + 2

    inset = max(8, cell_w // 60)
    if position == "top-left":
        bx = frame_origin[0] + inset
        by = frame_origin[1] + inset
    else:  # top-right
        bx = frame_origin[0] + cell_w - badge_w - inset
        by = frame_origin[1] + inset

    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    _draw_rounded_rect(
        draw, (bx, by, bx + badge_w, by + badge_h), radius=radius, fill=fill
    )
    draw.text(
        (bx + pad_x, by + pad_y - bbox[1]),
        text,
        font=font,
        fill=text_color,
    )
    base.alpha_composite(overlay)


def _draw_number_badge(
    base: Image.Image,
    number: int,
    *,
    cell_w: int,
    frame_origin: Tuple[int, int],
) -> None:
    """Big, prominent numbered badge in the top-left of a cell.

    Uses a stronger background and a noticeably larger font than the
    timestamp pill so the LLM can easily reference frames by number.
    """
    _draw_pill(
        base,
        str(number),
        cell_w=cell_w,
        frame_origin=frame_origin,
        position="top-left",
        size_ratio=0.07,
        min_size=16,
        max_size=32,
        pad_x=10,
        pad_y=5,
        radius=8,
        fill=(0, 0, 0, 220),  # stronger than timestamp
    )


def _draw_timestamp_pill(
    base: Image.Image,
    timestamp_ms: int,
    *,
    cell_w: int,
    frame_origin: Tuple[int, int],
) -> None:
    """Smaller timestamp pill in the top-right of a cell."""
    _draw_pill(
        base,
        _format_timestamp(timestamp_ms),
        cell_w=cell_w,
        frame_origin=frame_origin,
        position="top-right",
        size_ratio=0.055,
        min_size=14,
        max_size=28,
        pad_x=8,
        pad_y=4,
        radius=6,
        fill=TIMESTAMP_BG,
        text_color=TIMESTAMP_TEXT_COLOR,
    )


def _draw_caption_strip(
    base: Image.Image,
    text: str,
    *,
    strip_bounds: Tuple[int, int, int, int],
    cell_w: int,
) -> None:
    """Draw the dark caption strip beneath a frame."""
    x1, y1, x2, y2 = strip_bounds
    draw = ImageDraw.Draw(base)
    draw.rectangle((x1, y1, x2, y2), fill=CAPTION_STRIP_BG)

    font_size = max(11, min(22, int(cell_w * 0.055)))
    font = _font(font_size)

    pad = 8
    avail_w = cell_w - 2 * pad
    avail_h = (y2 - y1) - 2 * pad

    lines = _wrap_text(text, font, avail_w, max_lines=2)
    if not lines:
        return

    line_h = font_size + 2
    total_h = len(lines) * line_h
    y_offset = y1 + pad + max(0, (avail_h - total_h) // 2)

    for i, line in enumerate(lines):
        draw.text(
            (x1 + pad, y_offset + i * line_h),
            line,
            font=font,
            fill=CAPTION_TEXT_COLOR,
        )


def _wrap_text(
    text: str, font: ImageFont.FreeTypeFont, max_w: int, max_lines: int = 2
) -> List[str]:
    """Naive word-wrap that measures with the given font."""
    words = text.split()
    if not words:
        return []

    tmp = Image.new("RGB", (10, 10))
    draw = ImageDraw.Draw(tmp)

    def width_of(s: str) -> int:
        bbox = draw.textbbox((0, 0), s, font=font)
        return bbox[2] - bbox[0]

    lines: List[str] = []
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        if width_of(candidate) <= max_w:
            current = candidate
        else:
            if current:
                lines.append(current)
            if len(lines) >= max_lines:
                break
            current = word
            if width_of(current) > max_w:
                # Single word longer than line, truncate with ellipsis
                while current and width_of(current + "…") > max_w:
                    current = current[:-1]
                lines.append(current + "…")
                current = ""
                if len(lines) >= max_lines:
                    break

    if current and len(lines) < max_lines:
        lines.append(current)

    if len(lines) == max_lines and any(True for _ in words[len(" ".join(lines).split()):]):
        last = lines[-1]
        while last and width_of(last + "…") > max_w:
            last = last[:-1]
        lines[-1] = last.rstrip() + "…"

    return lines


# ---------- board composition ----------

def compose_board(
    board: Board,
    source_width: int,
    source_height: int,
    *,
    burn_captions: bool = False,
) -> Image.Image:
    """Render one Board into a single RGBA image.

    Does not write to disk. Caller handles saving.
    """
    layout = board.layout
    board_w, board_h, cell_w, cell_h = _compute_cell_dims(
        layout, source_width, source_height, burn_captions=burn_captions
    )

    canvas = Image.new("RGBA", (board_w, board_h), BOARD_BG + (255,))
    frame_h = cell_h - (int(cell_h * CAPTION_STRIP_RATIO / (1 + CAPTION_STRIP_RATIO)) if burn_captions else 0)
    strip_h = cell_h - frame_h

    # Walk every position in the grid layout, not just cells we have.
    # This lets the last board in a multi-board run show blank placeholders
    # for cells that would've existed if the video were longer.
    total_positions = layout.cols * layout.rows
    for idx in range(total_positions):
        col = idx % layout.cols
        row = idx // layout.cols

        cell_x = BOARD_PADDING + col * (cell_w + CELL_GAP)
        cell_y = BOARD_PADDING + row * (cell_h + CELL_GAP)

        if idx < len(board.cells):
            cell = board.cells[idx]

            # 1) Frame image
            try:
                with Image.open(cell.sample.frame_path) as frame_img:
                    frame_img = frame_img.convert("RGB")
                    fitted = _fit_frame(frame_img, cell_w, frame_h)
            except (FileNotFoundError, OSError):
                fitted = Image.new("RGB", (cell_w, frame_h), FRAME_BG)

            canvas.paste(fitted, (cell_x, cell_y))

            # 2) Numbered badge (top-left, prominent)
            _draw_number_badge(
                canvas,
                cell.sample.index,
                cell_w=cell_w,
                frame_origin=(cell_x, cell_y),
            )

            # 3) Timestamp pill (top-right, smaller)
            _draw_timestamp_pill(
                canvas,
                cell.sample.timestamp_ms,
                cell_w=cell_w,
                frame_origin=(cell_x, cell_y),
            )

            # 4) Optional caption strip
            if burn_captions and cell.caption and strip_h > 0:
                strip_bounds = (
                    cell_x,
                    cell_y + frame_h,
                    cell_x + cell_w,
                    cell_y + cell_h,
                )
                _draw_caption_strip(
                    canvas,
                    cell.caption.text,
                    strip_bounds=strip_bounds,
                    cell_w=cell_w,
                )
        else:
            # Blank cell — draw a dark placeholder so the grid structure is
            # still visible to the viewer and the LLM knows the board ended.
            placeholder = Image.new("RGB", (cell_w, frame_h), FRAME_BG)
            canvas.paste(placeholder, (cell_x, cell_y))

    return canvas
