import os
import logging
from motor.motor_asyncio import AsyncIOMotorClient
from models import default_user
from datetime import datetime

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
logger = logging.getLogger(__name__)

try:
    client = AsyncIOMotorClient(
        MONGODB_URI,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=10000,
        socketTimeoutMS=10000,
        maxPoolSize=50,
        minPoolSize=10
    )
except Exception as e:
    logger.error(f"MongoDB client initialization failed: {e}")

db = client["anonindochat"]

async def test_connection():
    """Test MongoDB connection - call this at startup"""
    try:
        await client.server_info()
        logger.info("✅ MongoDB connection successful")
        return True
    except Exception as e:
        logger.error(f"❌ MongoDB connection failed: {e}")
        return False

async def create_indexes():
    """Create database indexes for performance"""
    try:
        await db.users.create_index("user_id", unique=True)
        await db.users.create_index("username")
        await db.users.create_index("is_premium")
        await db.users.create_index("is_online")
        await db.rooms.create_index("room_id", unique=True)
        await db.rooms.create_index("active")
        await db.premium_queue.create_index("user_id", unique=True)
        await db.user_rooms.create_index("user_id", unique=True)
        await db.user_rooms.create_index("room_id")
        await db.blocked_words.create_index("word", unique=True)
        logger.info("✅ Database indexes created")
    except Exception as e:
        logger.warning(f"Index creation warning: {e}")

async def get_user(user_id):
    user = await db.users.find_one({"user_id": user_id})
    username = ""
    phone_number = ""
    full_name = ""
    first_name = ""
    if user:
        username = user.get('username', '')
        phone_number = user.get('phone_number', '')
        full_name = user.get('name', '')
        first_name = user.get('first_name', '')
        defaults = default_user(type('TelegramUser', (), {
            'id': user_id,
            'username': username,
            'phone_number': phone_number,
            'full_name': full_name,
            'first_name': first_name
        })())
        for k, v in defaults.items():
            if k not in user:
                user[k] = v
    return user

async def get_user_by_username(username):
    user = await db.users.find_one({"username": username})
    user_id = user['user_id'] if user else 0
    phone_number = user.get('phone_number', '') if user else ''
    full_name = user.get('name', '') if user else ''
    first_name = user.get('first_name', '') if user else ''
    defaults = default_user(type('TelegramUser', (), {
        'id': user_id,
        'username': username,
        'phone_number': phone_number,
        'full_name': full_name,
        'first_name': first_name
    })())
    if user:
        for k, v in defaults.items():
            if k not in user:
                user[k] = v
    return user

async def update_user(user_id, updates):
    doc = await db.users.find_one({"user_id": user_id})
    username = updates.get('username', '')
    phone_number = updates.get('phone_number', '')
    full_name = updates.get('name', '')
    first_name = updates.get('first_name', '')
    if not doc:
        temp_user = type('TelegramUser', (), {
            'id': user_id,
            'username': username,
            'phone_number': phone_number,
            'full_name': full_name,
            'first_name': first_name
        })()
        full_doc = default_user(temp_user)
        full_doc.update(updates)
        await db.users.update_one({"user_id": user_id}, {"$set": full_doc}, upsert=True)
    else:
        doc.update(updates)
        defaults = default_user(type('TelegramUser', (), {
            'id': user_id,
            'username': doc.get('username', ''),
            'phone_number': doc.get('phone_number', ''),
            'full_name': doc.get('name', ''),
            'first_name': doc.get('first_name', '')
        })())
        for k, v in defaults.items():
            if k not in doc:
                doc[k] = v
        await db.users.update_one({"user_id": user_id}, {"$set": doc}, upsert=True)

# ===== ROOM MAPPING FUNCTIONS (DATABASE-BACKED) =====

async def set_user_room(user_id, room_id):
    """Store user's current room in database - PERSISTENT across restarts"""
    await db.user_rooms.update_one(
        {"user_id": user_id},
        {"$set": {
            "room_id": room_id, 
            "updated_at": datetime.utcnow()
        }},
        upsert=True
    )
    logger.info(f"Set user {user_id} to room {room_id}")

async def get_user_room(user_id):
    """Get user's current room from database"""
    doc = await db.user_rooms.find_one({"user_id": user_id})
    return doc["room_id"] if doc else None

async def remove_user_room(user_id):
    """Remove user from room mapping"""
    result = await db.user_rooms.delete_one({"user_id": user_id})
    if result.deleted_count > 0:
        logger.info(f"Removed user {user_id} from room mapping")

async def get_room_users(room_id):
    """Get all users in a specific room"""
    cursor = db.user_rooms.find({"room_id": room_id})
    users = []
    async for doc in cursor:
        users.append(doc["user_id"])
    return users

async def clear_room_mappings(room_id):
    """Remove all users from a specific room"""
    result = await db.user_rooms.delete_many({"room_id": room_id})
    logger.info(f"Cleared {result.deleted_count} users from room {room_id}")

async def insert_room(room):
    await db.rooms.insert_one(room)

async def get_room(room_id):
    return await db.rooms.find_one({"room_id": room_id})

async def update_room(room_id, updates):
    await db.rooms.update_one({"room_id": room_id}, {"$set": updates})

async def delete_room(room_id):
    await db.rooms.delete_one({"room_id": room_id})

async def log_chat(room_id, msg):
    await db.chatlogs.insert_one({"room_id": room_id, **msg})

async def get_chat_history(room_id):
    cursor = db.chatlogs.find({"room_id": room_id})
    return [doc async for doc in cursor]

async def delete_chat_logs(room_id):
    """Delete all chat logs for a room"""
    result = await db.chatlogs.delete_many({"room_id": room_id})
    return result.deleted_count

async def insert_report(report):
    await db.reports.insert_one(report)

async def insert_blocked_word(word):
    await db.blocked_words.update_one(
        {"word": word.lower()}, 
        {"$set": {"word": word.lower()}}, 
        upsert=True
    )

async def remove_blocked_word(word):
    await db.blocked_words.delete_one({"word": word.lower()})

async def get_blocked_words():
    cursor = db.blocked_words.find({})
    return [doc["word"] async for doc in cursor]

async def mark_user_online(user_id):
    """Mark user as online"""
    await update_user(user_id, {
        "is_online": True,
        "last_active": datetime.utcnow()
    })

async def mark_user_offline(user_id):
    """Mark user as offline"""
    await update_user(user_id, {
        "is_online": False,
        "last_active": datetime.utcnow()
    })

async def mark_all_users_offline():
    """Mark all users as offline - call on bot shutdown"""
    result = await db.users.update_many(
        {},
        {"$set": {"is_online": False}}
    )
    logger.info(f"Marked {result.modified_count} users as offline")

async def cleanup_stale_rooms():
    """Clean up stale room mappings (rooms that don't exist)"""
    count = 0
    async for mapping in db.user_rooms.find({}):
        room = await get_room(mapping["room_id"])
        if not room or not room.get("active", False):
            await remove_user_room(mapping["user_id"])
            count += 1
    if count > 0:
        logger.info(f"Cleaned up {count} stale room mappings")
    return count
