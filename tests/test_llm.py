"""Tests for LLM provider detection and prompt building.

Real API calls are not made in CI. The Anthropic/OpenAI/Gemini SDKs are
mocked at the import level so the tests run anywhere.
"""

from __future__ import annotations

import pytest

from vidgrid.llm import (
    LLMError,
    _build_prompt,
    detect_provider,
)


class TestDetectProvider:
    def test_claude_models(self):
        assert detect_provider("claude-opus-4-7") == "anthropic"
        assert detect_provider("claude-sonnet-4-6") == "anthropic"
        assert detect_provider("claude-haiku-4-5") == "anthropic"

    def test_openai_models(self):
        assert detect_provider("gpt-5") == "openai"
        assert detect_provider("gpt-4o") == "openai"
        assert detect_provider("o1-mini") == "openai"
        assert detect_provider("o3") == "openai"

    def test_gemini_models(self):
        assert detect_provider("gemini-2.5-flash") == "google"
        assert detect_provider("gemini-2.5-pro") == "google"

    def test_case_insensitive(self):
        assert detect_provider("CLAUDE-OPUS-4-6") == "anthropic"

    def test_unknown_model_raises(self):
        with pytest.raises(LLMError):
            detect_provider("llama-3")


class TestBuildPrompt:
    def test_no_transcript(self):
        result = _build_prompt("describe this", None)
        assert result == "describe this"

    def test_with_transcript(self):
        result = _build_prompt("summarize", "hello world")
        assert "summarize" in result
        assert "hello world" in result
        assert "Transcript" in result
