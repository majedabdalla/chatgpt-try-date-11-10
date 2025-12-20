"""
Helper functions to avoid circular imports
"""
import logging

logger = logging.getLogger(__name__)

async def update_user_profile_info(user_id, context):
    """
    Helper function to update user's profile info from Telegram
    Updates: username, name, and profile photos (limited to 10)
    Returns: dict with old and new info for comparison
    """
    try:
        from db import get_user, update_user
        
        existing = await get_user(user_id)
        if not existing:
            return None
        
        try:
            chat_member = await context.bot.get_chat(user_id)
            new_username = chat_member.username if chat_member.username else ""
            new_name = chat_member.full_name or chat_member.first_name or ""
        except Exception as e:
            logger.warning(f"Could not get chat info for user {user_id}: {e}")
            return None
        
        photos = []
        try:
            user_photos = await context.bot.get_user_profile_photos(user_id, limit=10)
            for photo in user_photos.photos[:10]:
                photos.append(photo[-1].file_id)
            logger.info(f"Fetched {len(photos)} profile photos for user {user_id}")
        except Exception as e:
            logger.warning(f"Could not get profile photos for user {user_id}: {e}")
        
        updates = {}
        old_info = {
            "username": existing.get("username", ""),
            "name": existing.get("name", ""),
            "profile_photos": existing.get("profile_photos", [])
        }
        
        if new_username != existing.get("username", ""):
            updates["username"] = new_username
        
        if new_name != existing.get("name", ""):
            updates["name"] = new_name
        
        if photos and photos != existing.get("profile_photos", []):
            updates["profile_photos"] = photos
        
        if updates:
            await update_user(user_id, updates)
            logger.info(f"Updated profile info for user {user_id}: {list(updates.keys())}")
        
        return {
            "updated": bool(updates),
            "old": old_info,
            "new": {
                "username": new_username,
                "name": new_name,
                "profile_photos": photos
            }
        }
    except Exception as e:
        logger.error(f"Error updating user profile info: {e}")
        return None

async def safe_send_message(bot, user_id, text, **kwargs):
    """
    Helper to safely send a message to a user
    Returns True if successful, False otherwise
    """
    try:
        await bot.send_message(chat_id=user_id, text=text, **kwargs)
        return True
    except Exception as e:
        logger.warning(f"Could not send message to user {user_id}: {e}")
        return False

async def safe_send_photo(bot, user_id, photo, **kwargs):
    """
    Helper to safely send a photo to a user
    Returns True if successful, False otherwise
    """
    try:
        await bot.send_photo(chat_id=user_id, photo=photo, **kwargs)
        return True
    except Exception as e:
        logger.warning(f"Could not send photo to user {user_id}: {e}")
        return False

async def get_user_display_name(user):
    """
    Get a user's display name (username or name)
    """
    if user.get("username"):
        return f"@{user['username']}"
    elif user.get("name"):
        return user["name"]
    else:
        return f"User {user['user_id']}"

def sanitize_text(text, max_length=4096):
    """
    Sanitize and truncate text for Telegram
    Telegram has a 4096 character limit for messages
    """
    if not text:
        return ""
    
    text = text.replace('\x00', '')
    
    if len(text) > max_length:
        text = text[:max_length-3] + "..."
    
    return text
