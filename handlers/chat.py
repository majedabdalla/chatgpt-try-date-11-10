from telegram import Update
from telegram.ext import ContextTypes
from db import get_room, update_room, log_chat, get_blocked_words
import re

# Regex for links and Telegram bot usernames (robust, covers most common cases)
link_or_bot_regex = re.compile(
    r'(http[s]?://|www\.|\.com|\.net|\.org|\.me|\.io|\.ly|\.ru|\.ir|\.in|\.id|@[\w\d_]{5,32}bot\b)',
    re.IGNORECASE
)
user_link_strike_counter = {}

MAX_LINK_STRIKES = 3  # 3 strikes: then notify admin with #spam

async def process_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    # FIX: Try context.user_data['room_id'] first, then fallback to bot_data['user_room_map']
    room_id = context.user_data.get("room_id")
    if not room_id:
        room_id = context.bot_data.get("user_room_map", {}).get(user_id)
    if not room_id:
        await update.message.reply_text("Not in a room. Use /find to start a chat.")
        return

    blocked_words = await get_blocked_words()
    for word in blocked_words:
        if word.lower() in text.lower():
            await update.message.reply_text("Your message contains a blocked word. Please be respectful.")
            return

    # Check for links or Telegram bot usernames
    if link_or_bot_regex.search(text):
        # Count strikes per user per session
        strike_key = f"{user_id}"
        user_link_strike_counter.setdefault(strike_key, 0)
        user_link_strike_counter[strike_key] += 1
        if user_link_strike_counter[strike_key] < MAX_LINK_STRIKES:
            await update.message.reply_text("Links and Telegram bot usernames are not allowed. This is against bot policy.")
            return
        else:
            # On 3rd strike: notify admin group for block request
            admin_group_id = context.bot_data.get("ADMIN_GROUP_ID")
            if admin_group_id:
                await context.bot.send_message(
                    chat_id=admin_group_id,
                    text=f"#spam User {user_id} sent forbidden links or bot usernames 3 times. Please consider blocking."
                )
            await update.message.reply_text("You have violated the bot policy multiple times. Admin has been notified.")
            return

    # No rate limiting. Just log and forward the message.
    await log_chat(room_id, {
        "user_id": user_id,
        "text": text,
        "timestamp": update.message.date.timestamp() if update.message.date else None
    })
    room = await get_room(room_id)
    if not room or "users" not in room:
        await update.message.reply_text("Chat room error. Please use /find again.")
        return
    other_id = [uid for uid in room["users"] if uid != user_id]
    if not other_id:
        await update.message.reply_text("Your chat partner is not available.")
        return
    other_id = other_id[0]
    await context.bot.send_message(chat_id=other_id, text=text)
