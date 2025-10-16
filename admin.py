from db import db, update_user, get_user, get_user_by_username, get_room, update_room, get_chat_history, insert_blocked_word, remove_blocked_word, get_blocked_words
from models import default_report
from datetime import datetime, timedelta

async def approve_premium(user_id, duration_days=90):
    expiry = (datetime.utcnow() + timedelta(days=duration_days)).isoformat()
    await update_user(user_id, {"is_premium": True, "premium_expiry": expiry})
    return expiry  # Ensure this is returned

async def downgrade_expired_premium():
    now = datetime.utcnow().isoformat()
    async for user in db.users.find({"is_premium": True, "premium_expiry": {"$lt": now}}):
        await update_user(user["user_id"], {"is_premium": False})

async def block_user(user_id):
    await update_user(user_id, {"blocked": True})

async def unblock_user(user_id):
    await update_user(user_id, {"blocked": False})

async def send_admin_message(bot, user_id_or_username, text, file=None):
    user = await get_user(user_id_or_username)
    if not user:
        user = await get_user_by_username(user_id_or_username)
    if user:
        try:
            await bot.send_message(chat_id=user["user_id"], text=text)
            if file:
                await bot.send_document(chat_id=user["user_id"], document=file)
            return True
        except Exception:
            return False
    return False

async def add_blocked_word(word):
    await insert_blocked_word(word)

async def remove_blocked_word(word):
    await remove_blocked_word(word)

async def get_stats():
    users_count = await db.users.count_documents({})
    rooms_count = await db.rooms.count_documents({})
    reports_count = await db.reports.count_documents({})
    return {
        "users": users_count, "rooms": rooms_count, "reports": reports_count
    }
