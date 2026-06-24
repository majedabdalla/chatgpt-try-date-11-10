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
                    ),
                ),
                timeout=self._timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            logger.warning("Gemini request timed out after %.1fs", self._timeout_seconds)
            raise TranslationError("Translation request timed out.") from exc
        except Exception as exc:
            logger.error("Gemini API call failed: %s", exc)
            raise TranslationError("Translation request failed.") from exc

        translated = _extract_text(response)
        if not translated:
            logger.warning("Gemini returned an empty or unusable response.")
            raise TranslationError("Translation returned no usable text.")

        return translated


def _extract_text(response: object) -> Optional[str]:
    text = getattr(response, "text", None)
    return text.strip() if text else None
