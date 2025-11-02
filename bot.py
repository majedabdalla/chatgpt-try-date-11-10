import os
import logging
import json
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler, ConversationHandler, filters
)
from db import db, get_user, update_user
from handlers.profile import (
    unified_profile_entry, profile_menu_cb, gender_cb, region_cb, country_cb,
    ASK_GENDER, ASK_REGION, ASK_COUNTRY, PROFILE_MENU
)
from handlers.premium import start_upgrade, handle_proof, admin_callback
from handlers.chat import process_message
from handlers.report import report_partner
from handlers.admincmds import (
    admin_block, admin_unblock, admin_message, admin_stats, admin_blockword, admin_unblockword,
    admin_userinfo, admin_roominfo, admin_viewhistory, admin_setpremium, admin_resetpremium, admin_adminroom
)
from handlers.match import (
    find_command, search_conv, end_command, next_command, open_filter_menu,
    menu_callback_handler, select_filter_cb, stop_search_callback
)
from handlers.forward import forward_to_admin
from admin import downgrade_expired_premium
from handlers.message_router import route_message

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
    # Enhanced welcome with better formatting
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(locale, callback_data=f"lang_{code}")]
        for code, locale in LANGS.items()
    ])
    welcome_text = (
        "🎉 *Welcome to MeetMate!*\n\n"
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
    await update_user(query.from_user.id, {"language": lang})
    locale = load_locale(lang)
    
    # Better menu layout with emojis
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"👤 {locale.get('profile', 'Profile')}", callback_data="menu_profile")],
        [InlineKeyboardButton(f"🔍 {locale.get('find', 'Find Partner')}", callback_data="menu_find")],
        [InlineKeyboardButton(f"🔎 {locale.get('search', 'Advanced Search')}", callback_data="menu_search")],
        [InlineKeyboardButton(f"⚙️ {locale.get('filters', 'Filter Settings')}", callback_data="menu_filter")],
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

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.bot_data["ADMIN_GROUP_ID"] = ADMIN_GROUP_ID
    app.bot_data["ADMIN_ID"] = ADMIN_ID

    profile_conv = ConversationHandler(
        entry_points=[
            CommandHandler('profile', unified_profile_entry),
            CallbackQueryHandler(unified_profile_entry, pattern="^menu_profile$")
        ],
        states={
            PROFILE_MENU: [CallbackQueryHandler(profile_menu_cb, pattern=None)],
            ASK_GENDER: [CallbackQueryHandler(gender_cb, pattern=None)],
            ASK_REGION: [CallbackQueryHandler(region_cb, pattern=None)],
            ASK_COUNTRY: [CallbackQueryHandler(country_cb, pattern=None)]
        },
        fallbacks=[]
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

    app.add_handler(CallbackQueryHandler(language_select_callback, pattern="^lang_"))
    app.add_handler(CallbackQueryHandler(menu_callback_handler, pattern="^(menu_find|menu_upgrade|menu_filter|menu_search|menu_back)$"))
    
    # FIX #1: Add handler for stop/cancel search
    app.add_handler(CallbackQueryHandler(stop_search_callback, pattern="^(stop_search|cancel_search)$"))

    admin_filter = filters.User(ADMIN_ID)
    app.add_handler(CommandHandler("block", admin_block, admin_filter))
    app.add_handler(CommandHandler("unblock", admin_unblock, admin_filter))
    app.add_handler(CommandHandler("message", admin_message, admin_filter))
    app.add_handler(CommandHandler("stats", admin_stats, admin_filter))
    app.add_handler(CommandHandler("blockword", admin_blockword, admin_filter))
    app.add_handler(CommandHandler("unblockword", admin_unblockword, admin_filter))
    app.add_handler(CommandHandler("userinfo", admin_userinfo, admin_filter))
    app.add_handler(CommandHandler("roominfo", admin_roominfo, admin_filter))
    app.add_handler(CommandHandler("viewhistory", admin_viewhistory, admin_filter))
    app.add_handler(CommandHandler("setpremium", admin_setpremium, admin_filter))
    app.add_handler(CommandHandler("resetpremium", admin_resetpremium, admin_filter))
    app.add_handler(CommandHandler("adminroom", admin_adminroom, admin_filter))

    app.add_handler(CallbackQueryHandler(admin_callback))

    app.add_handler(MessageHandler(~filters.COMMAND, route_message))
    app.add_error_handler(lambda update, context: logger.error(msg="Exception while handling an update:", exc_info=context.error))

    async def expiry_job(context):
        await downgrade_expired_premium()
    app.job_queue.run_repeating(expiry_job, interval=3600, first=10)

    logger.info("🚀 MeetMate Bot started successfully!")
    logger.info("📡 Polling for updates...")
    app.run_polling()

if __name__ == "__main__":
    main()
