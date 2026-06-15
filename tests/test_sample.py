"""Tests for the sampling logic with configurable intervals.

Only pure logic — no real ffmpeg extraction.
"""

from __future__ import annotations

import pytest

from vidgrid.models import Preset, VideoInfo
from vidgrid.presets import LAYOUT_2x2, LAYOUT_3x3, LAYOUT_4x4, LAYOUT_5x5
from vidgrid.sample import SLOT_MID, plan_timestamps


def _preset(layout, max_boards, interval=1.0):
    return Preset(
        name=layout.label,
        layout=layout,
        max_boards=max_boards,
        sample_interval_s=interval,
    )


class TestPlanTimestamps:
    def test_9s_3x3_produces_one_full_board(self):
        plan = plan_timestamps(_preset(LAYOUT_3x3, 1), 9000)
        assert len(plan) == 1
        assert len(plan[0]) == 9

    def test_timestamps_are_half_interval_offset(self):
        plan = plan_timestamps(_preset(LAYOUT_3x3, 1), 9000)
        assert plan[0][0] == 500  # 0.5s
        assert plan[0][1] == 1500  # 1.5s
        assert plan[0][8] == 8500  # 8.5s

    def test_strict_one_second_spacing_at_1fps(self):
        plan = plan_timestamps(_preset(LAYOUT_3x3, 1), 9000)
        ts_list = plan[0]
        for i in range(1, len(ts_list)):
            assert ts_list[i] - ts_list[i - 1] == 1000

    def test_10s_produces_two_boards(self):
        plan = plan_timestamps(_preset(LAYOUT_3x3, 2), 10000)
        assert len(plan) == 2
        assert len(plan[0]) == 9
        assert len(plan[1]) == 1

    def test_partial_first_board_for_short_clip(self):
        plan = plan_timestamps(_preset(LAYOUT_2x2, 1), 3000)
        assert len(plan) == 1
        assert len(plan[0]) == 3
        assert plan[0] == [500, 1500, 2500]

    def test_8s_at_2x2_yields_2_boards(self):
        """The Homi PropertyShowcase case: 8s video with 2x2 auto-pick."""
        plan = plan_timestamps(_preset(LAYOUT_2x2, 2), 8000)
        assert len(plan) == 2
        assert len(plan[0]) == 4
        assert len(plan[1]) == 4
        assert sum(len(b) for b in plan) == 8

    def test_custom_interval_2s(self):
        """60s video at 2s interval = 30 cells."""
        plan = plan_timestamps(_preset(LAYOUT_3x3, 4, interval=2.0), 60000)
        # 30 cells / 9 per board = 4 boards (3 full + 1 with 3)
        assert sum(len(b) for b in plan) == 30
        # First timestamp at 1.0s (0.5 * 2.0)
        assert plan[0][0] == 1000
        # Second at 3.0s (1.5 * 2.0)
        assert plan[0][1] == 3000

    def test_custom_interval_spacing(self):
        """Timestamps should be evenly spaced by interval."""
        plan = plan_timestamps(_preset(LAYOUT_2x2, 3, interval=2.5), 30000)
        flat = [ts for board in plan for ts in board]
        for i in range(1, len(flat)):
            assert flat[i] - flat[i - 1] == 2500

    def test_timestamps_never_exceed_duration(self):
        plan = plan_timestamps(_preset(LAYOUT_3x3, 1), 9000)
        for board in plan:
            for ts in board:
                assert ts < 9000

    def test_global_ordering_across_boards(self):
        plan = plan_timestamps(_preset(LAYOUT_3x3, 3), 20000)
        flat = [ts for board in plan for ts in board]
        assert flat == sorted(flat)

    def test_sub_second_video_returns_empty(self):
        plan = plan_timestamps(_preset(LAYOUT_2x2, 1), 400)
        total = sum(len(b) for b in plan)
        assert total == 0


class TestSlotMid:
    def test_offset_is_half(self):
        assert SLOT_MID == 0.5
