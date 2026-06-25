"""
gemini_client.py
-----------------
Async Gemini translation client using google-genai's client.aio interface.
"""

import asyncio
import logging
from typing import Optional

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

_SYSTEM_INSTRUCTION = (
    "You are a translation engine specialized in informal Indonesian "
    "internet slang, abbreviated text speak, and casual chat language.\n\n"
    "Translate the user's message into fluent, natural English.\n\n"
    "Rules:\n"
    "- Infer the intended meaning even when the source is fragmented, "
    "has typos, repeats words, or omits the subject.\n"
    "- Preserve the original tone (e.g. rude, casual, sarcastic, "
    "affectionate, angry) wherever possible -- this is a meaning-for-"
    "meaning translation, not a literal word-for-word one.\n"
    "- Output ONLY the translated text. No labels like 'Translation:', "
    "no notes, no explanations, no analysis, no disclaimers.\n"
    "- Do not wrap the output in quotation marks.\n"
    "- Do not use markdown or any other formatting unless the source "
    "text itself requires it.\n"
    "- If the source text is already in English, return a cleaned-up "
    "version with the same meaning."
)

_TEMPERATURE = 0.3
_MAX_OUTPUT_TOKENS = 512


class TranslationError(Exception):
    """Raised whenever a translation could not be produced."""


class GeminiTranslator:
    def __init__(self, api_key: str, model: str, timeout_seconds: float = 20.0) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._timeout_seconds = timeout_seconds

    async def translate(self, text: str) -> str:
        cleaned = text.strip()
        if not cleaned:
            raise TranslationError("Cannot translate empty text.")

        try:
            response = await asyncio.wait_for(
                self._client.aio.models.generate_content(
                    model=self._model,
                    contents=cleaned,
                    config=types.GenerateContentConfig(
                        system_instruction=_SYSTEM_INSTRUCTION,
                        temperature=_TEMPERATURE,
                        max_output_tokens=_MAX_OUTPUT_TOKENS,
                        # Relax safety filters. This is an internal admin-log
                        # translation of casual/rude/flirty anonymous chat
                        # text, not user-facing generation. Without this,
                        # Gemini's default thresholds silently block a large
                        # fraction of normal chat messages and the failure
                        # looks identical to every other [Unavailable] case.
                        safety_settings=[
                            types.SafetySetting(
                                category=cat,
                                threshold="BLOCK_NONE",
                            )
                            for cat in (
                                "HARM_CATEGORY_HARASSMENT",
                                "HARM_CATEGORY_HATE_SPEECH",
                                "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                                "HARM_CATEGORY_DANGEROUS_CONTENT",
                            )
                        ],
                    ),
                ),
                timeout=self._timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            logger.warning("Gemini request timed out after %.1fs", self._timeout_seconds)
            raise TranslationError("Translation request timed out.") from exc
        except Exception as exc:
            logger.error("Gemini API call failed (%s): %s", type(exc).__name__, exc)
            raise TranslationError(f"Translation request failed: {exc}") from exc

        translated, reason = _extract_text(response)
        if not translated:
            logger.warning(
                "Gemini returned no usable text for input %r — reason=%s",
                cleaned[:200], reason,
            )
            raise TranslationError(f"Translation returned no usable text ({reason}).")

        return translated


def _extract_text(response: object) -> tuple[Optional[str], str]:
    """Return (text, diagnostic_reason). text is None on any failure."""
    # Fast path: SDK successfully assembled flat text.
    text = getattr(response, "text", None)
    if text and text.strip():
        return text.strip(), "ok"

    # Slow path: figure out *why* there's no text, from candidates.
    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        prompt_feedback = getattr(response, "prompt_feedback", None)
        block_reason = getattr(prompt_feedback, "block_reason", None)
        if block_reason:
            return None, f"prompt_blocked:{block_reason}"
        return None, "no_candidates"

    candidate = candidates[0]
    finish_reason = getattr(candidate, "finish_reason", None)
    safety_ratings = getattr(candidate, "safety_ratings", None)

    if finish_reason and str(finish_reason) not in ("STOP", "FinishReason.STOP"):
        detail = f"finish_reason:{finish_reason}"
        if safety_ratings:
            blocked = [
                str(getattr(r, "category", r))
                for r in safety_ratings
                if getattr(r, "blocked", False)
            ]
            if blocked:
                detail += f" blocked_categories:{blocked}"
        return None, detail

    # finish_reason was STOP but there's still no text -- try pulling
    # raw parts directly as a last resort.
    content = getattr(candidate, "content", None)
    parts = getattr(content, "parts", None) or []
    joined = "".join(getattr(p, "text", "") or "" for p in parts).strip()
    if joined:
        return joined, "ok_via_parts"

    return None, "empty_parts_with_stop"
