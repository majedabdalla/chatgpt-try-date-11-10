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
    admin_userinfo, admin_roominfo, admin_viewhistory, admin_setpremium
)
from handlers.match import (
    find_command, search_conv, end_command, next_command, open_filter_menu,
    menu_callback_handler, select_filter_cb
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
    "en": "English",
    "ar": "Arabic",
    "hi": "Hindi",
    "id": "Indonesian"
}

def load_locale(lang):
    path = os.path.join(LOCALE_DIR, f"{lang}.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

async def reply_translated(update, context, key, **kwargs):
    user = update.effective_user
    lang = "en"
    dbuser = await get_user(user.id)
    if dbuser and dbuser.get("language"):
        lang = dbuser["language"]
    locale = load_locale(lang)
    msg = locale.get(key, key)
    if kwargs:
        msg = msg.format(**kwargs)
    await update.message.reply_text(msg)

async def start(update: Update, context):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(locale, callback_data=f"lang_{code}")]
        for code, locale in LANGS.items()
    ])
    await update.message.reply_text(
        load_locale("en")["welcome"],
        reply_markup=kb
    )

async def language_select_callback(update: Update, context):
    query = update.callback_query
    await query.answer()
    lang = query.data.split("_", 1)[1]
    await update_user(query.from_user.id, {"language": lang})
    locale = load_locale(lang)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Profile", callback_data="menu_profile")],
        [InlineKeyboardButton("Find", callback_data="menu_find")],
        [InlineKeyboardButton("Upgrade", callback_data="menu_upgrade")],
        [InlineKeyboardButton("Filters", callback_data="menu_filter")],
        [InlineKeyboardButton("Back", callback_data="menu_back")]
    ])
    await query.edit_message_text(locale.get("main_menu", "Main Menu:"), reply_markup=kb)
    # Always enter the profile conversation for new users
    user = await get_user(query.from_user.id)
    if not user:
        # Enter profile setup conversation
        await unified_profile_entry(update, context)

def is_true_admin(update: Update):
    user_id = update.effective_user.id
    return user_id == ADMIN_ID

async def main_menu(update: Update, context):
    user = await get_user(update.effective_user.id)
    lang = user.get("language", "en") if user else "en"
    locale = load_locale(lang)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Profile", callback_data="menu_profile")],
        [InlineKeyboardButton("Find", callback_data="menu_find")],
        [InlineKeyboardButton("Upgrade", callback_data="menu_upgrade")],
        [InlineKeyboardButton("Filters", callback_data="menu_filter")],
        [InlineKeyboardButton("Back", callback_data="menu_back")]
    ])
    await update.effective_message.reply_text(locale.get("main_menu", "Main Menu:"), reply_markup=kb)

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.bot_data["ADMIN_GROUP_ID"] = ADMIN_GROUP_ID
    app.bot_data["ADMIN_ID"] = ADMIN_ID

    # Unified profile flow: all /profile and menu_profile go through the same ConversationHandler
    profile_conv = ConversationHandler(
        entry_points=[
            CommandHandler('profile', unified_profile_entry),
            CallbackQueryHandler(unified_profile_entry, pattern="^menu_profile$")
        ],
        states={
            PROFILE_MENU: [CallbackQueryHandler(profile_menu_cb, pattern="^(edit_profile|menu_back)$")],
            ASK_GENDER: [CallbackQueryHandler(gender_cb, pattern="^gender_")],
            ASK_REGION: [CallbackQueryHandler(region_cb, pattern="^region_")],
            ASK_COUNTRY: [CallbackQueryHandler(country_cb, pattern="^country_")]
        },
        fallbacks=[]
    )
    app.add_handler(profile_conv)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("find", find_command))
    app.add_handler(CommandHandler("end", end_command))
    app.add_handler(CommandHandler("next", next_command))
    app.add_handler(CommandHandler("upgrade", start_upgrade))
    app.add_handler(CommandHandler("report", report_partner))
    app.add_handler(CommandHandler("filters", open_filter_menu))

    app.add_handler(CallbackQueryHandler(language_select_callback, pattern="^lang_"))
    # Only menu options NOT for profile (the rest go to the conv handler)
    app.add_handler(CallbackQueryHandler(menu_callback_handler, pattern="^(menu_find|menu_upgrade|menu_filter|menu_back)$"))
    app.add_handler(CallbackQueryHandler(select_filter_cb, pattern="^(filter_|gender_|region_|country_|language_|menu_back)$"))

    app.add_handler(search_conv)

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

    app.add_handler(CallbackQueryHandler(admin_callback))

    # Only handle proof if user is in proof mode; otherwise, route_message handles all media
    # Remove: app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, handle_proof))
    app.add_handler(MessageHandler(~filters.COMMAND, route_message))
    app.add_error_handler(lambda update, context: logger.error(msg="Exception while handling an update:", exc_info=context.error))

    async def expiry_job(context):
        await downgrade_expired_premium()
    app.job_queue.run_repeating(expiry_job, interval=3600, first=10)

    logger.info("AnonindoChat Bot started (polling).")
    app.run_polling()

if __name__ == "__main__":
    main()
