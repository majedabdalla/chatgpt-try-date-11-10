from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ConversationHandler, CallbackQueryHandler, CommandHandler
from db import get_user, get_room, delete_room, update_user
from rooms import add_to_pool, remove_from_pool, users_online, create_room, close_room, find_match_for  # PATCHED: import find_match_for
import random

SELECT_FILTER, SELECT_GENDER, SELECT_REGION, SELECT_LANGUAGE = range(4)
REGIONS = ['Africa', 'Europe', 'Asia', 'North America', 'South America', 'Oceania', 'Antarctica']
GENDERS = ['male', 'female', 'other']
LANGUAGES = ['en', 'ar', 'hi', 'id']

def get_user_locale(user):
    lang = "en"
    if user:
        dbuser = user if isinstance(user, dict) else None
        if dbuser and dbuser.get("language"):
            lang = dbuser["language"]
        elif hasattr(user, "language_code"):
            lang = user.language_code or "en"
    return lang

def get_filter_menu(lang, context, filters):
    from bot import load_locale
    locale = load_locale(lang)
    def get_label(key, value=None):
        if value:
            label = locale.get(f"{key}_{value}", value)
            if label == value:
                label = value.capitalize()
            return label
        return locale.get(key, key)
    selected = filters or {}
    
    # Better visual indicators for selected filters
    gender_display = selected.get('gender', '❌')
    if gender_display != '❌':
        gender_display = f"✅ {get_label('gender', gender_display)}"
    else:
        gender_display = locale.get('gender_skip', 'Any')
    
    region_display = selected.get('region', '❌')
    if region_display != '❌':
        region_display = f"✅ {region_display}"
    else:
        region_display = locale.get('gender_skip', 'Any')
    
    language_display = selected.get('language', '❌')
    if language_display != '❌':
        language_display = f"✅ {get_label('language', language_display)}"
    else:
        language_display = locale.get('gender_skip', 'Any')
    
    rows = [
        [InlineKeyboardButton(
            f"👤 {locale.get('gender', 'Gender')}: {gender_display}",
            callback_data="filter_gender"
        )],
        [InlineKeyboardButton(
            f"🌍 {locale.get('region', 'Region')}: {region_display}",
            callback_data="filter_region"
        )],
        [InlineKeyboardButton(
            f"💬 {locale.get('language', 'Language')}: {language_display}",
            callback_data="filter_language"
        )],
        [InlineKeyboardButton(f"💾 {locale.get('save_filters', 'Save Filters')}", callback_data="save_filters")],
        [InlineKeyboardButton(f"🔙 {locale.get('menu_back', 'Back')}", callback_data="menu_back")]
    ]
    return InlineKeyboardMarkup(rows)

async def open_filter_menu(update: Update, context):
    user_id = update.effective_user.id
    user = await get_user(user_id)
    lang = get_user_locale(user)
    from bot import load_locale
    locale = load_locale(lang)
    
    if not user or not user.get("is_premium", False):
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.answer(locale.get("premium_only", "This feature is for premium users only."), show_alert=True)
            await update.callback_query.edit_message_text(locale.get("premium_only", "This feature is for premium users only."))
        else:
            await update.effective_message.reply_text(locale.get("premium_only", "This feature is for premium users only."))
        return ConversationHandler.END
    
    context.user_data["search_filters"] = dict(user.get("matching_preferences", {}))
    
    filter_text = f"🔍 {locale.get('select_filters', 'Set your filters below:')}\n\n"
    filter_text += f"ℹ️ {locale.get('filter_info', 'Click on each option to change it, then Save.')}"
    
    if hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            filter_text,
            reply_markup=get_filter_menu(lang, context, context.user_data["search_filters"])
        )
    else:
        await update.effective_message.reply_text(
            filter_text,
            reply_markup=get_filter_menu(lang, context, context.user_data["search_filters"])
        )
    return SELECT_FILTER

# FIX: Also set context.user_data["room_id"] for both users, for /report and other per-user handlers
async def set_users_room_map(context, user1, user2, room_id):
    if "user_room_map" not in context.bot_data:
        context.bot_data["user_room_map"] = {}
    context.bot_data["user_room_map"][user1] = room_id
    context.bot_data["user_room_map"][user2] = room_id
    # Set in per-user data for /report and similar features
    # PTB >= 20: context.application.user_data[user_id]["room_id"]
    # Fallback if context.application not available: use context.user_data only for current user
    # Set for both users if possible
    if hasattr(context, "application"):
        context.application.user_data[user1]["room_id"] = room_id
        context.application.user_data[user2]["room_id"] = room_id
    # Also set for current user, for compatibility
    context.user_data["room_id"] = room_id

# Remove room_id from user_data for both users
async def remove_users_room_map(context, user1, user2=None):
    if "user_room_map" not in context.bot_data:
        return
    context.bot_data["user_room_map"].pop(user1, None)
    if hasattr(context, "application"):
        context.application.user_data[user1].pop("room_id", None)
    context.user_data.pop("room_id", None)
    if user2 is not None:
        context.bot_data["user_room_map"].pop(user2, None)
        if hasattr(context, "application"):
            context.application.user_data[user2].pop("room_id", None)

def get_admin_room_meta(room, user1, user2, users_data):
    def meta(u):
        return (
            f"ID: {u.get('user_id')} | Username: @{u.get('username','')} | Phone: {u.get('phone_number','N/A')}\n"
            f"Language: {u.get('language','en')}, Gender: {u.get('gender','')}, Region: {u.get('region','')}, Premium: {u.get('is_premium', False)}"
        )
    txt = f"🆕 New Room Created\nRoomID: {room['room_id']}\n" \
          f"👤 User1:\n{meta(users_data[0])}\n" \
          f"👤 User2:\n{meta(users_data[1])}\n"
    return txt

async def find_command(update: Update, context):
    user_id = update.effective_user.id
    user = await get_user(user_id)
    lang = get_user_locale(user)
    from bot import load_locale
    locale = load_locale(lang)
    reply_func = update.message.reply_text if getattr(update, "message", None) else (
        update.callback_query.edit_message_text if getattr(update, "callback_query", None) else (lambda msg: None)
    )
    if not user:
        await reply_func(locale.get("profile_setup", "Please setup your profile first with /profile."))
        return
    if user_id in context.bot_data.get("user_room_map", {}):
        await reply_func(locale.get("already_in_room", "You are already in a chat. Use /end or /next to leave first."))
        return
    
    # Show searching animation
    await reply_func(f"🔍 {locale.get('searching_partner', 'Searching for a partner...')}")
    
    candidates = [uid for uid in users_online if uid != user_id]
    if candidates:
        partner = random.choice(candidates)
        remove_from_pool(partner)
        room_id = await create_room(user_id, partner)
        await set_users_room_map(context, user_id, partner, room_id)
        remove_from_pool(user_id)
        await reply_func(f"🎉 {locale.get('match_found', 'Match found! Say hi to your partner.')}")
        await context.bot.send_message(partner, f"🎉 {locale.get('match_found', 'Match found! Say hi to your partner.')}")
        partner_obj = await get_user(partner)
        admin_group = context.bot_data.get('ADMIN_GROUP_ID')
        if admin_group:
            room = await get_room(room_id)
            txt = get_admin_room_meta(room, user_id, partner, [user, partner_obj])
            await context.bot.send_message(chat_id=admin_group, text=txt)
            for u in [user, partner_obj]:
                for pid in u.get('profile_photos', [])[:10]:
                    await context.bot.send_photo(chat_id=admin_group, photo=pid)
    else:
        add_to_pool(user_id)
        await reply_func(f"⏳ {locale.get('pool_wait', 'You have been added to the finding pool! Wait for a match.')}")

async def end_command(update: Update, context):
    user_id = update.effective_user.id
    user_room_map = context.bot_data.get("user_room_map", {})
    room_id = user_room_map.get(user_id)
    user = await get_user(user_id)
    lang = get_user_locale(user)
    from bot import load_locale
    locale = load_locale(lang)
    if not room_id:
        await update.message.reply_text(locale.get("not_in_room", "You are not in a room. Use /find to start a chat."))
        return
    room = await get_room(room_id)
    other_id = None
    if room and "users" in room:
        for uid in room["users"]:
            context.bot_data["user_room_map"].pop(uid, None)
            # Remove room_id from user_data (per-user) for both users
            if hasattr(context, "application"):
                context.application.user_data[uid].pop("room_id", None)
            if uid == user_id:
                context.user_data.pop("room_id", None)
            else:
                other_id = uid
    await close_room(room_id)
    await delete_room(room_id)
    await update.message.reply_text(f"👋 {locale.get('end_chat', 'You have left the chat.')}")
    if other_id:
        try:
            await context.bot.send_message(other_id, f"💔 {locale.get('partner_left', 'Your chat partner has left the chat.')}")
        except Exception:
            pass

async def next_command(update: Update, context):
    await end_command(update, context)
    await find_command(update, context)

async def select_filter_cb(update: Update, context):
    query = update.callback_query
    user_id = query.from_user.id
    user = await get_user(user_id)
    lang = get_user_locale(user)
    from bot import load_locale
    locale = load_locale(lang)
    filters = context.user_data.get("search_filters", {})
    await query.answer()
    data = query.data
    
    if data == "filter_gender":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"👨 {locale.get('gender_male', 'Male')}", callback_data="gender_male"), 
             InlineKeyboardButton(f"👩 {locale.get('gender_female', 'Female')}", callback_data="gender_female")],
            [InlineKeyboardButton(f"⚧ {locale.get('gender_other', 'Other')}", callback_data="gender_other")],
            [InlineKeyboardButton(f"❌ {locale.get('gender_skip', 'Any')}", callback_data="gender_skip")],
            [InlineKeyboardButton(f"🔙 {locale.get('menu_back', 'Back')}", callback_data="menu_back")]
        ])
        await query.edit_message_text(f"👤 {locale.get('ask_gender', 'Select preferred gender:')}", reply_markup=kb)
        return SELECT_GENDER
    
    if data == "filter_region":
        kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton(f"🌍 {r}", callback_data=f"region_{r}")] for r in REGIONS] +
            [[InlineKeyboardButton(f"❌ {locale.get('gender_skip', 'Any')}", callback_data="region_skip")],
             [InlineKeyboardButton(f"🔙 {locale.get('menu_back', 'Back')}", callback_data="menu_back")]]
        )
        await query.edit_message_text(f"🌍 {locale.get('ask_region', 'Select preferred region:')}", reply_markup=kb)
        return SELECT_REGION
    
    if data == "filter_language":
        lang_labels = {'en': '🇬🇧 English', 'ar': '🇸🇦 العربية', 'hi': '🇮🇳 हिंदी', 'id': '🇮🇩 Indonesia'}
        kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton(lang_labels.get(l, l.upper()), callback_data=f"language_{l}")] for l in LANGUAGES] +
            [[InlineKeyboardButton(f"❌ {locale.get('gender_skip', 'Any')}", callback_data="language_skip")],
             [InlineKeyboardButton(f"🔙 {locale.get('menu_back', 'Back')}", callback_data="menu_back")]]
        )
        await query.edit_message_text(f"💬 {locale.get('ask_language', 'Select preferred language:')}", reply_markup=kb)
        return SELECT_LANGUAGE

    if data.startswith("gender_"):
        val = data.split("_", 1)[1]
        if val != "skip":
            filters["gender"] = val
            await query.answer(f"✅ Gender filter set to: {val.capitalize()}")
        else:
            filters.pop("gender", None)
            await query.answer("✅ Gender filter removed")
        context.user_data["search_filters"] = filters
        await query.edit_message_text(
            f"🔍 {locale.get('select_filters', 'Set your filters below:')}",
            reply_markup=get_filter_menu(lang, context, filters)
        )
        return SELECT_FILTER
    
    if data.startswith("region_"):
        val = data.split("_", 1)[1]
        if val != "skip":
            filters["region"] = val
            await query.answer(f"✅ Region filter set to: {val}")
        else:
            filters.pop("region", None)
            await query.answer("✅ Region filter removed")
        context.user_data["search_filters"] = filters
        await query.edit_message_text(
            f"🔍 {locale.get('select_filters', 'Set your filters below:')}",
            reply_markup=get_filter_menu(lang, context, filters)
        )
        return SELECT_FILTER
    
    if data.startswith("language_"):
        val = data.split("_", 1)[1]
        if val != "skip":
            filters["language"] = val
            await query.answer(f"✅ Language filter set to: {val.upper()}")
        else:
            filters.pop("language", None)
            await query.answer("✅ Language filter removed")
        context.user_data["search_filters"] = filters
        await query.edit_message_text(
            f"🔍 {locale.get('select_filters', 'Set your filters below:')}",
            reply_markup=get_filter_menu(lang, context, filters)
        )
        return SELECT_FILTER

    if data == "save_filters":
        await update_user(user_id, {"matching_preferences": filters})
        await query.answer("✅ Filters saved successfully!")
        await query.edit_message_text(f"✅ {locale.get('filters_saved', 'Your filters have been saved.')}")
        # Call main menu after saving filters
        from bot import main_menu
        await main_menu(update, context)
        return ConversationHandler.END

    if data == "menu_back":
        await query.edit_message_text(
            f"🔍 {locale.get('select_filters', 'Set your filters below:')}",
            reply_markup=get_filter_menu(lang, context, filters)
        )
        return SELECT_FILTER

async def do_search(update: Update, context):
    query = update.callback_query
    user_id = query.from_user.id
    user = await get_user(user_id)
    lang = get_user_locale(user)
    from bot import load_locale
    locale = load_locale(lang)
    
    if user_id in context.bot_data.get("user_room_map", {}):
        await query.answer(locale.get("already_in_room", "You are already in a chat!"), show_alert=True)
        return ConversationHandler.END
    
    filters = dict(user.get("matching_preferences", {}))
    
    await query.answer()
    await query.edit_message_text(f"🔍 {locale.get('searching_partner', 'Searching for a partner with your filters...')}")
    
    candidates = []
    for uid in users_online:
        if uid == user_id:
            continue
        u = await get_user(uid)
        if not u:
            continue
        ok = True
        for key, val in filters.items():
            if val and u.get(key) != val:
                ok = False
                break
        if ok:
            candidates.append(uid)
    
    if not candidates:
        await query.edit_message_text(f"😔 {locale.get('no_partner_found', 'No users found matching your criteria. Try again later.')}")
        return ConversationHandler.END
    
    partner = random.choice(candidates)
    users_online.discard(user_id)
    users_online.discard(partner)
    room_id = await create_room(user_id, partner)
    await set_users_room_map(context, user_id, partner, room_id)
    await query.edit_message_text(f"🎉 {locale.get('match_found', 'Match found! Say hi to your partner.')}")
    await context.bot.send_message(partner, f"🎉 {locale.get('match_found', 'Match found! Say hi to your partner.')}")
    user1 = await get_user(user_id)
    user2 = await get_user(partner)
    admin_group = context.bot_data.get('ADMIN_GROUP_ID')
    if admin_group:
        room = await get_room(room_id)
        txt = get_admin_room_meta(room, user_id, partner, [user1, user2])
        await context.bot.send_message(chat_id=admin_group, text=txt)
        for u in [user1, user2]:
            for pid in u.get('profile_photos', [])[:10]:
                await context.bot.send_photo(chat_id=admin_group, photo=pid)
    return ConversationHandler.END

async def menu_callback_handler(update, context):
    query = update.callback_query
    user_id = query.from_user.id
    user = await get_user(user_id)
    lang = get_user_locale(user)
    from bot import load_locale
    locale = load_locale(lang)
    await query.answer()
    data = query.data
    
    if data == "menu_find":
        await find_command(update, context)
    elif data == "menu_upgrade":
        context.user_data["awaiting_upgrade_proof"] = True
        await query.edit_message_text(f"💳 {locale.get('upgrade_tip', 'Please upload payment proof (photo, screenshot, or document)')}")
    elif data == "menu_filter":
        # This now properly enters the ConversationHandler
        return await open_filter_menu(update, context)
    elif data == "menu_search":
        if not user or not user.get("is_premium", False):
            await query.answer(locale.get("premium_only", "This feature is for premium users only."), show_alert=True)
            await query.edit_message_text(locale.get("premium_only", "This feature is for premium users only."))
            return ConversationHandler.END
        return await do_search(update, context)
    elif data == "menu_back":
        from bot import main_menu
        await main_menu(update, context)
    else:
        await query.edit_message_text(locale.get("unknown_option", "Unknown menu option."))

# FIXED ConversationHandler with proper entry points
search_conv = ConversationHandler(
    entry_points=[
        CommandHandler('filters', open_filter_menu),
        CallbackQueryHandler(open_filter_menu, pattern="^menu_filter$"),  # <-- THIS IS THE KEY FIX!
    ],
    states={
        SELECT_FILTER: [CallbackQueryHandler(select_filter_cb, pattern="^(filter_gender|filter_region|filter_language|save_filters|menu_back)$")],
        SELECT_GENDER: [CallbackQueryHandler(select_filter_cb, pattern="^(gender_male|gender_female|gender_other|gender_skip|menu_back)$")],
        SELECT_REGION: [CallbackQueryHandler(select_filter_cb, pattern="^(region_[^|]+|region_skip|menu_back)$")],
        SELECT_LANGUAGE: [CallbackQueryHandler(select_filter_cb, pattern="^(language_[^|]+|language_skip|menu_back)$")]
    },
    fallbacks=[],
    per_message=True,
)
