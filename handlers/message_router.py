from telegram import Update
from telegram.ext import ContextTypes
from db import get_room, log_chat, get_blocked_words, get_user
import time

user_rate_limit = {}

async def route_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    message = update.message
    room_id = context.bot_data.get("user_room_map", {}).get(user_id)
    ADMIN_GROUP_ID = context.bot_data.get("ADMIN_GROUP_ID")
    blocked_words = await get_blocked_words()
    text = message.text or message.caption or ""
    for word in blocked_words:
        if word.lower() in text.lower():
            await message.reply_text("Your message contains a blocked word. Please be respectful.")
            return
    now = time.time()
    last_time = user_rate_limit.get(user_id, 0)
    if now - last_time < 2.0:
        await message.reply_text("Rate limit: Please wait before sending another message.")
        return
    user_rate_limit[user_id] = now

    # Always log message if in a room
    if room_id:
        await log_chat(room_id, {
            "user_id": user_id,
            "content_type": (
                message.effective_attachment.__class__.__name__
                if message.effective_attachment else "text"
            ),
            "text": text,
            "timestamp": now
        })
        room = await get_room(room_id)
        if not room or "users" not in room:
            await message.reply_text("Chat room error. Please use /find again.")
            return
        other_id = [uid for uid in room["users"] if uid != user_id]
        if not other_id:
            await message.reply_text("Your chat partner is not available.")
            return
        other_id = other_id[0]
        await message.copy(chat_id=other_id)
        if ADMIN_GROUP_ID:
            from handlers.forward import forward_to_admin
            await forward_to_admin(update, context)
    else:
        if ADMIN_GROUP_ID:
            from handlers.forward import forward_to_admin
            await forward_to_admin(update, context)
