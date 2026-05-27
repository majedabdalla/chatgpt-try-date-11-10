import time
from telegram import Update
from db import get_room, get_chat_history, insert_report, get_user, get_user_room
from helpers import make_mention


async def report_partner(update: Update, context):
    user_id = update.effective_user.id

    room_id = await get_user_room(user_id)

    if not room_id:
        await update.message.reply_text(
            "You can only report a user while you are in a chat room. Use /find to start chatting."
        )
        return

    room = await get_room(room_id)
    if not room or "users" not in room:
        await update.message.reply_text(
            "Could not find your active chat. Are you in a chat right now?"
        )
        return

    other_ids = [uid for uid in room["users"] if uid != user_id]
    if not other_ids:
        await update.message.reply_text("Could not determine the user to report.")
        return

    other_id = other_ids[0]

    user1 = await get_user(user_id)
    user2 = await get_user(other_id)

    def profile_text(u, label):
        uid = u.get('user_id')
        mention = make_mention(uid, u)
        username_display = f"@{u.get('username')}" if u.get('username') else "No username"
        return (
            f"{label}\n"
            f"ID: {uid} | {mention} | {username_display}\n"
            f"Phone: {u.get('phone_number', 'N/A')}\n"
            f"Language: {u.get('language', 'en')}\n"
            f"Gender: {u.get('gender', '')}\n"
            f"Region: {u.get('region', '')}\n"
            f"Premium: {u.get('is_premium', False)}"
        )

    profile1 = profile_text(user1, "👤 Reporter:")
    profile2 = profile_text(user2, "👤 Reported:")

    reported_msg = update.message.reply_to_message
    if reported_msg:
        if reported_msg.text:
            reported_text = reported_msg.text
        elif reported_msg.caption:
            reported_text = reported_msg.caption
        else:
            reported_text = "(Message type not supported for reporting.)"

        reported_by_user = reported_msg.from_user.id if reported_msg.from_user else "Unknown"
        # Escape any HTML special chars in user content before embedding
        safe_text = (
            reported_text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        reported_msg_details = (
            f"📝 Reported Message (by user {reported_by_user}):\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"{safe_text}\n"
            f"━━━━━━━━━━━━━━━━\n"
        )
    else:
        reported_msg_details = (
            "ℹ️ No specific message was reported.\n"
            "(User used /report without replying to a message)\n"
        )

    chat_history = await get_chat_history(room_id)

    await insert_report({
        "room_id": room_id,
        "reporter_id": user_id,
        "reported_id": other_id,
        "chat_history": chat_history,
        "created_at": time.time(),
        "reviewed": False
    })

    admin_group = context.bot_data.get('ADMIN_GROUP_ID')
    if admin_group:
        report_msg = (
            f"🚨 <b>REPORT RECEIVED</b> 🚨\n"
            f"━━━━━━━━━━━━━━━━\n\n"
            f"📍 Room: <code>{room_id}</code>\n\n"
            f"{reported_msg_details}\n"
            f"{profile1}\n\n"
            f"{profile2}\n\n"
            f"💬 Total messages in room: {len(chat_history)}\n"
            f"⏰ Report time: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}"
        )

        try:
            await context.bot.send_message(
                chat_id=admin_group,
                text=report_msg,
                parse_mode='HTML',
            )

            if user2 and user2.get('profile_photos'):
                for photo_id in user2['profile_photos'][:3]:
                    try:
                        await context.bot.send_photo(
                            chat_id=admin_group,
                            photo=photo_id,
                            caption=f"Photo of reported user {other_id}",
                        )
                    except Exception:
                        pass
        except Exception as e:
            import logging
            logging.error(f"Could not send report to admin group: {e}")

    await update.message.reply_text(
        "✅ Report sent to admin. Thank you for helping keep our platform safe.\n\n"
        "Our team will review this report and take appropriate action."
    )
