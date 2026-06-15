"""Tests for preset resolution and duration-aware auto-configuration."""

from __future__ import annotations

import pytest

from vidgrid.models import VideoInfo
from vidgrid.presets import (
    DEFAULT_MAX_BOARDS,
    LAYOUT_2x2,
    LAYOUT_3x3,
    LAYOUT_4x4,
    LAYOUT_5x5,
    LAYOUTS,
    MAX_DURATION_SECONDS,
    VideoTooLong,
    auto_pick,
    boards_needed,
    parse_grid_flag,
    preset_for,
    validate_duration,
)


def _video(duration_ms: int, w: int = 1920, h: int = 1080) -> VideoInfo:
    return VideoInfo(
        path="/fake.mp4", duration_ms=duration_ms, width=w, height=h, fps=30
    )


class TestParseGridFlag:
    def test_each_supported_layout(self):
        assert parse_grid_flag("2x2") == LAYOUT_2x2
        assert parse_grid_flag("3x3") == LAYOUT_3x3
        assert parse_grid_flag("4x4") == LAYOUT_4x4
        assert parse_grid_flag("5x5") == LAYOUT_5x5

    def test_case_insensitive(self):
        assert parse_grid_flag("3X3") == LAYOUT_3x3

    def test_times_symbol(self):
        assert parse_grid_flag("3×3") == LAYOUT_3x3

    def test_rejects_unsupported(self):
        for bad in ["1x1", "6x6", "banana", "3x4", "4x3"]:
            with pytest.raises(ValueError):
                parse_grid_flag(bad)


class TestAutoPick:
    """Auto-pick prefers the smallest grid (biggest cells) that fits
    within the max_boards limit at 1fps."""

    def test_short_clip_gets_2x2(self):
        layout, interval = auto_pick(3000)
        assert layout == LAYOUT_2x2
        assert interval == 1.0

    def test_8s_gets_2x2_with_2_boards(self):
        layout, interval = auto_pick(8000)
        assert layout == LAYOUT_2x2
        assert interval == 1.0
        # 8 cells / 4 per board = 2 boards

    def test_30s_gets_2x2_with_8_boards(self):
        layout, interval = auto_pick(30000)
        assert layout == LAYOUT_2x2
        assert interval == 1.0
        # 30 / 4 = 8 boards, within default max of 10

    def test_40s_at_2x2_would_be_10_boards(self):
        layout, interval = auto_pick(40000)
        assert layout == LAYOUT_2x2
        assert interval == 1.0
        # 40 / 4 = 10 boards, exactly at limit

    def test_41s_bumps_to_3x3(self):
        layout, interval = auto_pick(41000)
        assert layout == LAYOUT_3x3
        assert interval == 1.0
        # 41 / 4 = 11 boards (too many), 41 / 9 = 5 boards

    def test_90s_stays_3x3(self):
        layout, interval = auto_pick(90000)
        assert layout == LAYOUT_3x3
        assert interval == 1.0
        # 90 / 9 = 10 boards, at limit

    def test_91s_bumps_to_4x4(self):
        layout, interval = auto_pick(91000)
        assert layout == LAYOUT_4x4
        assert interval == 1.0
        # 91 / 9 = 11 (too many), 91 / 16 = 6 boards

    def test_160s_stays_4x4(self):
        layout, interval = auto_pick(160000)
        assert layout == LAYOUT_4x4
        assert interval == 1.0
        # 160 / 16 = 10 boards, at limit

    def test_161s_reduces_sampling_rate(self):
        layout, interval = auto_pick(161000)
        assert layout == LAYOUT_4x4
        assert interval > 1.0
        # 161 / 16 = 11 boards at 1fps, so interval increases

    def test_300s_reduces_sampling_rate(self):
        layout, interval = auto_pick(300000)
        assert layout == LAYOUT_4x4
        assert interval > 1.0
        # Should target ~10 boards: 300 / (10 * 16) = 1.875s interval

    def test_custom_max_boards(self):
        # With max_boards=5, a 30s video should bump to 3x3
        layout, interval = auto_pick(30000, max_boards=5)
        # 30 / 4 = 8 boards (too many for 5), 30 / 9 = 4 boards
        assert layout == LAYOUT_3x3
        assert interval == 1.0

    def test_zero_duration(self):
        layout, interval = auto_pick(0)
        assert layout == LAYOUT_2x2
        assert interval == 1.0


class TestBoardsNeeded:
    def test_3s_at_2x2(self):
        assert boards_needed(3000, LAYOUT_2x2) == 1

    def test_9s_at_3x3(self):
        assert boards_needed(9000, LAYOUT_3x3) == 1

    def test_10s_at_3x3(self):
        assert boards_needed(10000, LAYOUT_3x3) == 2

    def test_186s_at_3x3_is_21_boards(self):
        assert boards_needed(186000, LAYOUT_3x3) == 21

    def test_186s_at_4x4_is_12_boards(self):
        assert boards_needed(186000, LAYOUT_4x4) == 12

    def test_custom_interval(self):
        # 60s at 2s interval = 30 cells, at 3x3 = 4 boards
        assert boards_needed(60000, LAYOUT_3x3, interval_s=2.0) == 4

    def test_custom_interval_reduces_boards(self):
        # 186s at 1.875s interval, 4x4 = 100 cells / 16 = 7 boards
        assert boards_needed(186000, LAYOUT_4x4, interval_s=1.875) == 7


class TestValidateDuration:
    def test_under_cap_ok(self):
        validate_duration(_video(180000))

    def test_at_cap_ok(self):
        validate_duration(_video(MAX_DURATION_SECONDS * 1000))

    def test_over_cap_raises(self):
        with pytest.raises(VideoTooLong):
            validate_duration(_video((MAX_DURATION_SECONDS + 1) * 1000))

    def test_custom_cap(self):
        validate_duration(_video(10000), max_duration_seconds=60)
        with pytest.raises(VideoTooLong):
            validate_duration(_video(70000), max_duration_seconds=60)


class TestPresetFor:
    def test_auto_short_video_gets_2x2(self):
        p = preset_for(_video(3000))
        assert p.layout == LAYOUT_2x2
        assert p.max_boards == 1
        assert p.sample_interval_s == 1.0

    def test_auto_8s_video_gets_2x2(self):
        p = preset_for(_video(8000))
        assert p.layout == LAYOUT_2x2
        assert p.max_boards == 2
        assert p.sample_interval_s == 1.0

    def test_auto_30s_video_gets_2x2(self):
        p = preset_for(_video(30000))
        assert p.layout == LAYOUT_2x2
        assert p.max_boards == 8
        assert p.sample_interval_s == 1.0

    def test_auto_60s_video_gets_3x3(self):
        p = preset_for(_video(60000))
        assert p.layout == LAYOUT_3x3
        assert p.sample_interval_s == 1.0

    def test_auto_186s_video_gets_4x4_reduced_rate(self):
        p = preset_for(_video(186000))
        assert p.layout == LAYOUT_4x4
        assert p.sample_interval_s > 1.0

    def test_explicit_grid_honoured(self):
        p = preset_for(_video(30000), grid="4x4")
        assert p.layout == LAYOUT_4x4
        assert p.sample_interval_s == 1.0

    def test_explicit_fps(self):
        p = preset_for(_video(60000), fps=0.5)
        # 0.5 fps = 2s interval
        assert p.sample_interval_s == 2.0

    def test_over_cap_rejected(self):
        with pytest.raises(VideoTooLong):
            preset_for(_video(400000))

    def test_rejects_bad_grid_name(self):
        with pytest.raises(ValueError):
            preset_for(_video(30000), grid="6x6")


class TestLayoutsMap:
    def test_all_supported_layouts_exposed(self):
        assert set(LAYOUTS.keys()) == {"2x2", "3x3", "4x4", "5x5"}

    def test_total_cells_per_layout(self):
        assert LAYOUTS["2x2"].cells == 4
        assert LAYOUTS["3x3"].cells == 9
        assert LAYOUTS["4x4"].cells == 16
        assert LAYOUTS["5x5"].cells == 25
