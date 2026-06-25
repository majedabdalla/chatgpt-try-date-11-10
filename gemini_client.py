"""
gemini_client.py
-----------------
Async translation client. Originally built for Gemini; now backed by Groq's
OpenAI-compatible chat completions API for a much more generous free tier.

The class name, constructor signature, and translate() interface are kept
identical to the original Gemini-based version on purpose -- bot.py and
handlers/forward.py import GeminiTranslator and call translator.translate()
without any awareness of which provider is behind it. Swapping providers
again later only means editing this file.

Despite the name, GEMINI_API_KEY / GEMINI_MODEL env vars now hold your
Groq credentials -- see the Railway env var notes at the bottom of this file.
"""

import asyncio
import logging
from typing import Optional

from groq import AsyncGroq

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

# Groq model to fall back to if the configured model name looks like a
# leftover Gemini model string (e.g. someone forgot to update GEMINI_MODEL
# after switching providers). Llama 3.3 70B is a solid default for this
# kind of casual-slang translation workload.
_DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"


class TranslationError(Exception):
    """Raised whenever a translation could not be produced."""


class GeminiTranslator:
    """Name kept for backwards compatibility with bot.py's import.
    Internally this is now a Groq-backed translator.
    """

    def __init__(self, api_key: str, model: str, timeout_seconds: float = 20.0) -> None:
        self._client = AsyncGroq(api_key=api_key)
        # If GEMINI_MODEL still has an old "gemini-..." value left over in
        # Railway, fall back to a sane Groq default instead of sending a
        # request Groq can't possibly serve.
        self._model = model if model and not model.lower().startswith("gemini") else _DEFAULT_GROQ_MODEL
        self._timeout_seconds = timeout_seconds

    async def translate(self, text: str) -> str:
        cleaned = text.strip()
        if not cleaned:
            raise TranslationError("Cannot translate empty text.")

        try:
            response = await asyncio.wait_for(
                self._client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": _SYSTEM_INSTRUCTION},
                        {"role": "user", "content": cleaned},
                    ],
                    temperature=_TEMPERATURE,
                    max_tokens=_MAX_OUTPUT_TOKENS,
                ),
                timeout=self._timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            logger.warning("Groq request timed out after %.1fs", self._timeout_seconds)
            raise TranslationError("Translation request timed out.") from exc
        except Exception as exc:
            logger.error("Groq API call failed (%s): %s", type(exc).__name__, exc)
            raise TranslationError(f"Translation request failed: {exc}") from exc

        translated, reason = _extract_text(response)
        if not translated:
            logger.warning(
                "Groq returned no usable text for input %r — reason=%s",
                cleaned[:200], reason,
            )
            raise TranslationError(f"Translation returned no usable text ({reason}).")

        return translated


def _extract_text(response: object) -> tuple[Optional[str], str]:
    """Return (text, diagnostic_reason). text is None on any failure."""
    choices = getattr(response, "choices", None) or []
    if not choices:
        return None, "no_choices"

    choice = choices[0]
    finish_reason = getattr(choice, "finish_reason", None)
    message = getattr(choice, "message", None)
    content = getattr(message, "content", None) if message else None

    if content and content.strip():
        return content.strip(), "ok"

    if finish_reason and finish_reason not in ("stop", "length"):
        return None, f"finish_reason:{finish_reason}"

    return None, "empty_content"


# -----------------------------------------------------------------------
# Railway env var notes (no code changes needed beyond this file):
#
#   GEMINI_API_KEY        -> set this to your Groq API key (gsk_...)
#   GEMINI_MODEL           -> set this to a Groq model name, e.g.:
#                             llama-3.3-70b-versatile   (best quality/balance)
#                             llama-3.1-8b-instant      (fastest, lighter)
#   GEMINI_TIMEOUT_SECONDS -> unchanged, still works the same way
#
# requirements.txt also needs one change: replace `google-genai>=1.2.0`
# with `groq>=0.11.0`.
# -----------------------------------------------------------------------
