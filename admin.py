from db import db, update_user, get_user, get_user_by_username, get_room, update_room, get_chat_history, insert_blocked_word, remove_blocked_word, get_blocked_words
from models import default_report
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

async def approve_premium(user_id, duration_days=90):
    expiry = (datetime.utcnow() + timedelta(days=duration_days)).isoformat()
    await update_user(user_id, {"is_premium": True, "premium_expiry": expiry})
    return expiry

async def downgrade_expired_premium(bot=None):
    """
    FIX #2: Downgrade expired premium users and notify them
    """
    now = datetime.utcnow().isoformat()
    notified_count = 0
    
    async for user in db.users.find({"is_premium": True, "premium_expiry": {"$lt": now}}):
        user_id = user["user_id"]
        await update_user(user_id, {"is_premium": False})
        
        # Notify user about expiry
        if bot:
            try:
                lang = user.get("language", "en")
                from bot import load_locale
                locale = load_locale(lang)
                expiry_msg = (
                    f"⏰ {locale.get('premium_expired', 'Your premium membership has expired.')}\n\n"
                    f"💎 {locale.get('premium_expired_info', 'To continue enjoying premium features, please renew your subscription.')}\n\n"
                    f"Use /upgrade to renew your premium membership!"
                )
                await bot.send_message(chat_id=user_id, text=expiry_msg)
                notified_count += 1
            except Exception as e:
                logger.warning(f"Could not notify user {user_id} about premium expiry: {e}")
    
    if notified_count > 0:
        logger.info(f"Notified {notified_count} users about premium expiry")

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

async def send_global_announcement(bot, text):
    """
    FIX #3: Send announcement to all users
    Returns tuple: (success_count, fail_count, total_users)
    """
    success_count = 0
    fail_count = 0
    total_users = 0
    
    async for user in db.users.find({}):
        total_users += 1
        user_id = user["user_id"]
        try:
            await bot.send_message(chat_id=user_id, text=text, parse_mode='Markdown')
            success_count += 1
        except Exception as e:
            fail_count += 1
            logger.warning(f"Failed to send announcement to user {user_id}: {e}")
    
    return success_count, fail_count, total_users

async def add_blocked_word(word):
    await insert_blocked_word(word)

async def remove_blocked_word(word):
    await remove_blocked_word(word)

async def get_stats():
    """
    FIX #4: Get detailed stats
    """
    users_count = await db.users.count_documents({})
    premium_count = await db.users.count_documents({"is_premium": True})
    blocked_count = await db.users.count_documents({"blocked": True})
    rooms_count = await db.rooms.count_documents({})
    active_rooms = await db.rooms.count_documents({"active": True})
    reports_count = await db.reports.count_documents({})
    unreviewed_reports = await db.reports.count_documents({"reviewed": False})
    blocked_words_count = await db.blocked_words.count_documents({})
    
    # Get language distribution
    lang_pipeline = [
        {"$group": {"_id": "$language", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]
    lang_dist = []
    async for doc in db.users.aggregate(lang_pipeline):
        lang_dist.append(f"{doc['_id']}: {doc['count']}")
    
    # Get gender distribution
    gender_pipeline = [
        {"$group": {"_id": "$gender", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]
    gender_dist = []
    async for doc in db.users.aggregate(gender_pipeline):
        if doc['_id']:  # Skip empty gender
            gender_dist.append(f"{doc['_id']}: {doc['count']}")
    
    # Get region distribution
    region_pipeline = [
        {"$group": {"_id": "$region", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10}
    ]
    region_dist = []
    async for doc in db.users.aggregate(region_pipeline):
        if doc['_id']:  # Skip empty region
            region_dist.append(f"{doc['_id']}: {doc['count']}")
    
    return {
        "users": users_count,
        "premium_users": premium_count,
        "blocked_users": blocked_count,
        "rooms": rooms_count,
        "active_rooms": active_rooms,
        "reports": reports_count,
        "unreviewed_reports": unreviewed_reports,
        "blocked_words": blocked_words_count,
        "language_distribution": lang_dist,
        "gender_distribution": gender_dist,
        "region_distribution": region_dist
    }
