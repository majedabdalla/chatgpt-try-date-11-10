import os
from motor.motor_asyncio import AsyncIOMotorClient

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
client = AsyncIOMotorClient(MONGODB_URI)
db = client["anonindochat"]

async def get_user(user_id):
    return await db.users.find_one({"user_id": user_id})

async def get_user_by_username(username):
    return await db.users.find_one({"username": username})

async def update_user(user_id, updates):
    await db.users.update_one({"user_id": user_id}, {"$set": updates}, upsert=True)

async def get_room(room_id):
    return await db.rooms.find_one({"room_id": room_id})

async def update_room(room_id, updates):
    await db.rooms.update_one({"room_id": room_id}, {"$set": updates})

async def insert_room(room_data):
    await db.rooms.insert_one(room_data)

async def delete_room(room_id):
    # Completely deletes the room document from MongoDB
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
