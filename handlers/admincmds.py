from telegram import Update
from admin import (block_user, unblock_user, send_admin_message, get_stats, 
                   add_blocked_word, remove_blocked_word, approve_premium, send_global_announcement)
from db import get_user, get_user_by_username, get_room, get_chat_history, update_user, db
from datetime import datetime, timedelta
from rooms import create_room, close_room
import json
from io import BytesIO

def _is_admin(update, context):
    ADMIN_ID = context.bot_data.get("ADMIN_ID")
    user_id = update.effective_user.id if update.effective_user else None
    return user_id == ADMIN_ID

async def _lookup_user(identifier):
    """
    Tries to resolve identifier (int id or @username/username) to user dict.
    Always returns user dict with valid user_id or None.
    """
    try:
        uid = int(identifier)
        user = await get_user(uid)
        if user:
            return user
    except Exception:
        pass
    uname = identifier
    if uname.startswith("@"):
        uname = uname[1:]
    user = await get_user_by_username(uname)
    if user:
        return user
    return None

async def admin_block(update: Update, context):
    if not _is_admin(update, context):
        await update.message.reply_text("Unauthorized.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /block <user_id or @username>")
        return
    identifier = context.args[0]
    user = await _lookup_user(identifier)
    if not user:
        await update.message.reply_text("User not found.")
        return
    await block_user(user["user_id"])
    await update.message.reply_text(f"✅ User {user['user_id']} blocked.")

async def admin_unblock(update: Update, context):
    if not _is_admin(update, context):
        await update.message.reply_text("Unauthorized.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /unblock <user_id or @username>")
        return
    identifier = context.args[0]
    user = await _lookup_user(identifier)
    if not user:
        await update.message.reply_text("User not found.")
        return
    await unblock_user(user["user_id"])
    await update.message.reply_text(f"✅ User {user['user_id']} unblocked.")

async def admin_setpremium(update: Update, context):
    if not _is_admin(update, context):
        await update.message.reply_text("Unauthorized.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /setpremium <user_id or @username> [days]")
        return
    identifier = context.args[0]
    duration = 90  # Default 90 days
    if len(context.args) > 1:
        try:
            duration = int(context.args[1])
        except:
            pass
    
    user = await _lookup_user(identifier)
    if not user:
        await update.message.reply_text("User not found.")
        return
    expiry = await approve_premium(user["user_id"], duration)
    await update.message.reply_text(f"✅ User {user['user_id']} promoted to premium until {expiry}")

async def admin_resetpremium(update: Update, context):
    if not _is_admin(update, context):
        await update.message.reply_text("Unauthorized.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /resetpremium <user_id or @username>")
        return
    identifier = context.args[0]
    user = await _lookup_user(identifier)
    if not user:
        await update.message.reply_text("User not found.")
        return
    await update_user(user["user_id"], {"is_premium": False, "premium_expiry": None})
    await update.message.reply_text(f"✅ User {user['user_id']} downgraded to normal user.")

async def admin_message(update: Update, context):
    if not _is_admin(update, context):
        await update.message.reply_text("Unauthorized.")
        return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /message <user_id or @username> <text>")
        return
    user_id_or_username = context.args[0]
    text = " ".join(context.args[1:])
    user = await _lookup_user(user_id_or_username)
    if not user:
        await update.message.reply_text("User not found.")
        return
    success = await send_admin_message(context.bot, user["user_id"], text)
    if success:
        await update.message.reply_text("✅ Message sent.")
    else:
        await update.message.reply_text("❌ Failed to send message.")

async def admin_ad(update: Update, context):
    """
    FIX #3: Global announcement feature
    Usage: /ad <message text>
    Supports Markdown formatting
    """
    if not _is_admin(update, context):
        await update.message.reply_text("Unauthorized.")
        return
    
    if not context.args:
        await update.message.reply_text(
            "📢 *Global Announcement*\n\n"
            "Usage: `/ad <message>`\n\n"
            "Example: `/ad 🎉 Welcome to our new features!`\n\n"
            "The message supports Markdown formatting.",
            parse_mode='Markdown'
        )
        return
    
    announcement_text = " ".join(context.args)
    
    # Add header to announcement
    full_announcement = f"📢 *Announcement from Admin*\n\n{announcement_text}"
    
    # Confirm before sending
    await update.message.reply_text(
        f"📤 Sending announcement to all users:\n\n{full_announcement}\n\n⏳ Please wait...",
        parse_mode='Markdown'
    )
    
    # Send to all users
    success, failed, total = await send_global_announcement(context.bot, full_announcement)
    
    # Report results
    result_msg = (
        f"✅ *Announcement Sent*\n\n"
        f"Total Users: {total}\n"
        f"✅ Successfully sent: {success}\n"
        f"❌ Failed: {failed}\n"
        f"Success Rate: {(success/total*100):.1f}%"
    )
    await update.message.reply_text(result_msg, parse_mode='Markdown')

async def admin_adminroom(update: Update, context):
    if not _is_admin(update, context):
        await update.message.reply_text("Unauthorized.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /adminroom <user_id or @username>")
        return
    identifier = context.args[0]
    user = await _lookup_user(identifier)
    if not user:
        await update.message.reply_text("User not found.")
        return
    admin_id = context.bot_data.get("ADMIN_ID")
    room_id = await create_room(admin_id, user["user_id"])
    context.bot_data.setdefault("user_room_map", {})[admin_id] = room_id
    context.bot_data.setdefault("user_room_map", {})[user["user_id"]] = room_id
    await update.message.reply_text(f"✅ Private room with user {user['user_id']} created. Now chat as usual. Use /end to leave.")

async def admin_stats(update: Update, context):
    """
    FIX #4: Improved stats with detailed information
    """
    if not _is_admin(update, context):
        await update.message.reply_text("Unauthorized.")
        return
    
    await update.message.reply_text("📊 Generating detailed statistics... Please wait.")
    
    stats = await get_stats()
    
    # Create detailed stats message
    stats_msg = (
        f"📊 *Bot Statistics*\n"
        f"━━━━━━━━━━━━━━━━\n\n"
        f"👥 *Users*\n"
        f"  • Total: {stats['users']}\n"
        f"  • Premium: {stats['premium_users']}\n"
        f"  • Blocked: {stats['blocked_users']}\n\n"
        f"💬 *Rooms*\n"
        f"  • Total: {stats['rooms']}\n"
        f"  • Active: {stats['active_rooms']}\n\n"
        f"🚨 *Reports*\n"
        f"  • Total: {stats['reports']}\n"
        f"  • Unreviewed: {stats['unreviewed_reports']}\n\n"
        f"🚫 *Blocked Words*: {stats['blocked_words']}\n\n"
        f"🌐 *Language Distribution*\n"
    )
    
    for lang in stats['language_distribution']:
        stats_msg += f"  • {lang}\n"
    
    stats_msg += f"\n👫 *Gender Distribution*\n"
    for gender in stats['gender_distribution']:
        stats_msg += f"  • {gender}\n"
    
    stats_msg += f"\n🌍 *Top Regions*\n"
    for region in stats['region_distribution'][:5]:
        stats_msg += f"  • {region}\n"
    
    await update.message.reply_text(stats_msg, parse_mode='Markdown')
    
    # Offer to export detailed data
    await update.message.reply_text(
        "📥 *Export Options*\n\n"
        "Use these commands to export detailed data:\n"
        "• `/export users` - Export all user data\n"
        "• `/export rooms` - Export all room data\n"
        "• `/export reports` - Export all reports\n"
        "• `/export blocked` - Export blocked words",
        parse_mode='Markdown'
    )

async def admin_export(update: Update, context):
    """
    FIX #4: Export detailed data as JSON file
    Usage: /export <users|rooms|reports|blocked>
    """
    if not _is_admin(update, context):
        await update.message.reply_text("Unauthorized.")
        return
    
    if not context.args or context.args[0] not in ['users', 'rooms', 'reports', 'blocked']:
        await update.message.reply_text(
            "Usage: `/export <users|rooms|reports|blocked>`",
            parse_mode='Markdown'
        )
        return
    
    export_type = context.args[0]
    await update.message.reply_text(f"📦 Exporting {export_type} data... Please wait.")
    
    try:
        if export_type == 'users':
            cursor = db.users.find({})
            data = [doc async for doc in cursor]
            # Remove sensitive data if needed
            for user in data:
                user.pop('_id', None)
        elif export_type == 'rooms':
            cursor = db.rooms.find({})
            data = [doc async for doc in cursor]
            for room in data:
                room.pop('_id', None)
        elif export_type == 'reports':
            cursor = db.reports.find({})
            data = [doc async for doc in cursor]
            for report in data:
                report.pop('_id', None)
        elif export_type == 'blocked':
            cursor = db.blocked_words.find({})
            data = [doc async for doc in cursor]
        
        # Convert to JSON and create file
        json_data = json.dumps(data, indent=2, default=str, ensure_ascii=False)
        file = BytesIO(json_data.encode('utf-8'))
        file.name = f"{export_type}_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        
        await update.message.reply_document(
            document=file,
            filename=file.name,
            caption=f"📊 {export_type.capitalize()} data export\nTotal records: {len(data)}"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Export failed: {str(e)}")

async def admin_blockword(update: Update, context):
    if not _is_admin(update, context):
        await update.message.reply_text("Unauthorized.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /blockword <word>")
        return
    word = context.args[0]
    await add_blocked_word(word)
    await update.message.reply_text(f"✅ Blocked word '{word}' added.")

async def admin_unblockword(update: Update, context):
    if not _is_admin(update, context):
        await update.message.reply_text("Unauthorized.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /unblockword <word>")
        return
    word = context.args[0]
    await remove_blocked_word(word)
    await update.message.reply_text(f"✅ Blocked word '{word}' removed.")

async def admin_userinfo(update: Update, context):
    if not _is_admin(update, context):
        await update.message.reply_text("Unauthorized.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /userinfo <user_id or @username>")
        return
    identifier = context.args[0]
    user = await _lookup_user(identifier)
    if not user:
        await update.message.reply_text("User not found.")
        return
    
    premium_info = ""
    if user.get('is_premium', False):
        premium_info = f"Premium Expiry: {user.get('premium_expiry','N/A')}\n"
    
    txt = (
        f"👤 *User Information*\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"ID: `{user['user_id']}`\n"
        f"Username: @{user.get('username','N/A')}\n"
        f"Name: {user.get('name','N/A')}\n"
        f"Phone: {user.get('phone_number','N/A')}\n"
        f"Language: {user.get('language','en')}\n"
        f"Gender: {user.get('gender','N/A')}\n"
        f"Region: {user.get('region','N/A')}\n"
        f"Country: {user.get('country','N/A')}\n"
        f"Premium: {'✅ Yes' if user.get('is_premium', False) else '❌ No'}\n"
        f"{premium_info}"
        f"Blocked: {'✅ Yes' if user.get('blocked', False) else '❌ No'}\n"
        f"Created: {user.get('created_at','N/A')}\n"
        f"Profile Photos: {len(user.get('profile_photos',[]))}"
    )
    await update.message.reply_text(txt, parse_mode='Markdown')
    for pid in user.get('profile_photos', [])[:5]:
        await context.bot.send_photo(chat_id=update.effective_chat.id, photo=pid)

async def admin_roominfo(update: Update, context):
    if not _is_admin(update, context):
        await update.message.reply_text("Unauthorized.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /roominfo <room_id>")
        return
    room_id = context.args[0]
    room = await get_room(room_id)
    if room:
        users_info = []
        for uid in room["users"]:
            u = await get_user(uid)
            if u:
                txt = (
                    f"👤 *User {uid}*\n"
                    f"Username: @{u.get('username','N/A')}\n"
                    f"Gender: {u.get('gender','N/A')}\n"
                    f"Region: {u.get('region','N/A')}\n"
                    f"Premium: {'✅' if u.get('is_premium', False) else '❌'}"
                )
                users_info.append(txt)
                for pid in u.get('profile_photos', [])[:3]:
                    await context.bot.send_photo(chat_id=update.effective_chat.id, photo=pid)
        
        room_txt = (
            f"💬 *Room Information*\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"Room ID: `{room['room_id']}`\n"
            f"Active: {'✅ Yes' if room.get('active', False) else '❌ No'}\n"
            f"Created: {datetime.fromtimestamp(room['created_at']).strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            + "\n\n".join(users_info)
        )
        await update.message.reply_text(room_txt, parse_mode='Markdown')
    else:
        await update.message.reply_text("Room not found.")

async def admin_viewhistory(update: Update, context):
    if not _is_admin(update, context):
        await update.message.reply_text("Unauthorized.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /viewhistory <room_id>")
        return
    room_id = context.args[0]
    history = await get_chat_history(room_id)
    if history:
        # Export as file for better readability
        history_text = json.dumps(history, indent=2, default=str, ensure_ascii=False)
        file = BytesIO(history_text.encode('utf-8'))
        file.name = f"chat_history_{room_id}.json"
        
        await update.message.reply_document(
            document=file,
            filename=file.name,
            caption=f"💬 Chat history for room {room_id}\nTotal messages: {len(history)}"
        )
    else:
        await update.message.reply_text("No chat history found.")
