from telegram import Update
from admin import (block_user, unblock_user, send_admin_message, get_stats, 
                   add_blocked_word, remove_blocked_word, approve_premium, send_global_announcement)
from db import get_user, get_user_by_username, get_room, get_chat_history, update_user, db
from datetime import datetime, timedelta
from rooms import create_room, close_room
import json
from io import BytesIO
import asyncio

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

async def _copy_message_to_user(context, to_chat_id, from_message):
    """
    Helper function to copy any type of message to a user
    Returns True if successful, False otherwise
    """
    try:
        await from_message.copy(chat_id=to_chat_id)
        return True
    except Exception as e:
        return False

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
    """
    Enhanced /message command that supports all message types
    
    Usage method 1: /message <user_id or @username> <text>
    Usage method 2: Reply to any message with /message <user_id or @username>
    """
    if not _is_admin(update, context):
        await update.message.reply_text("Unauthorized.")
        return
    
    if not context.args:
        await update.message.reply_text(
            "Usage:\n"
            "1. /message <user_id or @username> <text>\n"
            "2. Reply to any message with: /message <user_id or @username>"
        )
        return
    
    identifier = context.args[0]
    user = await _lookup_user(identifier)
    
    if not user:
        await update.message.reply_text("User not found.")
        return
    
    user_id = user["user_id"]
    
    # Check if this is a reply to a message
    if update.message.reply_to_message:
        # Method 2: Copy the replied message
        success = await _copy_message_to_user(context, user_id, update.message.reply_to_message)
        
        if success:
            await update.message.reply_text(f"✅ Message sent to user {user_id}.")
        else:
            await update.message.reply_text(f"❌ Failed to send message to user {user_id}.")
    else:
        # Method 1: Traditional text message
        if len(context.args) < 2:
            await update.message.reply_text("Please provide a message text or reply to a message.")
            return
        
        text = " ".join(context.args[1:])
        success = await send_admin_message(context.bot, user_id, text)
        
        if success:
            await update.message.reply_text(f"✅ Message sent to user {user_id}.")
        else:
            await update.message.reply_text(f"❌ Failed to send message to user {user_id}.")

async def admin_ad(update: Update, context):
    """
    Enhanced /ad command that supports all message types with rate limiting
    
    Usage method 1: /ad <message text>
    Usage method 2: Reply to any message with /ad
    """
    if not _is_admin(update, context):
        await update.message.reply_text("Unauthorized.")
        return
    
    # Check if this is a reply to a message
    if update.message.reply_to_message:
        # Method 2: Broadcast the replied message to all users WITH RATE LIMITING
        await update.message.reply_text(
            "📤 Broadcasting message to all users...\n⏳ Please wait..."
        )
        
        success_count = 0
        fail_count = 0
        total_users = 0
        
        async for user in db.users.find({}):
            total_users += 1
            user_id = user["user_id"]
            
            # CRITICAL FIX: Add delay between messages to prevent API overload and room disconnections
            await asyncio.sleep(0.05)  # 50ms delay between each message
            
            # Try to copy the message to each user
            try:
                await update.message.reply_to_message.copy(chat_id=user_id)
                success_count += 1
            except Exception as e:
                fail_count += 1
        
        # Report results
        result_msg = (
            f"✅ *Broadcast Complete*\n\n"
            f"Total Users: {total_users}\n"
            f"✅ Successfully sent: {success_count}\n"
            f"❌ Failed: {fail_count}\n"
            f"Success Rate: {(success_count/total_users*100):.1f}%"
        )
        await update.message.reply_text(result_msg, parse_mode='Markdown')
        
    else:
        # Method 1: Traditional text announcement
        if not context.args:
            await update.message.reply_text(
                "📢 *Global Announcement*\n\n"
                "Usage:\n"
                "1. `/ad <message text>` - Send text announcement\n"
                "2. Reply to any message with `/ad` - Broadcast that message\n\n"
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
        
        # Send to all users (this already has rate limiting in admin.py)
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

async def admin_linkusers(update: Update, context):
    """
    NEW FEATURE: Secretly link two users together in a room
    The users will think they were matched normally - they won't know admin linked them
    
    Usage: /linkusers <user1_id or @username1> <user2_id or @username2>
    """
    if not _is_admin(update, context):
        await update.message.reply_text("Unauthorized.")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text(
            "Usage: /linkusers <user1_id or @username1> <user2_id or @username2>\n\n"
            "Example: /linkusers 123456789 @johndoe\n"
            "This will secretly match the two users together."
        )
        return
    
    identifier1 = context.args[0]
    identifier2 = context.args[1]
    
    # Lookup both users
    user1 = await _lookup_user(identifier1)
    user2 = await _lookup_user(identifier2)
    
    if not user1:
        await update.message.reply_text(f"❌ User 1 not found: {identifier1}")
        return
    
    if not user2:
        await update.message.reply_text(f"❌ User 2 not found: {identifier2}")
        return
    
    user1_id = user1["user_id"]
    user2_id = user2["user_id"]
    
    # Check if users are the same
    if user1_id == user2_id:
        await update.message.reply_text("❌ Cannot link a user with themselves.")
        return
    
    # Check if either user is already in a room
    user_room_map = context.bot_data.get("user_room_map", {})
    if user1_id in user_room_map:
        await update.message.reply_text(f"❌ User {user1_id} is already in a chat room.")
        return
    
    if user2_id in user_room_map:
        await update.message.reply_text(f"❌ User {user2_id} is already in a chat room.")
        return
    
    # Remove users from waiting pool/queue if they're there
    from rooms import users_online, remove_from_pool
    from handlers.match import remove_from_premium_queue
    
    if user1_id in users_online:
        remove_from_pool(user1_id)
    if user2_id in users_online:
        remove_from_pool(user2_id)
    
    # Remove from premium queue if present
    await remove_from_premium_queue(user1_id)
    await remove_from_premium_queue(user2_id)
    
    # Create room between the two users
    room_id = await create_room(user1_id, user2_id)
    
    # Set room mapping
    if "user_room_map" not in context.bot_data:
        context.bot_data["user_room_map"] = {}
    context.bot_data["user_room_map"][user1_id] = room_id
    context.bot_data["user_room_map"][user2_id] = room_id
    
    # Set in application user_data if available
    if hasattr(context, "application"):
        context.application.user_data[user1_id]["room_id"] = room_id
        context.application.user_data[user2_id]["room_id"] = room_id
    
    # Get user locales
    from bot import load_locale
    
    def get_user_locale(user):
        lang = "en"
        if user:
            dbuser = user if isinstance(user, dict) else None
            if dbuser and dbuser.get("language"):
                lang = dbuser["language"]
        return lang
    
    user1_lang = get_user_locale(user1)
    user2_lang = get_user_locale(user2)
    
    locale1 = load_locale(user1_lang)
    locale2 = load_locale(user2_lang)
    
    # Notify both users as if they were matched normally
    try:
        await context.bot.send_message(
            chat_id=user1_id,
            text=f"🎉 {locale1.get('match_found', 'Match found! Say hi to your partner.')}"
        )
    except Exception as e:
        await update.message.reply_text(f"⚠️ Could not notify user {user1_id}: {e}")
    
    try:
        await context.bot.send_message(
            chat_id=user2_id,
            text=f"🎉 {locale2.get('match_found', 'Match found! Say hi to your partner.')}"
        )
    except Exception as e:
        await update.message.reply_text(f"⚠️ Could not notify user {user2_id}: {e}")
    
    # Notify admin group with room details
    admin_group = context.bot_data.get('ADMIN_GROUP_ID')
    if admin_group:
        from handlers.match import get_admin_room_meta
        try:
            room = await get_room(room_id)
            txt = f"🔗 Admin Linked Users\n" + get_admin_room_meta(room, user1_id, user2_id, [user1, user2])
            await context.bot.send_message(chat_id=admin_group, text=txt)
            
            # Send profile photos
            for u in [user1, user2]:
                for pid in u.get('profile_photos', [])[:5]:
                    try:
                        await context.bot.send_photo(chat_id=admin_group, photo=pid)
                    except:
                        pass
        except Exception as e:
            pass
    
    # Confirm to admin
    username1 = f"@{user1.get('username')}" if user1.get('username') else f"ID:{user1_id}"
    username2 = f"@{user2.get('username')}" if user2.get('username') else f"ID:{user2_id}"
    
    await update.message.reply_text(
        f"✅ *Successfully linked users!*\n\n"
        f"👤 User 1: {username1} (ID: {user1_id})\n"
        f"👤 User 2: {username2} (ID: {user2_id})\n"
        f"🆔 Room ID: `{room_id}`\n\n"
        f"Both users have been notified of their match.\n"
        f"They don't know you linked them - it appears as a normal match.",
        parse_mode='Markdown'
    )

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
    
    # FIX: Display username properly - show "No username" if empty
    username_display = f"@{user.get('username')}" if user.get('username') else "No username"
    
    txt = (
        f"👤 *User Information*\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"ID: `{user['user_id']}`\n"
        f"Username: {username_display}\n"
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
                # FIX: Display username properly
                username_display = f"@{u.get('username')}" if u.get('username') else "No username"
                
                txt = (
                    f"👤 *User {uid}*\n"
                    f"Username: {username_display}\n"
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
