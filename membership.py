"""
Mandatory channel-membership gate.

Configuration (.env):
    REQUIRED_CHANNEL=@your_channel    # @username  OR  numeric ID (-100…)

Leave blank / unset to disable the gate entirely.
• Admins (ADMIN_ID stored in bot_data) always bypass the check.
• Any get_chat_member API error lets the user through silently (fail-open).
"""

import os
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)


def _get_channel() -> str:
    """Read REQUIRED_CHANNEL fresh every call — safe regardless of import order."""
    return os.getenv("REQUIRED_CHANNEL", "").strip()


def _channel_url(channel: str) -> str:
    """Build a clickable t.me link from a @username or numeric chat-id."""
    tag = channel.lstrip("@")
    if tag.lstrip("-").isdigit():          # e.g. -1001234567890 → t.me/c/1234567890
        return f"https://t.me/c/{tag.lstrip('-')}"
    return f"https://t.me/{tag}"           # e.g. @mychannel → t.me/mychannel


async def is_member(bot, user_id: int, admin_id: int) -> bool:
    """
    Return True when the user is allowed to proceed, False when they are
    definitively not a channel member.

    True conditions:
      • REQUIRED_CHANNEL is not set (gate disabled)
      • user_id == admin_id (admin bypass)
      • get_chat_member status is member / administrator / creator
      • get_chat_member raised any exception (fail-open / silent)
    """
    channel = _get_channel()
    if not channel:
        return True
    if user_id == admin_id:
        return True
    try:
        member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
        return member.status in ("member", "administrator", "creator")
    except Exception as exc:
        logger.warning("Membership check failed for user %s: %s", user_id, exc)
        return True   # fail-open: API errors must not lock users out


async def send_join_prompt(bot, chat_id: int) -> None:
    """
    Send the 'please join first' message with an inline Join button.
    Safe to call even when REQUIRED_CHANNEL is not configured (no-op).
    """
    channel = _get_channel()
    if not channel:
        return
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("📢 Join Channel", url=_channel_url(channel))
    ]])
    await bot.send_message(
        chat_id=chat_id,
        text=(
            "⚠️ You must join our channel before using this bot.\n\n"
            "Tap the button below to join, then send any message or "
            "command to continue."
        ),
        reply_markup=kb,
    )
