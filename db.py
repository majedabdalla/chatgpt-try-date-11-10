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
    if user:
        defaults = default_user(type('TelegramUser', (), {'id': user_id, 'username': user.get('username', ''), 'phone_number': user.get('phone_number', ''), 'full_name': user.get('name',''), 'first_name': user.get('name','')})())
        for k, v in defaults.items():
            if k not in user:
                user[k] = v
    return user

async def get_user_by_username(username):
    user = await db.users.find_one({"username": username})
    if user:
        defaults = default_user(type('TelegramUser', (), {'id': user['user_id'], 'username': user.get('username', ''), 'phone_number': user.get('phone_number', ''), 'full_name': user.get('name',''), 'first_name': user.get('name','')})())
        for k, v in defaults.items():
            if k not in user:
                user[k] = v
    return user

async def update_user(user_id, updates):
    doc = await db.users.find_one({"user_id": user_id})
    if not doc:
        temp_user = type('TelegramUser', (), {'id': user_id, **updates})()
        full_doc = default_user(temp_user)
        full_doc.update(updates)
        await db.users.update_one({"user_id": user_id}, {"$set": full_doc}, upsert=True)
    else:
        doc.update(updates)
        defaults = default_user(type('TelegramUser', (), {'id': user_id, 'username': doc.get('username', ''), 'phone_number': doc.get('phone_number', ''), 'full_name': doc.get('name',''), 'first_name': doc.get('name','')})())
        for k, v in defaults.items():
            if k not in doc:
                doc[k] = v
        await db.users.update_one({"user_id": user_id}, {"$set": doc}, upsert=True)

async def get_room(room_id):
    return await db.rooms.find_one({"room_id": room_id})

async def update_room(room_id, updates):
    await db.rooms.update_one({"room_id": room_id}, {"$set": updates})

async def insert_room(room_data):
    await db.rooms.insert_one(room_data)

async def delete_room(room_id):
    await db.rooms.delete_one({"room_id": room_id})

async def insert_report(report_data):
    await db.reports.insert_one(report_data)

async def insert_blocked_word(word):
    await db.blocked_words.update_one({"word": word}, {"$set": {"word": word}}, upsert=True)

async def remove_blocked_word(word):
    await db.blocked_words.delete_one({"word": word})

async def get_blocked_words():
    cursor = db.blocked_words.find({})
    return [doc["word"] async for doc in cursor]

async def log_chat(room_id, log_data):
    await db.chatlogs.insert_one({"room_id": room_id, **log_data})

async def get_chat_history(room_id):
    cursor = db.chatlogs.find({"room_id": room_id})
    return [doc async for doc in cursor]
