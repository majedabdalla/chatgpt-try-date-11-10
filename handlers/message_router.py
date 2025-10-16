from telegram import Update
from telegram.ext import ContextTypes
from db import get_room, log_chat, get_blocked_words, get_user
import re

# Regex for links and Telegram bot usernames
link_or_bot_regex = re.compile(
    r'(http[s]?://|www\.|\.com|\.net|\.org|\.me|\.io|\.ly|\.ru|\.ir|\.in|\.id|@[\w\d_]{5,32}bot\b)',
    re.IGNORECASE
)
user_link_strike_counter = {}

MAX_LINK_STRIKES = 3  # Block after 3 warnings

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

    # Check for links or Telegram bot usernames
    if link_or_bot_regex.search(text):
        strike_key = f"{user_id}"
        user_link_strike_counter.setdefault(strike_key, 0)
        user_link_strike_counter[strike_key] += 1
        if user_link_strike_counter[strike_key] < MAX_LINK_STRIKES:
            await message.reply_text(locale.get("policy_no_links", "Links and Telegram bot usernames are not allowed. This is against bot policy."))
            return
        else:
            if ADMIN_GROUP_ID:
                await context.bot.send_message(
                    chat_id=ADMIN_GROUP_ID,
                    text=f"#spam User {user_id} (@{user.get('username','')}) sent forbidden links or bot usernames 3 times. Please consider blocking."
                )
            await message.reply_text(locale.get("policy_blocked", "You have violated the bot policy multiple times. Admin has been notified."))
            return

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
        try:
            await message.copy(chat_id=other_id)
        except Exception as e:
            await message.reply_text("Your partner has left the chat.")
            context.bot_data["user_room_map"].pop(user_id, None)
            return
        if ADMIN_GROUP_ID:
            from handlers.forward import forward_to_admin
            await forward_to_admin(update, context)
    else:
        await message.reply_text(locale.get("not_in_room", "You are not in a chat. Use /find or main menu to start one."))
        if ADMIN_GROUP_ID:
            from handlers.forward import forward_to_admin
            await forward_to_admin(update, context)
