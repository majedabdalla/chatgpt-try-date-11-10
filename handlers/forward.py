import logging
from html import escape as html_escape
from gemini_client import TranslationError

logger = logging.getLogger(__name__)

from telegram import Update
from telegram.ext import ContextTypes
from db import get_room, get_user, get_user_room
from helpers import make_mention


async def forward_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id

    room_id = await get_user_room(user_id)
    admin_group_id = context.bot_data.get("ADMIN_GROUP_ID")

    room = await get_room(room_id) if room_id else None
    receiver_id = None
    if room and "users" in room:
        receiver_id = [uid for uid in room["users"] if uid != user_id]
        receiver_id = receiver_id[0] if receiver_id else None
    receiver = await get_user(receiver_id) if receiver_id else None

    # --- Build tappable HTML mentions ---
    # Sender: prefer DB record (has name); fall back to live Telegram object
    sender_db = await get_user(user_id)
    sender_data = sender_db if sender_db else {
        "name": user.full_name or user.first_name or "",
        "username": user.username or "",
    }
    sender_mention = make_mention(user_id, sender_data)
    sender_username = f"@{sender_data.get('username')}" if sender_data.get('username') else "No username"
    sender_phone = sender_db.get("phone_number", "N/A") if sender_db else "N/A"

    header = (
        f"📢 Room #{room_id}\n"
        f"👤 Sender: {sender_mention} | {sender_username} (ID: {user_id}, phone: {sender_phone})"
    )

    if receiver and receiver_id:
        receiver_mention = make_mention(receiver_id, receiver)
        receiver_username = f"@{receiver.get('username')}" if receiver.get('username') else "No username"
        receiver_phone = receiver.get("phone_number", "N/A")
        header += (
            f"\n👥 Receiver: {receiver_mention} | {receiver_username} "
            f"(ID: {receiver_id}, phone: {receiver_phone})"
        )

    header += f"\nRoom Created: {room['created_at'] if room else 'N/A'}\n"

    # --- Forward the actual message content ---
    if update.message.text:
        original_text = update.message.text

        # Translate before sending the log so the translation lands in
        # the SAME admin message. A translation failure never drops the
        # underlying log -- it just falls back to "[Unavailable]".
        translator = context.bot_data.get("translator")
        translation = "[Unavailable: translator not initialized]"
        if translator is not None:
            try:
                translation = await translator.translate(original_text)
            except TranslationError as e:
                logger.warning(f"Gemini translation failed for room {room_id}: {e}")
                translation = f"[Unavailable: {e}]"
        else:
            logger.warning("Gemini translator not initialized; skipping translation.")

        msg = (
            f"{header}\n"
            f"💬 Message: {original_text}\n"
            f"🗣️ Translation: {html_escape(translation)}"
        )
        await context.bot.send_message(
            chat_id=admin_group_id, text=msg, parse_mode='HTML'
        )
    elif update.message.photo:
        await context.bot.send_photo(
            chat_id=admin_group_id,
            photo=update.message.photo[-1].file_id,
            caption=f"{header}\n[Photo message]",
            parse_mode='HTML',
        )
    elif update.message.video:
        await context.bot.send_video(
            chat_id=admin_group_id,
            video=update.message.video.file_id,
            caption=f"{header}\n[Video message]",
            parse_mode='HTML',
        )
    elif getattr(update.message, "video_note", None):
        await context.bot.send_video_note(
            chat_id=admin_group_id,
            video_note=update.message.video_note.file_id,
        )
        await context.bot.send_message(
            chat_id=admin_group_id,
            text=f"{header}\n[Video Note (round video)]",
            parse_mode='HTML',
        )
    elif update.message.audio:
        await context.bot.send_audio(
            chat_id=admin_group_id,
            audio=update.message.audio.file_id,
            caption=f"{header}\n[Audio message]",
            parse_mode='HTML',
        )
    elif update.message.voice:
        await context.bot.send_voice(
            chat_id=admin_group_id,
            voice=update.message.voice.file_id,
            caption=f"{header}\n[Voice message]",
            parse_mode='HTML',
        )
    elif update.message.document:
        await context.bot.send_document(
            chat_id=admin_group_id,
            document=update.message.document.file_id,
            caption=f"{header}\n[Document message]",
            parse_mode='HTML',
        )
    elif update.message.sticker:
        await context.bot.send_sticker(
            chat_id=admin_group_id,
            sticker=update.message.sticker.file_id,
        )
        await context.bot.send_message(
            chat_id=admin_group_id,
            text=f"{header}\n[Sticker sent above]",
            parse_mode='HTML',
        )
    else:
        try:
            await update.message.forward(chat_id=admin_group_id)
            await context.bot.send_message(
                chat_id=admin_group_id,
                text=f"{header}\n[Above: unknown message type forwarded]",
                parse_mode='HTML',
            )
        except Exception as e:
            await context.bot.send_message(
                chat_id=admin_group_id,
                text=(
                    f"{header}\n[Could not forward message: {e}]\n"
                    f"Type: {type(update.message)}\n{update.message}"
                ),
                parse_mode='HTML',
        )
