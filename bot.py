import os
import logging
import json
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler, ConversationHandler, filters
)
from db import (
    db, get_user, update_user, get_room, test_connection, create_indexes,
    mark_all_users_offline, cleanup_stale_rooms, get_user_room, set_user_room
)
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
    admin_adminroom, admin_ad, admin_export, admin_linkusers
)
from handlers.match import (
    find_command, search_conv, end_command, next_command, open_filter_menu,
    menu_callback_handler, select_filter_cb, stop_search_callback,
    remove_from_premium_queue, create_room, get_admin_room_meta
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

_locale_cache = {}

def load_locale(lang):
    """Load locale with caching"""
    if lang in _locale_cache:
        return _locale_cache[lang]
    
    path = os.path.join(LOCALE_DIR, f"{lang}.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            _locale_cache[lang] = data
            return data
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
    user = query.from_user
    
    existing_user = await get_user(user.id)
    
    photos = []
    try:
        user_photos = await context.bot.get_user_profile_photos(user.id, limit=10)
        for photo in user_photos.photos[:10]:
            photos.append(photo[-1].file_id)
    except Exception as e:
        logger.warning(f"Could not fetch profile photos: {e}")
    
    username = user.username if user.username else ""
    
    await update_user(user.id, {
        "language": lang,
        "username": username,
        "name": user.full_name or user.first_name or "",
        "profile_photos": photos
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
    
    if not existing_user:
        await unified_profile_entry(update, context)

async def show_main_menu(update, context, menu_text=None, reply_markup=None):
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
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user = await get_user(user_id)
    
    if not user:
        await query.edit_message_text("Please complete your profile first using /start")
        return
    
    lang = get_user_locale(user)
    locale = load_locale(lang)
    
    bot_info = await context.bot.get_me()
    bot_username = bot_info.username
    
    from handlers.referral import generate_referral_link
    referral_link = await generate_referral_link(user_id, bot_username)
    
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
    """Background job to check premium queue for matches"""
    try:
        queued_users = []
        async for queued in db.premium_queue.find({}):
            queued_users.append(queued)
        
        online_users = []
        async for user in db.users.find({"is_online": True}):
            user_id = user["user_id"]
            existing_room = await get_user_room(user_id)
            if not existing_room:
                online_users.append(user)
        
        for queued in queued_users:
            queued_user_id = queued["user_id"]
            filters = queued.get("filters", {})
            
            existing_room = await get_user_room(queued_user_id)
            if existing_room:
                await remove_from_premium_queue(queued_user_id)
                continue
            
            for online_user in online_users:
                online_user_id = online_user["user_id"]
                
                if online_user_id == queued_user_id:
                    continue
                
                if await get_user_room(online_user_id):
                    continue
                
                match = True
                for key, val in filters.items():
                    if val and online_user.get(key) != val:
                        match = False
                        break
                
                if match:
                    await remove_from_premium_queue(queued_user_id)
                    users_online.discard(online_user_id)
                    users_online.discard(queued_user_id)
                    
                    room_id = await create_room(queued_user_id, online_user_id)
                    
                    await set_user_room(queued_user_id, room_id)
                    await set_user_room(online_user_id, room_id)
                    
                    queued_user = await get_user(queued_user_id)
                    
                    for uid, user_data in [(queued_user_id, queued_user), (online_user_id, online_user)]:
                        try:
                            lang = get_user_locale(user_data)
                            locale = load_locale(lang)
                            await context.bot.send_message(
                                uid,
                                f"🎉 {locale.get('match_found', 'Match found! Say hi to your partner.')}"
                            )
                        except Exception as e:
                            logger.warning(f"Could not notify user {uid}: {e}")
                    
                    admin_group = context.bot_data.get('ADMIN_GROUP_ID')
                    if admin_group:
                        try:
                            room = await get_room(room_id)
                            txt = get_admin_room_meta(room, queued_user_id, online_user_id, [queued_user, online_user])
                            await context.bot.send_message(chat_id=admin_group, text=txt)
                            for u in [queued_user, online_user]:
                                for pid in u.get('profile_photos', [])[:5]:
                                    try:
                                        await context.bot.send_photo(chat_id=admin_group, photo=pid)
                                    except:
                                        pass
                        except Exception as e:
                            logger.warning(f"Could not notify admin group: {e}")
                    
                    online_users.remove(online_user)
                    break
    
    except Exception as e:
        logger.error(f"Error in premium queue check: {e}")

async def startup(application):
    """Startup tasks"""
    logger.info("🚀 Starting AnonIndoChat Bot...")
    
    if not await test_connection():
        logger.error("❌ Database connection failed! Bot cannot start.")
        raise Exception("MongoDB connection failed")
    
    await create_indexes()
    
    cleaned = await cleanup_stale_rooms()
    if cleaned > 0:
        logger.info(f"🧹 Cleaned up {cleaned} stale room mappings")
    
    logger.info("✅ Bot startup complete!")

async def shutdown(application):
    """Shutdown tasks"""
    logger.info("🛑 Shutting down AnonIndoChat Bot...")
    await mark_all_users_offline()
    logger.info("✅ Bot shutdown complete!")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.bot_data["ADMIN_GROUP_ID"] = ADMIN_GROUP_ID
    app.bot_data["ADMIN_ID"] = ADMIN_ID

    app.post_init = startup
    app.post_shutdown = shutdown

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

    app.add_handler(search_conv)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("find", find_command))
    app.add_handler(CommandHandler("end", end_command))
    app.add_handler(CommandHandler("next", next_command))
    app.add_handler(CommandHandler("upgrade", start_upgrade))
    app.add_handler(CommandHandler("report", report_partner))
    app.add_handler(CommandHandler("filters", open_filter_menu))
    app.add_handler(CommandHandler("referral", show_referral_info))
    app.add_handler(CommandHandler("invite", show_referral_info))

    app.add_handler(CallbackQueryHandler(language_select_callback, pattern="^lang_"))
    app.add_handler(CallbackQueryHandler(menu_callback_handler, pattern="^(menu_find|menu_upgrade|menu_filter|menu_search|menu_back)$"))
    app.add_handler(CallbackQueryHandler(referral_menu_callback, pattern="^menu_referral$"))
    app.add_handler(CallbackQueryHandler(stop_search_callback, pattern="^(stop_search|cancel_search)$"))

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
    app.add_handler(CommandHandler("linkusers", admin_linkusers, admin_filter))
    app.add_handler(CommandHandler("checkreferrals", admin_check_referrals, admin_filter))

    app.add_handler(CallbackQueryHandler(admin_callback))

    app.add_handler(MessageHandler(~filters.COMMAND, route_message))
    
    app.add_error_handler(lambda update, context: logger.error(msg="Exception while handling an update:", exc_info=context.error))

    async def expiry_job(context):
        await downgrade_expired_premium(context.bot)
    app.job_queue.run_repeating(expiry_job, interval=3600, first=10)
    
    app.job_queue.run_repeating(check_premium_queue_job, interval=45, first=15)
    
    async def cleanup_job(context):
        cleaned = await cleanup_stale_rooms()
        if cleaned > 0:
            logger.info(f"Periodic cleanup: removed {cleaned} stale mappings")
    app.job_queue.run_repeating(cleanup_job, interval=1800, first=300)

    logger.info("🚀 AnonIndoChat Bot started successfully!")
    logger.info("📡 Polling for updates...")
    logger.info("⏰ Premium queue checker running every 45 seconds")
    logger.info("🧹 Cleanup job running every 30 minutes")
    app.run_polling()

if __name__ == "__main__":
    main()
