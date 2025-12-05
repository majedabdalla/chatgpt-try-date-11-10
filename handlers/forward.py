from telegram import Update
from telegram.ext import ContextTypes
from db import get_room, get_user

async def forward_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    # FIX: Display username properly
    username = f"@{user.username}" if user.username else "No username"
    
    room_id = context.bot_data.get("user_room_map", {}).get(user_id, 0)
    admin_group_id = context.bot_data.get("ADMIN_GROUP_ID")

    # Get receiver info
    room = await get_room(room_id)
    receiver_id = None
    if room and "users" in room:
        receiver_id = [uid for uid in room["users"] if uid != user_id]
        receiver_id = receiver_id[0] if receiver_id else None
    receiver = await get_user(receiver_id) if receiver_id else None

    # FIX: Display receiver username properly
    receiver_username = f"@{receiver.get('username')}" if receiver and receiver.get('username') else "No username"

    header = f"📢 Room #{room_id}\n👤 Sender: {user_id} (username: {username}, phone: {getattr(user, 'phone_number', 'N/A')})"
    if receiver:
        header += f"\n👥 Receiver: {receiver['user_id']} (username: {receiver_username}, phone: {receiver.get('phone_number','N/A')})"
    header += f"\nRoom Created: {room['created_at'] if room else 'N/A'}\n"

    msg = None
    # Forward text
    if update.message.text:
        msg = f"{header}\n💬 Message: {update.message.text}"
        await context.bot.send_message(chat_id=admin_group_id, text=msg)
    # Forward photo
    elif update.message.photo:
        caption = f"{header}\n[Photo message]"
        await context.bot.send_photo(
            chat_id=admin_group_id,
            photo=update.message.photo[-1].file_id,
            caption=caption
        )
    # Forward video
    elif update.message.video:
        caption = f"{header}\n[Video message]"
        await context.bot.send_video(
            chat_id=admin_group_id,
            video=update.message.video.file_id,
            caption=caption
        )
    # Forward video note (round video)
    elif getattr(update.message, "video_note", None):
        caption = f"{header}\n[Video Note (round video)]"
        await context.bot.send_video_note(
            chat_id=admin_group_id,
            video_note=update.message.video_note.file_id
        )
        await context.bot.send_message(chat_id=admin_group_id, text=caption)
    # Forward audio
    elif update.message.audio:
        caption = f"{header}\n[Audio message]"
        await context.bot.send_audio(
            chat_id=admin_group_id,
            audio=update.message.audio.file_id,
            caption=caption
        )
    # Forward voice
    elif update.message.voice:
        caption = f"{header}\n[Voice message]"
        await context.bot.send_voice(
            chat_id=admin_group_id,
            voice=update.message.voice.file_id,
            caption=caption
        )
    # Forward document
    elif update.message.document:
        caption = f"{header}\n[Document message]"
        await context.bot.send_document(
            chat_id=admin_group_id,
            document=update.message.document.file_id,
            caption=caption
        )
    # Forward sticker
    elif update.message.sticker:
        caption = f"{header}\n[Sticker]"
        await context.bot.send_sticker(
            chat_id=admin_group_id,
            sticker=update.message.sticker.file_id
        )
        await context.bot.send_message(chat_id=admin_group_id, text=header + "\n[Sticker sent above]")
    else:
        try:
            await update.message.forward(chat_id=admin_group_id)
            await context.bot.send_message(chat_id=admin_group_id, text=header + "\n[Above: unknown message type forwarded]")
        except Exception as e:
            await context.bot.send_message(chat_id=admin_group_id, text=header + f"\n[Could not forward message: {e}]\nType: {type(update.message)}\n{update.message}")
