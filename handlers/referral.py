"""
Referral/Affiliate Program
- Each user gets 1 day of premium for each new user they invite
- Users can share their referral link
- Track referrals and reward users automatically
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from db import get_user, update_user
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

def get_user_locale(user):
    lang = "en"
    if user:
        dbuser = user if isinstance(user, dict) else None
        if dbuser and dbuser.get("language"):
            lang = dbuser["language"]
        elif hasattr(user, "language_code"):
            lang = user.language_code or "en"
    return lang

async def generate_referral_link(user_id: int, bot_username: str) -> str:
    """Generate a unique referral link for a user"""
    return f"https://t.me/{bot_username}?start=ref_{user_id}"

async def process_referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Process referral when a new user starts the bot with a referral link
    Called from /start command
    """
    if not context.args:
        return None
    
    arg = context.args[0]
    if not arg.startswith("ref_"):
        return None
    
    try:
        referrer_id = int(arg.split("_")[1])
        new_user_id = update.effective_user.id
        
        # Don't allow self-referral
        if referrer_id == new_user_id:
            return None
        
        # Check if new user already exists
        existing_user = await get_user(new_user_id)
        if existing_user and existing_user.get("referred_by"):
            # User was already referred, don't process again
            return None
        
        # Check if referrer exists
        referrer = await get_user(referrer_id)
        if not referrer:
            return None
        
        # Mark new user as referred
        await update_user(new_user_id, {"referred_by": referrer_id})
        
        # Reward referrer with 1 day of premium
        await reward_referrer(referrer_id, referrer, context.bot)
        
        # Send notification to referrer
        from bot import load_locale
        referrer_lang = get_user_locale(referrer)
        referrer_locale = load_locale(referrer_lang)
        
        try:
            await context.bot.send_message(
                chat_id=referrer_id,
                text=f"🎉 {referrer_locale.get('referral_reward', 'Congrats! Someone joined using your referral link. You got 1 day of premium!')}"
            )
        except Exception as e:
            logger.warning(f"Could not notify referrer {referrer_id}: {e}")
        
        return referrer_id
        
    except Exception as e:
        logger.error(f"Error processing referral: {e}")
        return None

async def reward_referrer(referrer_id: int, referrer: dict, bot):
    """Give referrer 1 day of premium"""
    current_expiry = referrer.get("premium_expiry")
    
    if referrer.get("is_premium", False) and current_expiry:
        # User already has premium, extend by 1 day
        try:
            expiry_date = datetime.fromisoformat(current_expiry)
            # If expiry is in the past, start from now
            if expiry_date < datetime.utcnow():
                new_expiry = datetime.utcnow() + timedelta(days=1)
            else:
                new_expiry = expiry_date + timedelta(days=1)
            
            await update_user(referrer_id, {
                "premium_expiry": new_expiry.isoformat()
            })
        except Exception as e:
            logger.error(f"Error extending premium for referrer {referrer_id}: {e}")
            # Fallback: give 1 day from now
            new_expiry = datetime.utcnow() + timedelta(days=1)
            await update_user(referrer_id, {
                "is_premium": True,
                "premium_expiry": new_expiry.isoformat()
            })
    else:
        # User doesn't have premium, give 1 day
        new_expiry = datetime.utcnow() + timedelta(days=1)
        await update_user(referrer_id, {
            "is_premium": True,
            "premium_expiry": new_expiry.isoformat()
        })
    
    # Increment referral count
    referral_count = referrer.get("referral_count", 0) + 1
    await update_user(referrer_id, {"referral_count": referral_count})

async def show_referral_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Show user their referral link and stats
    Command: /referral or /invite
    """
    user_id = update.effective_user.id
    user = await get_user(user_id)
    
    if not user:
        await update.message.reply_text("Please complete your profile first using /start")
        return
    
    lang = get_user_locale(user)
    from bot import load_locale
    locale = load_locale(lang)
    
    # Get bot username
    bot_info = await context.bot.get_me()
    bot_username = bot_info.username
    
    # Generate referral link
    referral_link = await generate_referral_link(user_id, bot_username)
    
    # Get referral stats
    referral_count = user.get("referral_count", 0)
    
    # Calculate total premium days earned
    total_premium_days = referral_count  # 1 day per referral
    
    referral_text = (
        f"🎁 *{locale.get('referral_program', 'Referral Program')}*\n"
        f"━━━━━━━━━━━━━━━━\n\n"
        f"📊 *{locale.get('your_stats', 'Your Stats')}*\n"
        f"👥 {locale.get('referrals', 'Referrals')}: {referral_count}\n"
        f"⭐ {locale.get('premium_earned', 'Premium Days Earned')}: {total_premium_days}\n\n"
        f"🔗 *{locale.get('your_link', 'Your Referral Link')}*\n"
        f"`{referral_link}`\n\n"
        f"💡 *{locale.get('how_it_works', 'How it works')}*\n"
        f"• {locale.get('referral_step1', 'Share your link with friends')}\n"
        f"• {locale.get('referral_step2', 'They join using your link')}\n"
        f"• {locale.get('referral_step3', 'You get 1 day of premium for each referral!')}\n\n"
        f"🎉 {locale.get('referral_unlimited', 'Unlimited referrals = Unlimited premium!')}"
    )
    
    # Create share button
    share_text = locale.get('referral_share_text', f'Join me on AnonIndoChat! 🎉')
    share_url = f"https://t.me/share/url?url={referral_link}&text={share_text}"
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"📤 {locale.get('share_link', 'Share Link')}", url=share_url)]
    ])
    
    await update.message.reply_text(
        referral_text,
        parse_mode='Markdown',
        reply_markup=kb
    )

async def admin_check_referrals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Admin command to check referral stats
    Usage: /checkreferrals [user_id]
    """
    from handlers.admincmds import _is_admin, _lookup_user
    
    if not _is_admin(update, context):
        await update.message.reply_text("Unauthorized.")
        return
    
    if not context.args:
        # Show top referrers
        from db import db
        pipeline = [
            {"$match": {"referral_count": {"$exists": True, "$gt": 0}}},
            {"$sort": {"referral_count": -1}},
            {"$limit": 10}
        ]
        
        top_referrers = []
        async for user in db.users.aggregate(pipeline):
            top_referrers.append(
                f"👤 {user['user_id']} (@{user.get('username', 'N/A')}): {user.get('referral_count', 0)} referrals"
            )
        
        if top_referrers:
            msg = "🏆 *Top Referrers*\n\n" + "\n".join(top_referrers)
        else:
            msg = "No referrals yet."
        
        await update.message.reply_text(msg, parse_mode='Markdown')
    else:
        # Check specific user
        identifier = context.args[0]
        user = await _lookup_user(identifier)
        
        if not user:
            await update.message.reply_text("User not found.")
            return
        
        referral_count = user.get("referral_count", 0)
        referred_by = user.get("referred_by", None)
        
        msg = (
            f"👤 *Referral Info for {user['user_id']}*\n\n"
            f"📊 Referrals made: {referral_count}\n"
            f"🔗 Referred by: {referred_by if referred_by else 'None'}"
        )
        
        await update.message.reply_text(msg, parse_mode='Markdown')
