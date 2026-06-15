"""Thin LLM wrappers for Claude, GPT, and Gemini.

All three SDKs are optional. Each call_* function imports its SDK lazily so
that missing packages don't break the core vidgrid renderer.

API keys come from environment variables:
    ANTHROPIC_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY

Each wrapper takes image paths + prompt + optional transcript and returns
the model's text response. No streaming, no retries, no tool use in v1.
"""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import List, Optional

DEFAULT_CLAUDE_MODEL = "claude-opus-4-7"
DEFAULT_OPENAI_MODEL = "gpt-5"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"

MAX_OUTPUT_TOKENS = 2048


class LLMError(RuntimeError):
    """Raised when an LLM call fails or a required SDK is missing."""


def detect_provider(model: str) -> str:
    """Map a model name to its provider: anthropic / openai / google."""
    m = model.lower()
    if m.startswith("claude"):
        return "anthropic"
    if m.startswith("gpt") or m.startswith("o1") or m.startswith("o3") or m.startswith("o4"):
        return "openai"
    if m.startswith("gemini"):
        return "google"
    raise LLMError(
        f"Cannot detect provider from model '{model}'. "
        "Use a name starting with claude-, gpt-, or gemini-."
    )


def call(
    image_paths: List[str],
    prompt: str,
    *,
    transcript: Optional[str] = None,
    model: str = DEFAULT_CLAUDE_MODEL,
) -> str:
    """Dispatch an LLM call based on the model name."""
    provider = detect_provider(model)
    if provider == "anthropic":
        return call_claude(image_paths, prompt, transcript=transcript, model=model)
    if provider == "openai":
        return call_openai(image_paths, prompt, transcript=transcript, model=model)
    if provider == "google":
        return call_gemini(image_paths, prompt, transcript=transcript, model=model)
    raise LLMError(f"Unsupported provider: {provider}")


# ---------- Anthropic ----------

def call_claude(
    image_paths: List[str],
    prompt: str,
    *,
    transcript: Optional[str] = None,
    model: str = DEFAULT_CLAUDE_MODEL,
) -> str:
    try:
        from anthropic import Anthropic
    except ImportError as e:
        raise LLMError(
            "anthropic SDK not installed. Run: pip install vidgrid[anthropic]"
        ) from e

    client = Anthropic()

    content: list[dict] = []
    for path in image_paths:
        media_type, b64_data = _encode_image(path)
        content.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": b64_data,
                },
            }
        )

    full_prompt = _build_prompt(prompt, transcript)
    content.append({"type": "text", "text": full_prompt})

    try:
        response = client.messages.create(
            model=model,
            max_tokens=MAX_OUTPUT_TOKENS,
            messages=[{"role": "user", "content": content}],
        )
    except Exception as e:
        raise LLMError(f"Claude API call failed: {e}") from e

    parts = [block.text for block in response.content if getattr(block, "text", None)]
    return "\n".join(parts).strip()


# ---------- OpenAI ----------

def call_openai(
    image_paths: List[str],
    prompt: str,
    *,
    transcript: Optional[str] = None,
    model: str = DEFAULT_OPENAI_MODEL,
) -> str:
    try:
        from openai import OpenAI
    except ImportError as e:
        raise LLMError(
            "openai SDK not installed. Run: pip install vidgrid[openai]"
        ) from e

    client = OpenAI()

    user_content: list[dict] = []
    for path in image_paths:
        media_type, b64_data = _encode_image(path)
        user_content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{media_type};base64,{b64_data}"},
            }
        )

    full_prompt = _build_prompt(prompt, transcript)
    user_content.append({"type": "text", "text": full_prompt})

    try:
        response = client.chat.completions.create(
            model=model,
            max_tokens=MAX_OUTPUT_TOKENS,
            messages=[{"role": "user", "content": user_content}],
        )
    except Exception as e:
        raise LLMError(f"OpenAI API call failed: {e}") from e

    return (response.choices[0].message.content or "").strip()


# ---------- Google Gemini ----------

def call_gemini(
    image_paths: List[str],
    prompt: str,
    *,
    transcript: Optional[str] = None,
    model: str = DEFAULT_GEMINI_MODEL,
) -> str:
    try:
        from google import genai
    except ImportError as e:
        raise LLMError(
            "google-genai SDK not installed. Run: pip install vidgrid[gemini]"
        ) from e

    client = genai.Client()

    parts: list = []
    for path in image_paths:
        with open(path, "rb") as f:
            image_bytes = f.read()
        parts.append(
            {
                "inline_data": {
                    "mime_type": _guess_mime(path),
                    "data": base64.b64encode(image_bytes).decode("ascii"),
                }
            }
        )

    full_prompt = _build_prompt(prompt, transcript)
    parts.append({"text": full_prompt})

    try:
        response = client.models.generate_content(
            model=model,
            contents=parts,
        )
    except Exception as e:
        raise LLMError(f"Gemini API call failed: {e}") from e

    return (getattr(response, "text", None) or "").strip()


# ---------- helpers ----------

def _encode_image(path: str) -> tuple[str, str]:
    """Return (media_type, base64_data) for a file on disk."""
    p = Path(path)
    if not p.exists():
        raise LLMError(f"Image not found: {path}")
    media_type = _guess_mime(path)
    data = base64.b64encode(p.read_bytes()).decode("ascii")
    return media_type, data


def _guess_mime(path: str) -> str:
    mime, _ = mimetypes.guess_type(path)
    if mime and mime.startswith("image/"):
        return mime
    return "image/png"


def _build_prompt(prompt: str, transcript: Optional[str]) -> str:
    if not transcript:
        return prompt
    return (
        f"{prompt}\n\n"
        "---\n"
        "Transcript (aligned to timestamps visible in the image):\n"
        f"{transcript}"
    )
