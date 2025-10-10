import time
from telegram import Update
from db import get_room, get_chat_history, insert_report

async def report_partner(update: Update, context):
    user_id = update.effective_user.id
    room_id = context.user_data.get("room_id")
    room = await get_room(room_id)
    other_id = [uid for uid in room["users"] if uid != user_id][0]
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
    # Optionally send chat log as a file
    # ... (add file send logic if needed)
    await update.message.reply_text("Report sent to admin. Thank you for helping keep our platform safe.")
