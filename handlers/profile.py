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
        [InlineKeyboardButton(f"🔙 {locale.get('menu_back', 'Back to Menu')}", callback_data="menu_back")]
    ])

async def unified_profile_entry(update: Update, context):
    user = update.effective_user
    lang = user.language_code or "en"
    existing = await get_user(user.id)
    from bot import load_locale
    
    # Update language if we have existing user
    if existing:
        lang = get_user_locale(existing)
    
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
            [InlineKeyboardButton(locale.get('gender_male', 'Male'), callback_data='gender_male'),
             InlineKeyboardButton(locale.get('gender_female', 'Female'), callback_data='gender_female')]
        ])
        
        # Send the gender selection message
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(
                locale.get('ask_gender', 'Select your gender:'), 
                reply_markup=kb
            )
        else:
            await update.effective_message.reply_text(
                locale.get('ask_gender', 'Select your gender:'), 
                reply_markup=kb
            )
        return ASK_GENDER
    else:
        # FIX #1: Check if profile is complete
        if not existing.get('gender') or not existing.get('region') or not existing.get('country'):
            # Profile incomplete - go straight to edit mode
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton(locale.get('gender_male', 'Male'), callback_data='gender_male'),
                 InlineKeyboardButton(locale.get('gender_female', 'Female'), callback_data='gender_female')]
            ])
            
            if hasattr(update, 'callback_query') and update.callback_query:
                await update.callback_query.answer()
                await update.callback_query.edit_message_text(
                    locale.get('ask_gender', 'Select your gender:'), 
                    reply_markup=kb
                )
            else:
                await update.effective_message.reply_text(
                    locale.get('ask_gender', 'Select your gender:'), 
                    reply_markup=kb
                )
            return ASK_GENDER
        else:
            # Profile complete - show profile menu
            await show_profile_menu(update, context)
            return PROFILE_MENU

async def show_profile_menu(update: Update, context):
    user = await get_user(update.effective_user.id)
    lang = get_user_locale(user)
    from bot import load_locale
    locale = load_locale(lang)
    
    if not user:
        msg = locale.get("profile_setup", "No profile found! Please use /profile to set up your profile.")
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.message.reply_text(msg)
        else:
            await update.effective_message.reply_text(msg)
        return
    
    # FIX #2: Add premium expiry info
    premium_info = ""
    if user.get('is_premium', False):
        expiry = user.get('premium_expiry', 'N/A')
        premium_info = f"\n⭐ {locale.get('premium_until', 'Premium until')}: {expiry}"
    else:
        premium_info = f"\n💎 {locale.get('not_premium', 'Not Premium')}"
    
    txt = (
        f"👤 {locale.get('profile','Your Profile:')}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"🆔 ID: {user.get('user_id')}\n"
        f"👤 Username: @{user.get('username','N/A')}\n"
        f"👫 {locale.get('gender','Gender')}: {user.get('gender','N/A')}\n"
        f"🌍 {locale.get('region','Region')}: {user.get('region','N/A')}\n"
        f"🏳️ {locale.get('country','Country')}: {user.get('country','N/A')}\n"
        f"{premium_info}"
    )
    kb = make_profile_kb(lang)
    
    if hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.edit_message_text(txt, reply_markup=kb)
        except:
            await update.callback_query.message.reply_text(txt, reply_markup=kb)
    else:
        await update.effective_message.reply_text(txt, reply_markup=kb)

async def profile_menu_cb(update: Update, context):
    query = update.callback_query
    user = await get_user(query.from_user.id)
    lang = get_user_locale(user)
    from bot import load_locale
    locale = load_locale(lang)
    await query.answer()
    
    if query.data == "edit_profile":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(locale.get('gender_male', 'Male'), callback_data='gender_male'),
             InlineKeyboardButton(locale.get('gender_female', 'Female'), callback_data='gender_female')]
        ])
        await query.edit_message_text(locale.get('ask_gender', 'Select your gender:'), reply_markup=kb)
        return ASK_GENDER
    
    if query.data == "menu_back":
        from bot import main_menu
        await main_menu(update, context)
        return ConversationHandler.END

async def gender_cb(update: Update, context):
    query = update.callback_query
    user = await get_user(query.from_user.id)
    lang = get_user_locale(user)
    from bot import load_locale
    locale = load_locale(lang)
    await query.answer()
    
    # FIX #1: Extract gender value correctly
    gender = query.data.split('_', 1)[1]
    
    # Always save the gender (no skip option for profile setup)
    await update_user(query.from_user.id, {"gender": gender})
    
    # Show region selection
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(region, callback_data=f"region_{region}")] for region in REGIONS
    ])
    await query.edit_message_text(locale.get('ask_region', 'Now select your region:'), reply_markup=kb)
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
    ])
    await query.edit_message_text(locale.get('ask_country', 'Now select your country:'), reply_markup=kb)
    return ASK_COUNTRY

async def country_cb(update: Update, context):
    query = update.callback_query
    user = await get_user(query.from_user.id)
    lang = get_user_locale(user)
    from bot import load_locale
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
    if admin_group:
        await context.bot.send_message(chat_id=admin_group, text=profile_text)
        for file_id in user.get('profile_photos', [])[:10]:
            await context.bot.send_photo(chat_id=admin_group, photo=file_id)
    from bot import main_menu
    await main_menu(update, context)
    return ConversationHandler.END
