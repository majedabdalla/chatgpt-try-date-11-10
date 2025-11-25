import os
import logging
import json
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler, ConversationHandler, filters
)
from db import db, get_user, update_user, get_room
from handlers.profile import (
    unified_profile_entry, profile_menu_cb, gender_cb, region_cb, country_cb,
    ASK_GENDER, ASK_REGION, ASK_COUNTRY, PROFILE_MENU
)
from handlers.premium import start_upgrade, handle_proof, admin_callback
from handlers.chat import process_message
from handlers.report import report_partner
from handlers.admincmds import (
    admin_block, admin_unblock, admin_message, admin_stats, admin_blockword, admin_unblockword,
    admin_userinfo, admin_roominfo, admin_viewhistory, admin_setpremium, admin_resetpremium, 
    admin_adminroom, admin_ad, admin_export
)
from handlers.match import (
    find_command, search_conv, end_command, next_command, open_filter_menu,
    menu_callback_handler, select_filter_cb, stop_search_callback,
    remove_from_premium_queue, create_room, get_admin_room_meta, set_users_room_map
)
from handlers.forward import forward_to_admin
from handlers.referral import show_referral_info, process_referral, admin_check_referrals
from admin import downgrade_expired_premium
from handlers.message_router import route_message
from rooms import users_online

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
ADMIN_GROUP_ID = int(os.getenv("ADMIN_GROUP_ID"))
LOCALE_DIR = os.path.join(os.path.dirname(__file__), "locales")

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

LANGS = {
    "en": "🇬🇧 English",
    "ar": "🇸🇦 العربية", 
    "hi": "🇮🇳 हिंदी",
    "id": "🇮🇩 Indonesia"
}

def load_locale(lang):
    path = os.path.join(LOCALE_DIR, f"{lang}.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def get_user_locale(user):
    lang = "en"
    if user:
        dbuser = user if isinstance(user, dict) else None
        if dbuser and dbuser.get("language"):
            lang = dbuser["language"]
        elif hasattr(user, "language_code"):
            lang = user.language_code or "en"
    return lang

def make_inline_kb(rows, lang):
    """rows: list of [("text_key", callback_data)]"""
    locale = load_locale(lang)
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(locale.get(text_key, text_key), callback_data=cb)] for text_key, cb in rows]
    )

async def reply_translated(update, context, key, **kwargs):
    user = update.effective_user
    lang = get_user_locale(await get_user(user.id))
    locale = load_locale(lang)
    msg = locale.get(key, key)
    if kwargs:
        msg = msg.format(**kwargs)
    await update.message.reply_text(msg)

async def start(update: Update, context):
    # Process referral if present
    await process_referral(update, context)
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(locale, callback_data=f"lang_{code}")]
        for code, locale in LANGS.items()
    ])
    welcome_text = (
        "🎉 *Welcome to AnonIndoChat!*\n\n"
        "👋 Your friendly anonymous chat platform to meet new people from around the world!\n\n"
        "🌍 *Choose your language to get started:*"
    )
    await update.message.reply_text(
        welcome_text,
        reply_markup=kb,
        parse_mode='Markdown'
    )
    context.user_data.pop("last_menu_message_id", None)

async def language_select_callback(update: Update, context):
    query = update.callback_query
    await query.answer()
    lang = query.data.split("_", 1)[1]
    
    # FIX: Capture username and name when language is selected
    await update_user(query.from_user.id, {
        "language": lang,
        "username": query.from_user.username or "",
        "name": query.from_user.full_name or query.from_user.first_name or ""
    })
    
    locale = load_locale(lang)
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"👤 {locale.get('profile', 'Profile')}", callback_data="menu_profile")],
        [InlineKeyboardButton(f"🔍 {locale.get('find', 'Find Partner')}", callback_data="menu_find")],
        [InlineKeyboardButton(f"🔎 {locale.get('search', 'Advanced Search')}", callback_data="menu_search")],
        [InlineKeyboardButton(f"⚙️ {locale.get('filters', 'Filter Settings')}", callback_data="menu_filter")],
        [InlineKeyboardButton(f"🎁 {locale.get('referral_program', 'Referral Program')}", callback_data="menu_referral")],
        [InlineKeyboardButton(f"⭐ {locale.get('upgrade', 'Upgrade to Premium')}", callback_data="menu_upgrade")]
    ])
    
    await show_main_menu(update, context, f"🏠 {locale.get('main_menu', 'Main Menu:')}", kb)
    user = await get_user(query.from_user.id)
    if not user:
        await unified_profile_entry(update, context)

async def show_main_menu(update, context, menu_text=None, reply_markup=None):
    """Unified main menu display/edit; only one menu at a time."""
    message_id = context.user_data.get("last_menu_message_id")
    chat_id = update.effective_chat.id
    if not menu_text:
        user = await get_user(update.effective_user.id)
        lang = get_user_locale(user)
        locale = load_locale(lang)
        menu_text = f"🏠 {locale.get('main_menu', 'Main Menu:')}"
        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"👤 {locale.get('profile', 'Profile')}", callback_data="menu_profile")],
            [InlineKeyboardButton(f"🔍 {locale.get('find', 'Find Partner')}", callback_data="menu_find")],
            [InlineKeyboardButton(f"🔎 {locale.get('search', 'Advanced Search')}", callback_data="menu_search")],
            [InlineKeyboardButton(f"⚙️ {locale.get('filters', 'Filter Settings')}", callback_data="menu_filter")],
            [InlineKeyboardButton(f"🎁 {locale.get('referral_program', 'Referral Program')}", callback_data="menu_referral")],
            [InlineKeyboardButton(f"⭐ {locale.get('upgrade', 'Upgrade to Premium')}", callback_data="menu_upgrade")]
        ])
    try:
        if message_id:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=menu_text,
                reply_markup=reply_markup
            )
        else:
            sent = await update.effective_message.reply_text(menu_text, reply_markup=reply_markup)
            context.user_data["last_menu_message_id"] = sent.message_id
            return
    except Exception:
        sent = await update.effective_message.reply_text(menu_text, reply_markup=reply_markup)
        context.user_data["last_menu_message_id"] = sent.message_id
        return
    context.user_data["last_menu_message_id"] = message_id

def is_true_admin(update: Update):
    user_id = update.effective_user.id
    return user_id == ADMIN_ID

async def main_menu(update: Update, context):
    await show_main_menu(update, context)

async def referral_menu_callback(update: Update, context):
    """Handle the referral button click from main menu"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user = await get_user(user_id)
    
    if not user:
        await query.edit_message_text("Please complete your profile first using /start")
        return
    
    lang = get_user_locale(user)
    locale = load_locale(lang)
    
    # Get bot username
    bot_info = await context.bot.get_me()
    bot_username = bot_info.username
    
    # Generate referral link
    from handlers.referral import generate_referral_link
    referral_link = await generate_referral_link(user_id, bot_username)
    
    # Get referral stats
    referral_count = user.get("referral_count", 0)
    total_premium_days = referral_count
    
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
    
    # Create share button and back button
    share_text = locale.get('referral_share_text', f'Join me on AnonIndoChat! 🎉')
    share_url = f"https://t.me/share/url?url={referral_link}&text={share_text}"
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"📤 {locale.get('share_link', 'Share Link')}", url=share_url)],
        [InlineKeyboardButton(f"🔙 {locale.get('menu_back', 'Back to Menu')}", callback_data="menu_back")]
    ])
    
    await query.edit_message_text(
        referral_text,
        parse_mode='Markdown',
        reply_markup=kb
    )

async def check_premium_queue_job(context):
    """
    Background job to check premium queue for matches
    Runs every 45 seconds to balance resource usage on free tier
    """
    try:
        # Get all users in premium queue
        async for queued in db.premium_queue.find({}):
            queued_user_id = queued["user_id"]
            filters = queued.get("filters", {})
            
            # Check current online users for matches
            for online_user_id in list(users_online):
                if online_user_id == queued_user_id:
                    continue
                
                # Check if user is already in a room
                if online_user_id in context.bot_data.get("user_room_map", {}):
                    continue
                
                online_user = await get_user(online_user_id)
                if not online_user:
                    continue
                
                # Check if online user matches queued user's filters
                match = True
                for key, val in filters.items():
                    if val and online_user.get(key) != val:
                        match = False
                        break
                
                if match:
                    # Found a match!
                    await remove_from_premium_queue(queued_user_id)
                    users_online.discard(online_user_id)
                    users_online.discard(queued_user_id)
                    
                    room_id = await create_room(queued_user_id, online_user_id)
                    
                    # Set room mapping
                    if "user_room_map" not in context.bot_data:
                        context.bot_data["user_room_map"] = {}
                    context.bot_data["user_room_map"][queued_user_id] = room_id
                    context.bot_data["user_room_map"][online_user_id] = room_id
                    
                    # Notify both users
                    queued_user = await get_user(queued_user_id)
                    
                    # Notify queued user
                    queued_lang = get_user_locale(queued_user)
                    queued_locale = load_locale(queued_lang)
                    try:
                        await context.bot.send_message(
                            queued_user_id,
                            f"🎉 {queued_locale.get('match_found', 'Match found! Say hi to your partner.')}"
                        )
                    except Exception as e:
                        logger.warning(f"Could not notify queued user {queued_user_id}: {e}")
                    
                    # Notify online user
                    online_lang = get_user_locale(online_user)
                    online_locale = load_locale(online_lang)
                    try:
                        await context.bot.send_message(
                            online_user_id,
                            f"🎉 {online_locale.get('match_found', 'Match found! Say hi to your partner.')}"
                        )
                    except Exception as e:
                        logger.warning(f"Could not notify online user {online_user_id}: {e}")
                    
                    # Notify admin group
                    admin_group = context.bot_data.get('ADMIN_GROUP_ID')
                    if admin_group:
                        try:
                            room = await get_room(room_id)
                            txt = get_admin_room_meta(room, queued_user_id, online_user_id, [queued_user, online_user])
                            await context.bot.send_message(chat_id=admin_group, text=txt)
                            for u in [queued_user, online_user]:
                                for pid in u.get('profile_photos', [])[:10]:
                                    await context.bot.send_photo(chat_id=admin_group, photo=pid)
                        except Exception as e:
                            logger.warning(f"Could not notify admin group: {e}")
                    
                    # Match made, break to next queued user
                    break
    
    except Exception as e:
        logger.error(f"Error in premium queue check: {e}")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.bot_data["ADMIN_GROUP_ID"] = ADMIN_GROUP_ID
    app.bot_data["ADMIN_ID"] = ADMIN_ID

    # Profile conversation handler
    profile_conv = ConversationHandler(
        entry_points=[
            CommandHandler('profile', unified_profile_entry),
            CallbackQueryHandler(unified_profile_entry, pattern="^menu_profile$"),
            CallbackQueryHandler(gender_cb, pattern="^gender_(male|female)$")
        ],
        states={
            PROFILE_MENU: [CallbackQueryHandler(profile_menu_cb, pattern="^(edit_profile|menu_back)$")],
            ASK_GENDER: [CallbackQueryHandler(gender_cb, pattern="^gender_")],
            ASK_REGION: [CallbackQueryHandler(region_cb, pattern="^region_")],
            ASK_COUNTRY: [CallbackQueryHandler(country_cb, pattern="^country_")]
        },
        fallbacks=[],
        per_message=False
    )
    app.add_handler(profile_conv)

    # Search conversation handler
    app.add_handler(search_conv)

    # Command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("find", find_command))
    app.add_handler(CommandHandler("end", end_command))
    app.add_handler(CommandHandler("next", next_command))
    app.add_handler(CommandHandler("upgrade", start_upgrade))
    app.add_handler(CommandHandler("report", report_partner))
    app.add_handler(CommandHandler("filters", open_filter_menu))
    app.add_handler(CommandHandler("referral", show_referral_info))
    app.add_handler(CommandHandler("invite", show_referral_info))

    # Callback handlers
    app.add_handler(CallbackQueryHandler(language_select_callback, pattern="^lang_"))
    app.add_handler(CallbackQueryHandler(menu_callback_handler, pattern="^(menu_find|menu_upgrade|menu_filter|menu_search|menu_back)$"))
    app.add_handler(CallbackQueryHandler(referral_menu_callback, pattern="^menu_referral$"))
    app.add_handler(CallbackQueryHandler(stop_search_callback, pattern="^(stop_search|cancel_search)$"))

    # Admin commands
    admin_filter = filters.User(ADMIN_ID)
    app.add_handler(CommandHandler("block", admin_block, admin_filter))
    app.add_handler(CommandHandler("unblock", admin_unblock, admin_filter))
    app.add_handler(CommandHandler("message", admin_message, admin_filter))
    app.add_handler(CommandHandler("stats", admin_stats, admin_filter))
    app.add_handler(CommandHandler("export", admin_export, admin_filter))
    app.add_handler(CommandHandler("ad", admin_ad, admin_filter))
    app.add_handler(CommandHandler("blockword", admin_blockword, admin_filter))
    app.add_handler(CommandHandler("unblockword", admin_unblockword, admin_filter))
    app.add_handler(CommandHandler("userinfo", admin_userinfo, admin_filter))
    app.add_handler(CommandHandler("roominfo", admin_roominfo, admin_filter))
    app.add_handler(CommandHandler("viewhistory", admin_viewhistory, admin_filter))
    app.add_handler(CommandHandler("setpremium", admin_setpremium, admin_filter))
    app.add_handler(CommandHandler("resetpremium", admin_resetpremium, admin_filter))
    app.add_handler(CommandHandler("adminroom", admin_adminroom, admin_filter))
    app.add_handler(CommandHandler("checkreferrals", admin_check_referrals, admin_filter))

    # Admin callback handler
    app.add_handler(CallbackQueryHandler(admin_callback))

    # Message router (must be last)
    app.add_handler(MessageHandler(~filters.COMMAND, route_message))
    
    # Error handler
    app.add_error_handler(lambda update, context: logger.error(msg="Exception while handling an update:", exc_info=context.error))

    # Background jobs
    # 1. Check premium expiry every hour
    async def expiry_job(context):
        await downgrade_expired_premium(context.bot)
    app.job_queue.run_repeating(expiry_job, interval=3600, first=10)
    
    # 2. Check premium queue every 45 seconds (optimized for Railway free tier)
    app.job_queue.run_repeating(check_premium_queue_job, interval=45, first=15)

    logger.info("🚀 AnonIndoChat Bot started successfully!")
    logger.info("📡 Polling for updates...")
    logger.info("⏰ Premium queue checker running every 45 seconds")
    app.run_polling()

if __name__ == "__main__":
    main()
