import os
import logging
from motor.motor_asyncio import AsyncIOMotorClient
from models import default_user

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
try:
    client = AsyncIOMotorClient(
        MONGODB_URI,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=10000,
        socketTimeoutMS=10000
    )
    # Test connection
    import asyncio
    asyncio.get_event_loop().run_until_complete(client.server_info())
except Exception as e:
    logging.error(f"MongoDB connection failed: {e}")
db = client["anonindochat"]

async def get_user(user_id):
    user = await db.users.find_one({"user_id": user_id})
    # Always provide all expected attributes to default_user
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
    # Always provide all expected attributes to default_user
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

# ----- PATCH: Add room and utility functions -----

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
    # Returns list of chat logs for a room
    cursor = db.chatlogs.find({"room_id": room_id})
    return [doc async for doc in cursor]

async def insert_report(report):
    await db.reports.insert_one(report)

async def insert_blocked_word(word):
    await db.blocked_words.update_one({"word": word.lower()}, {"$set": {"word": word.lower()}}, upsert=True)

async def remove_blocked_word(word):
    await db.blocked_words.delete_one({"word": word.lower()})

async def get_blocked_words():
    cursor = db.blocked_words.find({})
    return [doc["word"] async for doc in cursor]
