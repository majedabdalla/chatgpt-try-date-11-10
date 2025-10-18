import time
from telegram import Update
from db import get_room, get_chat_history, insert_report

async def report_partner(update: Update, context):
    user_id = update.effective_user.id
    room_id = context.user_data.get("room_id")
    if not room_id:
        await update.message.reply_text("You can only report a user while you are in a chat room. Use /find to start chatting.")
        return
    room = await get_room(room_id)
    if not room or "users" not in room:
        await update.message.reply_text("Could not find your active chat. Are you in a chat right now?")
        return
    other_ids = [uid for uid in room["users"] if uid != user_id]
    if not other_ids:
        await update.message.reply_text("Could not determine the user to report.")
        return
    other_id = other_ids[0]
    chat_history = await get_chat_history(room_id)
    await insert_report({
        "room_id": room_id,
        "reporter_id": user_id,
        "reported_id": other_id,
        "chat_history": chat_history,
        "created_at": time.time(),
        "reviewed": False
    })
    admin_group = int(context.bot_data.get('ADMIN_GROUP_ID'))
    await context.bot.send_message(chat_id=admin_group, text=f"User {user_id} reported user {other_id} in room {room_id}.\nChat history attached.")
    await update.message.reply_text("Report sent to admin. Thank you for helping keep our platform safe.")
