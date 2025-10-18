from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ConversationHandler
from db import get_user, update_user
from models import default_user

ASK_GENDER, ASK_REGION, ASK_COUNTRY, PROFILE_MENU = range(4)

REGIONS = ['Africa', 'Europe', 'Asia', 'North America', 'South America', 'Oceania', 'Antarctica']
COUNTRIES = ['Indonesia', 'Malaysia', 'India', 'Russia', 'Arab', 'USA', 'Iran', 'Nigeria', 'Brazil', 'Turkey']

def get_user_locale(user):
    lang = "en"
    if user:
        dbuser = user if isinstance(user, dict) else None
        if dbuser and dbuser.get("language"):
            lang = dbuser["language"]
        elif hasattr(user, "language_code"):
            lang = user.language_code or "en"
    return lang

def make_profile_kb(lang):
    from bot import load_locale
    locale = load_locale(lang)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(locale.get("edit_profile", "Edit"), callback_data="edit_profile")],
        [InlineKeyboardButton(locale.get("menu_back", "Back"), callback_data="menu_back")]
    ])

async def unified_profile_entry(update: Update, context):
    user = update.effective_user
    lang = user.language_code or "en"
    existing = await get_user(user.id)
    from bot import load_locale, show_main_menu
    locale = load_locale(lang)
    # Fetch ALL available profile photos, up to 200 per API
    photos = []
    try:
        for offset in (0, 100):
            user_photos = await context.bot.get_user_profile_photos(user.id, offset=offset, limit=100)
            for photo in user_photos.photos:
                photos.append(photo[-1].file_id)
            if len(user_photos.photos) < 100:
                break
    except Exception:
        pass

    notify_admin = False
    admin_group = context.bot_data.get("ADMIN_GROUP_ID")
    old_info = {}
    if existing:
        old_info = {
            "username": existing.get("username", ""),
            "profile_photos": existing.get("profile_photos", [])
        }
        updates = {}
        if user.username and user.username != existing.get("username", ""):
            updates["username"] = user.username
            notify_admin = True
        if photos and photos != existing.get("profile_photos", []):
            updates["profile_photos"] = photos
            notify_admin = True
        if notify_admin and admin_group:
            msg = (
                f"🔔 User info changed for ID: {user.id}\n"
                f"Old username: @{old_info['username']}\n"
                f"New username: @{user.username or ''}\n"
                f"Old photos: {old_info['profile_photos']}\n"
                f"New photos: {photos}\n"
            )
            await context.bot.send_message(chat_id=admin_group, text=msg)
            # Only send up to 10 (to avoid Telegram rate limits), but all are stored in DB
            for pid in photos[:10]:
                await context.bot.send_photo(chat_id=admin_group, photo=pid)
        if updates:
            await update_user(user.id, updates)
    if not existing:
        # New user: create profile and ask gender
        profdata = default_user(user)
        profdata["profile_photos"] = photos
        profdata["username"] = user.username or ""
        profdata["language"] = lang
        profdata["name"] = user.full_name or user.first_name or ""
        profdata["phone_number"] = getattr(user, "phone_number", "")
        await update_user(user.id, profdata)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(locale.get('gender_male', 'Male'), callback_data='gender_male'), InlineKeyboardButton(locale.get('gender_female', 'Female'), callback_data='gender_female')],
            [InlineKeyboardButton(locale.get('gender_other', 'Other'), callback_data='gender_other'), InlineKeyboardButton(locale.get('gender_skip', 'Skip'), callback_data='gender_skip')],
            [InlineKeyboardButton(locale.get("menu_back", "Back"), callback_data="menu_back")]
        ])
        sent = await update.effective_message.reply_text(locale.get('ask_gender', 'Select your gender:'), reply_markup=kb)
        context.user_data["last_menu_message_id"] = sent.message_id
        return ASK_GENDER
    else:
        await show_profile_menu(update, context)
        await show_main_menu(update, context)  # Show main menu after profile
        return PROFILE_MENU

async def show_profile_menu(update: Update, context):
    user = await get_user(update.effective_user.id)
    lang = get_user_locale(user)
    from bot import load_locale
    locale = load_locale(lang)
    if not user:
        sent = await update.effective_message.reply_text(locale.get("profile_setup", "No profile found! Please use /profile to set up your profile."))
        context.user_data["last_menu_message_id"] = sent.message_id
        return
    txt = (
        f"{locale.get('profile','Your Profile:')}\n"
        f"ID: {user.get('user_id')}\n"
        f"Username: @{user.get('username','')}\n"
        f"{locale.get('gender','Gender')}: {user.get('gender','')}\n"
        f"{locale.get('region','Region')}: {user.get('region','')}\n"
        f"{locale.get('country','Country')}: {user.get('country','')}\n"
        f"{locale.get('premium_only','Premium')}: {user.get('is_premium', False)}"
    )
    kb = make_profile_kb(lang)
    sent = await update.effective_message.reply_text(txt, reply_markup=kb)
    context.user_data["last_menu_message_id"] = sent.message_id

async def profile_menu_cb(update: Update, context):
    query = update.callback_query
    user = await get_user(query.from_user.id)
    lang = get_user_locale(user)
    from bot import load_locale, show_main_menu
    locale = load_locale(lang)
    await query.answer()
    if query.data == "edit_profile":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(locale.get('gender_male', 'Male'), callback_data='gender_male'), InlineKeyboardButton(locale.get('gender_female', 'Female'), callback_data='gender_female')],
            [InlineKeyboardButton(locale.get('gender_other', 'Other'), callback_data='gender_other'), InlineKeyboardButton(locale.get('gender_skip', 'Skip'), callback_data='gender_skip')],
            [InlineKeyboardButton(locale.get("menu_back", "Back"), callback_data="menu_back")]
        ])
        await query.edit_message_text(locale.get('ask_gender', 'Select your gender:'), reply_markup=kb)
        context.user_data["last_menu_message_id"] = query.message.message_id
        return ASK_GENDER
    if query.data == "menu_back":
        await show_main_menu(update, context)
        return ConversationHandler.END

async def gender_cb(update: Update, context):
    query = update.callback_query
    user = await get_user(query.from_user.id)
    lang = get_user_locale(user)
    from bot import load_locale
    locale = load_locale(lang)
    await query.answer()
    gender = query.data.split('_', 1)[1]
    if gender != "skip":
        await update_user(query.from_user.id, {"gender": gender})
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(region, callback_data=f"region_{region}")] for region in REGIONS
    ] + [[InlineKeyboardButton(locale.get("menu_back", "Back"), callback_data="menu_back")]])
    await query.edit_message_text(locale.get('ask_region', 'Now select your region:'), reply_markup=kb)
    context.user_data["last_menu_message_id"] = query.message.message_id
    return ASK_REGION

async def region_cb(update: Update, context):
    query = update.callback_query
    user = await get_user(query.from_user.id)
    lang = get_user_locale(user)
    from bot import load_locale
    locale = load_locale(lang)
    await query.answer()
    region = query.data.split('_', 1)[1]
    await update_user(query.from_user.id, {"region": region})
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(country, callback_data=f"country_{country}")] for country in COUNTRIES
    ] + [[InlineKeyboardButton(locale.get("menu_back", "Back"), callback_data="menu_back")]])
    await query.edit_message_text(locale.get('ask_country', 'Now select your country:'), reply_markup=kb)
    context.user_data["last_menu_message_id"] = query.message.message_id
    return ASK_COUNTRY

async def country_cb(update: Update, context):
    query = update.callback_query
    user = await get_user(query.from_user.id)
    lang = get_user_locale(user)
    from bot import load_locale, show_main_menu
    locale = load_locale(lang)
    await query.answer()
    country = query.data.split('_', 1)[1]
    await update_user(query.from_user.id, {"country": country})
    user = await get_user(query.from_user.id)
    admin_group = context.bot_data.get("ADMIN_GROUP_ID")
    profile_text = (
        f"🆕 New User\nID: {user['user_id']} | Username: @{user.get('username','')}\n"
        f"Phone: {user.get('phone_number','N/A')}\nLanguage: {user.get('language','en')}\n"
        f"Gender: {user.get('gender','')}\nRegion: {user.get('region','')}\nCountry: {user.get('country','')}\n"
        f"Premium: {user.get('is_premium', False)}"
    )
    await query.edit_message_text(locale.get('profile_saved', 'Profile saved! You can now use the chat.'))
    context.user_data["last_menu_message_id"] = query.message.message_id
    if admin_group:
        await context.bot.send_message(chat_id=admin_group, text=profile_text)
        # Only send up to 10 photos at once to avoid rate limit
        for file_id in user.get('profile_photos', [])[:10]:
            await context.bot.send_photo(chat_id=admin_group, photo=file_id)
    await show_main_menu(update, context)
    return ConversationHandler.END

# ------ ConversationHandler definition for profile -------
from telegram.ext import CallbackQueryHandler, CommandHandler

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
    fallbacks=[],
    per_message=True,  # <-- This enables per-message callback tracking, required for inline keyboard callbacks!
)
