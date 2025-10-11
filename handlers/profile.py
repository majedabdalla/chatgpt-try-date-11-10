from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from db import get_user, update_user
from models import default_user

ASK_GENDER, ASK_REGION, ASK_COUNTRY, PROFILE_MENU = range(4)

REGIONS = ['Africa', 'Europe', 'Asia', 'North America', 'South America', 'Oceania', 'Antarctica']
COUNTRIES = ['Indonesia', 'Malaysia', 'India', 'Russia', 'Arab', 'USA', 'Iran', 'Nigeria', 'Brazil', 'Turkey']

# Unified entry: /profile or Profile menu button
async def unified_profile_entry(update: Update, context):
    user = update.effective_user
    existing = await get_user(user.id)
    if not existing:
        # New user: create profile and ask gender
        profdata = default_user(user)
        photos = []
        try:
            user_photos = await context.bot.get_user_profile_photos(user.id)
            for photo in user_photos.photos[:3]:
                photos.append(photo[-1].file_id)
        except Exception:
            pass
        profdata["profile_photos"] = photos
        await update_user(user.id, profdata)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton('Male', callback_data='gender_male'), InlineKeyboardButton('Female', callback_data='gender_female')],
            [InlineKeyboardButton('Other', callback_data='gender_other'), InlineKeyboardButton('Skip', callback_data='gender_skip')],
            [InlineKeyboardButton("Back", callback_data="menu_back")]
        ])
        await update.effective_message.reply_text('Select your gender:', reply_markup=kb)
        return ASK_GENDER
    else:
        # Existing user: show profile menu
        await show_profile_menu(update, context)
        return PROFILE_MENU

async def show_profile_menu(update: Update, context):
    # Always called inside conv. handler!
    user = await get_user(update.effective_user.id)
    if not user:
        await update.effective_message.reply_text("No profile found! Please use /profile to set up your profile.")
        return
    txt = (
        f"Your Profile:\n"
        f"Username: @{user.get('username','')}\n"
        f"Gender: {user.get('gender','')}\n"
        f"Region: {user.get('region','')}\n"
        f"Country: {user.get('country','')}\n"
        f"Premium: {user.get('is_premium', False)}"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Edit", callback_data="edit_profile")],
        [InlineKeyboardButton("Back", callback_data="menu_back")]
    ])
    await update.effective_message.reply_text(txt, reply_markup=kb)

# Handles both "Edit" and "Back" in profile menu (inside conv. handler)
async def profile_menu_cb(update: Update, context):
    query = update.callback_query
    await query.answer()
    if query.data == "edit_profile":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton('Male', callback_data='gender_male'), InlineKeyboardButton('Female', callback_data='gender_female')],
            [InlineKeyboardButton('Other', callback_data='gender_other'), InlineKeyboardButton('Skip', callback_data='gender_skip')],
            [InlineKeyboardButton("Back", callback_data="menu_back")]
        ])
        await query.edit_message_text('Select your gender:', reply_markup=kb)
        return ASK_GENDER
    if query.data == "menu_back":
        from bot import main_menu
        await main_menu(update, context)
        return ConversationHandler.END

async def gender_cb(update: Update, context):
    query = update.callback_query
    await query.answer()
    gender = query.data.split('_', 1)[1]
    if gender != "skip":
        await update_user(query.from_user.id, {"gender": gender})
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(region, callback_data=f"region_{region}")] for region in REGIONS
    ] + [[InlineKeyboardButton("Back", callback_data="menu_back")]])
    await query.edit_message_text('Gender saved. Now select your region:', reply_markup=kb)
    return ASK_REGION

async def region_cb(update: Update, context):
    query = update.callback_query
    await query.answer()
    region = query.data.split('_', 1)[1]
    await update_user(query.from_user.id, {"region": region})
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(country, callback_data=f"country_{country}")] for country in COUNTRIES
    ] + [[InlineKeyboardButton("Back", callback_data="menu_back")]])
    await query.edit_message_text('Region saved. Now select your country:', reply_markup=kb)
    return ASK_COUNTRY

async def country_cb(update: Update, context):
    query = update.callback_query
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
    await query.edit_message_text('Profile saved! You can now use the chat.')
    if admin_group:
        await context.bot.send_message(chat_id=admin_group, text=profile_text)
        for file_id in user.get('profile_photos', []):
            await context.bot.send_photo(chat_id=admin_group, photo=file_id)
    from bot import main_menu
    await main_menu(update, context)
    return ConversationHandler.END
