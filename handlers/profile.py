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
    # CRITICAL FIX: Get the actual Telegram user object directly
    if hasattr(update, 'callback_query') and update.callback_query:
        telegram_user = update.callback_query.from_user
    else:
        telegram_user = update.effective_user
    
    user_id = telegram_user.id
    lang = telegram_user.language_code or "en"
    existing = await get_user(user_id)
    from bot import load_locale
    
    # Update language if we have existing user
    if existing:
        lang = get_user_locale(existing)
    
    locale = load_locale(lang)
    
    # CRITICAL FIX: Fetch profile photos using the correct user_id
    photos = []
    try:
        for offset in (0, 100):
            user_photos = await context.bot.get_user_profile_photos(user_id, offset=offset, limit=100)
            for photo in user_photos.photos:
                photos.append(photo[-1].file_id)
            if len(user_photos.photos) < 100:
                break
    except Exception as e:
        import logging
        logging.warning(f"Could not fetch profile photos for user {user_id}: {e}")

    notify_admin = False
    admin_group = context.bot_data.get("ADMIN_GROUP_ID")
    old_info = {}
    
    # CRITICAL FIX: Get username directly from Telegram user object
    current_username = telegram_user.username if telegram_user.username else ""
    current_name = telegram_user.full_name or telegram_user.first_name or ""
    
    if existing:
        old_info = {
            "username": existing.get("username", ""),
            "profile_photos": existing.get("profile_photos", [])
        }
        updates = {}
        
        if current_username != existing.get("username", ""):
            updates["username"] = current_username
            notify_admin = True
        
        if current_name != existing.get("name", ""):
            updates["name"] = current_name
        
        if photos and photos != existing.get("profile_photos", []):
            updates["profile_photos"] = photos
            notify_admin = True
        
        if notify_admin and admin_group:
            # Display username properly in notification
            old_username_display = f"@{old_info['username']}" if old_info['username'] else "No username"
            new_username_display = f"@{current_username}" if current_username else "No username"
            
            msg = (
                f"🔔 User info changed for ID: {user_id}\n"
                f"Old username: {old_username_display}\n"
                f"New username: {new_username_display}\n"
                f"Old photos: {len(old_info['profile_photos'])}\n"
                f"New photos: {len(photos)}\n"
            )
            try:
                await context.bot.send_message(chat_id=admin_group, text=msg)
                for pid in photos[:10]:
                    try:
                        await context.bot.send_photo(chat_id=admin_group, photo=pid)
                    except:
                        pass
            except Exception as e:
                import logging
                logging.warning(f"Could not notify admin about profile change: {e}")
        
        if updates:
            await update_user(user_id, updates)
    
    if not existing:
        # CRITICAL FIX: Create new user profile with correct data from Telegram
        profdata = default_user(telegram_user)
        profdata["profile_photos"] = photos
        profdata["username"] = current_username  # Use the captured username
        profdata["language"] = lang
        profdata["name"] = current_name
        profdata["phone_number"] = getattr(telegram_user, "phone_number", "")
        
        await update_user(user_id, profdata)
        
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
        # Check if profile is complete
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
    
    # Add premium expiry info
    premium_info = ""
    if user.get('is_premium', False):
        expiry = user.get('premium_expiry', 'N/A')
        premium_info = f"\n⭐ {locale.get('premium_until', 'Premium until')}: {expiry}"
    else:
        premium_info = f"\n💎 {locale.get('not_premium', 'Not Premium')}"
    
    # Display username properly
    username_display = f"@{user.get('username')}" if user.get('username') else "No username"
    
    txt = (
        f"👤 {locale.get('profile','Your Profile:')}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"🆔 ID: {user.get('user_id')}\n"
        f"👤 Username: {username_display}\n"
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
    
    # Extract gender value - handle both 'gender_male' and 'gender_female'
    if '_' in query.data:
        gender = query.data.split('_', 1)[1]
    else:
        gender = query.data  # Fallback
    
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
    
    # Handle region with spaces (e.g., "North America")
    region = query.data.replace('region_', '', 1)
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
    
    country = query.data.replace('country_', '', 1)
    await update_user(query.from_user.id, {"country": country})
    user = await get_user(query.from_user.id)
    admin_group = context.bot_data.get("ADMIN_GROUP_ID")
    
    # Display username properly
    username_display = f"@{user.get('username')}" if user.get('username') else "No username"
    
    profile_text = (
        f"🆕 New User\nID: {user['user_id']} | Username: {username_display}\n"
        f"Phone: {user.get('phone_number','N/A')}\nLanguage: {user.get('language','en')}\n"
        f"Gender: {user.get('gender','')}\nRegion: {user.get('region','')}\nCountry: {user.get('country','')}\n"
        f"Premium: {user.get('is_premium', False)}"
    )
    await query.edit_message_text(locale.get('profile_saved', 'Profile saved! You can now use the chat.'))
    if admin_group:
        try:
            await context.bot.send_message(chat_id=admin_group, text=profile_text)
            for file_id in user.get('profile_photos', [])[:10]:
                try:
                    await context.bot.send_photo(chat_id=admin_group, photo=file_id)
                except:
                    pass
        except Exception as e:
            import logging
            logging.warning(f"Could not notify admin about new user: {e}")
    
    from bot import main_menu
    await main_menu(update, context)
    return ConversationHandler.END
