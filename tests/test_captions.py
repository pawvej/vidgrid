"""Tests for caption loading and phrase windowing."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vidgrid.captions import (
    SUPPORTED_FORMATS,
    _ms_to_srt_time,
    _parse_srt,
    _parse_txt,
    _to_srt,
    _to_txt,
    captions_to_prompt_text,
    load_captions,
    phrase_for_timestamp,
    write_captions,
)
from vidgrid.models import CaptionPhrase


def _word(text: str, start_ms: int, end_ms: int) -> dict:
    return {
        "text": f" {text}",
        "startMs": start_ms,
        "endMs": end_ms,
        "timestampMs": start_ms,
        "confidence": 0.98,
    }


SAMPLE_CAPTIONS = [
    _word("we", 0, 300),
    _word("just", 300, 600),
    _word("hit", 600, 900),
    _word("three", 900, 1300),
    _word("hundred", 1300, 1700),
    _word("thousand", 1700, 2200),
    _word("in", 2200, 2400),
    _word("MRR", 2400, 2900),
    _word("solo", 2900, 3400),
    _word("no", 3400, 3700),
    _word("funding", 3700, 4400),
]


class TestPhraseForTimestamp:
    def test_returns_none_for_empty_captions(self):
        assert phrase_for_timestamp([], 1000) is None

    def test_returns_none_if_no_words_in_window(self):
        # timestamp far before any caption
        assert phrase_for_timestamp(SAMPLE_CAPTIONS, -10000) is None

    def test_extracts_window_around_timestamp(self):
        phrase = phrase_for_timestamp(SAMPLE_CAPTIONS, 1500)
        assert phrase is not None
        assert isinstance(phrase, CaptionPhrase)
        # Should include words around 1500ms
        assert "hundred" in phrase.text or "three" in phrase.text

    def test_max_words_limits_output(self):
        phrase = phrase_for_timestamp(
            SAMPLE_CAPTIONS, 2000, before_ms=10000, after_ms=10000, max_words=3
        )
        assert phrase is not None
        word_count = len(phrase.text.split())
        assert word_count <= 4  # allow for ellipsis

    def test_max_chars_truncates(self):
        phrase = phrase_for_timestamp(
            SAMPLE_CAPTIONS,
            2000,
            before_ms=10000,
            after_ms=10000,
            max_chars=20,
            max_words=100,
        )
        assert phrase is not None
        assert len(phrase.text) <= 21  # includes possible ellipsis char


class TestLoadCaptions:
    def test_missing_file_returns_empty(self, tmp_path: Path):
        assert load_captions(str(tmp_path / "missing.json")) == []

    def test_invalid_json_returns_empty(self, tmp_path: Path):
        path = tmp_path / "bad.json"
        path.write_text("not json {")
        assert load_captions(str(path)) == []

    def test_non_list_returns_empty(self, tmp_path: Path):
        path = tmp_path / "obj.json"
        path.write_text('{"not": "a list"}')
        assert load_captions(str(path)) == []

    def test_valid_list_loads(self, tmp_path: Path):
        path = tmp_path / "good.json"
        path.write_text(json.dumps(SAMPLE_CAPTIONS))
        loaded = load_captions(str(path))
        assert len(loaded) == len(SAMPLE_CAPTIONS)


class TestCaptionsToPromptText:
    def test_empty_returns_empty_string(self):
        assert captions_to_prompt_text([]) == ""

    def test_produces_timestamped_lines(self):
        result = captions_to_prompt_text(SAMPLE_CAPTIONS)
        assert "[0:00]" in result
        assert "we just hit" in result

    def test_breaks_on_sentence_end(self):
        captions = [
            _word("end.", 1000, 1500),
            _word("next", 2000, 2300),
        ]
        result = captions_to_prompt_text(captions)
        lines = result.split("\n")
        assert len(lines) >= 2


class TestSrtTimeFormat:
    def test_zero(self):
        assert _ms_to_srt_time(0) == "00:00:00,000"

    def test_one_second(self):
        assert _ms_to_srt_time(1000) == "00:00:01,000"

    def test_sub_second(self):
        assert _ms_to_srt_time(1234) == "00:00:01,234"

    def test_minutes(self):
        assert _ms_to_srt_time(65_432) == "00:01:05,432"

    def test_hours(self):
        assert _ms_to_srt_time(3_723_456) == "01:02:03,456"


class TestSrtRoundTrip:
    def test_roundtrip_preserves_timing_and_text(self):
        srt = _to_srt(SAMPLE_CAPTIONS)
        parsed = _parse_srt(srt)
        assert len(parsed) == len(SAMPLE_CAPTIONS)
        for orig, rt in zip(SAMPLE_CAPTIONS, parsed):
            assert rt["startMs"] == orig["startMs"]
            assert rt["endMs"] == orig["endMs"]
            assert rt["text"].strip() == orig["text"].strip()

    def test_srt_has_expected_shape(self):
        srt = _to_srt(SAMPLE_CAPTIONS)
        assert srt.startswith("1\n")
        assert " --> " in srt
        # Has sequentially numbered entries
        assert "\n2\n" in srt

    def test_parse_srt_with_dot_separator(self):
        # Some SRT exporters use . instead of ,
        srt = "1\n00:00:01.000 --> 00:00:02.000\nhello\n"
        parsed = _parse_srt(srt)
        assert len(parsed) == 1
        assert parsed[0]["startMs"] == 1000
        assert parsed[0]["endMs"] == 2000

    def test_parse_srt_without_index_line(self):
        srt = "00:00:01,000 --> 00:00:02,000\nhello\n"
        parsed = _parse_srt(srt)
        assert len(parsed) == 1
        assert parsed[0]["text"].strip() == "hello"


class TestTxtRoundTrip:
    def test_roundtrip_preserves_text_and_start(self):
        txt = _to_txt(SAMPLE_CAPTIONS)
        parsed = _parse_txt(txt)
        assert len(parsed) == len(SAMPLE_CAPTIONS)
        for orig, rt in zip(SAMPLE_CAPTIONS, parsed):
            assert rt["startMs"] == orig["startMs"]
            assert rt["text"].strip() == orig["text"].strip()

    def test_txt_is_one_line_per_word(self):
        txt = _to_txt(SAMPLE_CAPTIONS)
        non_empty = [ln for ln in txt.splitlines() if ln.strip()]
        assert len(non_empty) == len(SAMPLE_CAPTIONS)

    def test_txt_ends_with_newline(self):
        txt = _to_txt(SAMPLE_CAPTIONS)
        assert txt.endswith("\n")

    def test_parse_txt_ignores_blank_lines(self):
        txt = "0.00 hello\n\n0.50 world\n"
        parsed = _parse_txt(txt)
        assert len(parsed) == 2

    def test_parse_txt_handles_malformed_lines(self):
        txt = "not_a_number hello\n0.50 world\n"
        parsed = _parse_txt(txt)
        assert len(parsed) == 1
        assert parsed[0]["text"].strip() == "world"


class TestWriteCaptions:
    def test_write_json_default(self, tmp_path: Path):
        path = tmp_path / "out.json"
        write_captions(SAMPLE_CAPTIONS, str(path))
        loaded = json.loads(path.read_text())
        assert len(loaded) == len(SAMPLE_CAPTIONS)

    def test_write_srt(self, tmp_path: Path):
        path = tmp_path / "out.srt"
        write_captions(SAMPLE_CAPTIONS, str(path), format="srt")
        content = path.read_text()
        assert "-->" in content
        assert "1\n" in content

    def test_write_txt(self, tmp_path: Path):
        path = tmp_path / "out.txt"
        write_captions(SAMPLE_CAPTIONS, str(path), format="txt")
        content = path.read_text()
        lines = [ln for ln in content.splitlines() if ln.strip()]
        assert len(lines) == len(SAMPLE_CAPTIONS)

    def test_write_format_inferred_from_extension(self, tmp_path: Path):
        path = tmp_path / "out.srt"
        write_captions(SAMPLE_CAPTIONS, str(path))  # format=None
        assert "-->" in path.read_text()

    def test_unknown_format_raises(self, tmp_path: Path):
        with pytest.raises(ValueError):
            write_captions(SAMPLE_CAPTIONS, str(tmp_path / "x.vtt"), format="vtt")


class TestLoadCaptionsAutoDetect:
    def test_loads_json(self, tmp_path: Path):
        path = tmp_path / "x.json"
        path.write_text(json.dumps(SAMPLE_CAPTIONS))
        loaded = load_captions(str(path))
        assert len(loaded) == len(SAMPLE_CAPTIONS)

    def test_loads_srt(self, tmp_path: Path):
        path = tmp_path / "x.srt"
        path.write_text(_to_srt(SAMPLE_CAPTIONS))
        loaded = load_captions(str(path))
        assert len(loaded) == len(SAMPLE_CAPTIONS)

    def test_loads_txt(self, tmp_path: Path):
        path = tmp_path / "x.txt"
        path.write_text(_to_txt(SAMPLE_CAPTIONS))
        loaded = load_captions(str(path))
        assert len(loaded) == len(SAMPLE_CAPTIONS)

    def test_unknown_extension_falls_back_to_json(self, tmp_path: Path):
        # .vtt is unsupported but we should still try JSON
        path = tmp_path / "x.vtt"
        path.write_text(json.dumps(SAMPLE_CAPTIONS))
        loaded = load_captions(str(path))
        assert len(loaded) == len(SAMPLE_CAPTIONS)


class TestSupportedFormats:
    def test_exposes_all_three(self):
        assert set(SUPPORTED_FORMATS) == {"json", "srt", "txt"}
