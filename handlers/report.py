import time
from telegram import Update
from db import get_room, get_chat_history, insert_report, get_user

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

    # Get profiles of both users
    user1 = await get_user(user_id)
    user2 = await get_user(other_id)
    def profile_text(u, label):
        return (
            f"{label}\n"
            f"ID: {u.get('user_id')}\n"
            f"Username: @{u.get('username','')}\n"
            f"Phone: {u.get('phone_number','N/A')}\n"
            f"Language: {u.get('language','en')}\n"
            f"Gender: {u.get('gender','')}\n"
            f"Region: {u.get('region','')}\n"
            f"Premium: {u.get('is_premium', False)}"
        )
    profile1 = profile_text(user1, "👤 User1:")
    profile2 = profile_text(user2, "👤 User2:")

    # Get the message being reported, if /report is used as a reply
    reported_msg = update.message.reply_to_message
    if reported_msg:
        if reported_msg.text:
            reported_text = reported_msg.text
        elif reported_msg.caption:
            reported_text = reported_msg.caption
        else:
            reported_text = "(Message type not supported for reporting.)"
        reported_by_user = reported_msg.from_user.id if reported_msg.from_user else "Unknown"
        reported_msg_details = (
            f"Reported Message (by user {reported_by_user}):\n"
            f"{reported_text}\n"
        )
    else:
        reported_msg_details = "(No specific message was reported. User used /report without replying to a message.)"

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
    report_msg = (
        f"🚨 User {user_id} reported user {other_id} in room {room_id}.\n"
        f"{reported_msg_details}\n\n"
        f"{profile1}\n\n{profile2}\n"
        # Optionally, you could attach chat history as a file or as text if desired
    )
    await context.bot.send_message(chat_id=admin_group, text=report_msg)

    await update.message.reply_text("Report sent to admin. Thank you for helping keep our platform safe.")
import time
from telegram import Update
from db import get_room, get_chat_history, insert_report, get_user

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

    # Get profiles of both users
    user1 = await get_user(user_id)
    user2 = await get_user(other_id)
    
    def profile_text(u, label):
        # FIX: Display username properly
        username_display = f"@{u.get('username')}" if u.get('username') else "No username"
        
        return (
            f"{label}\n"
            f"ID: {u.get('user_id')}\n"
            f"Username: {username_display}\n"
            f"Phone: {u.get('phone_number','N/A')}\n"
            f"Language: {u.get('language','en')}\n"
            f"Gender: {u.get('gender','')}\n"
            f"Region: {u.get('region','')}\n"
            f"Premium: {u.get('is_premium', False)}"
        )
    profile1 = profile_text(user1, "👤 User1:")
    profile2 = profile_text(user2, "👤 User2:")

    # Get the message being reported, if /report is used as a reply
    reported_msg = update.message.reply_to_message
    if reported_msg:
        if reported_msg.text:
            reported_text = reported_msg.text
        elif reported_msg.caption:
            reported_text = reported_msg.caption
        else:
            reported_text = "(Message type not supported for reporting.)"
        reported_by_user = reported_msg.from_user.id if reported_msg.from_user else "Unknown"
        reported_msg_details = (
            f"Reported Message (by user {reported_by_user}):\n"
            f"{reported_text}\n"
        )
    else:
        reported_msg_details = "(No specific message was reported. User used /report without replying to a message.)"

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
    report_msg = (
        f"🚨 User {user_id} reported user {other_id} in room {room_id}.\n"
        f"{reported_msg_details}\n\n"
        f"{profile1}\n\n{profile2}\n"
    )
    await context.bot.send_message(chat_id=admin_group, text=report_msg)

    await update.message.reply_text("Report sent to admin. Thank you for helping keep our platform safe.")
