"""
Helper functions to avoid circular imports
"""
import logging

logger = logging.getLogger(__name__)

async def update_user_profile_info(user_id, context):
    """
    Helper function to update user's profile info from Telegram
    Updates: username, name, and profile photos
    Returns: dict with old and new info for comparison
    """
    try:
        from db import get_user, update_user
        
        # Get current user data from database
        existing = await get_user(user_id)
        if not existing:
            return None
        
        # Get fresh data from Telegram
        try:
            chat_member = await context.bot.get_chat(user_id)
            new_username = chat_member.username if chat_member.username else ""
            new_name = chat_member.full_name or chat_member.first_name or ""
        except Exception as e:
            logger.warning(f"Could not get chat info for user {user_id}: {e}")
            return None
        
        # Fetch profile photos
        photos = []
        try:
            for offset in (0, 100):
                user_photos = await context.bot.get_user_profile_photos(user_id, offset=offset, limit=100)
                for photo in user_photos.photos:
                    photos.append(photo[-1].file_id)
                if len(user_photos.photos) < 100:
                    break
        except Exception as e:
            logger.warning(f"Could not get profile photos for user {user_id}: {e}")
        
        # Prepare updates
        updates = {}
        old_info = {
            "username": existing.get("username", ""),
            "name": existing.get("name", ""),
            "profile_photos": existing.get("profile_photos", [])
        }
        
        # Use empty string instead of "none" for users without username
        if new_username != existing.get("username", ""):
            updates["username"] = new_username
        
        if new_name != existing.get("name", ""):
            updates["name"] = new_name
        
        if photos and photos != existing.get("profile_photos", []):
            updates["profile_photos"] = photos
        
        # Apply updates if any
        if updates:
            await update_user(user_id, updates)
            logger.info(f"Updated profile info for user {user_id}")
        
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
