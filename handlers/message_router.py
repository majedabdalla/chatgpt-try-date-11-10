from telegram import Update
from telegram.ext import ContextTypes
from db import get_room, log_chat, get_blocked_words, get_user
import re

# SPAM PREVENTION LOGIC: instead of time-based, detect excessive link sharing and warn admin

link_regex = re.compile(r'(http[s]?://|www\.|\.com|\.net|\.org|\.me|\.io|\.ly|\.ru|\.ir|\.in|\.id)', re.IGNORECASE)
user_link_spam_counter = {}

MAX_LINKS_PER_SESSION = 3  # Threshold for link messages per session before warning admin

async def route_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    message = update.message
    room_id = context.bot_data.get("user_room_map", {}).get(user_id)
    ADMIN_GROUP_ID = context.bot_data.get("ADMIN_GROUP_ID")
    user = await get_user(user_id)
    lang = user.get("language", "en") if user else "en"

    from bot import load_locale
    locale = load_locale(lang)

    blocked_words = await get_blocked_words()
    text = message.text or message.caption or ""
    for word in blocked_words:
        if word.lower() in text.lower():
            await message.reply_text(locale.get("blocked_word", "Your message contains a blocked word. Please be respectful."))
            return

    # SPAM detection: count link messages in session
    session_key = f"{room_id}:{user_id}"
    if link_regex.search(text):
        user_link_spam_counter.setdefault(session_key, 0)
        user_link_spam_counter[session_key] += 1
        if user_link_spam_counter[session_key] >= MAX_LINKS_PER_SESSION:
            if ADMIN_GROUP_ID:
                await context.bot.send_message(
                    chat_id=ADMIN_GROUP_ID,
                    text=f"⚠️ User {user_id} (@{user.get('username','')}) may be spamming links in room {room_id}! Please review and consider blocking."
                )

    # If user is awaiting for upgrade proof, handle as proof.
    if context.user_data.get("awaiting_upgrade_proof"):
        from handlers.premium import handle_proof
        await handle_proof(update, context)
        return

    # Always log/forward
    if room_id:
        await log_chat(room_id, {
            "user_id": user_id,
            "content_type": (
                message.effective_attachment.__class__.__name__
                if message.effective_attachment else "text"
            ),
            "text": text,
            "timestamp": message.date.timestamp() if message.date else None
        })
        room = await get_room(room_id)
        if not room or "users" not in room:
            await message.reply_text(locale.get("chat_error", "Chat room error. Please use /find again."))
            return
        other_id = [uid for uid in room["users"] if uid != user_id]
        if not other_id:
            await message.reply_text(locale.get("partner_left", "Your chat partner is not available."))
            return
        other_id = other_id[0]
        await message.copy(chat_id=other_id)
        if ADMIN_GROUP_ID:
            from handlers.forward import forward_to_admin
            await forward_to_admin(update, context)
    else:
        # Not in a room - tell user, but still forward to admin
        await message.reply_text(locale.get("not_in_room", "You are not in a chat. Use /find or main menu to start one."))
        if ADMIN_GROUP_ID:
            from handlers.forward import forward_to_admin
            await forward_to_admin(update, context)
