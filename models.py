from datetime import datetime

def default_user(user, language="en"):
    return {
        "user_id": user.id,
        "username": user.username or "",
        "phone_number": getattr(user, "phone_number", ""),
        "language": language,
        "name": getattr(user, "full_name", "") or getattr(user, "first_name", ""),
        "gender": "",
        "region": "",
        "country": "",
        "is_premium": False,
        "premium_expiry": None,
        "blocked": False,
        "matching_preferences": {},
        "profile_photos": [],
        "created_at": datetime.utcnow().isoformat(),
        "referred_by": None,  # NEW: User ID of who referred this user
        "referral_count": 0   # NEW: Number of users this person referred
    }

def default_room(room_id, user1, user2):
    return {
        "room_id": room_id,
        "users": [user1, user2],
        "created_at": datetime.utcnow().timestamp(),
        "messages": [],
        "active": True,
        "reports": []
    }

def default_report(room_id, reporter_id, reported_id, chat_history):
    return {
        "room_id": room_id,
        "reporter_id": reporter_id,
        "reported_id": reported_id,
        "chat_history": chat_history,
        "created_at": datetime.utcnow().isoformat(),
        "reviewed": False
    }
