from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ConversationHandler, CallbackQueryHandler, CommandHandler
from db import get_user, get_room, delete_room, update_user
from rooms import add_to_pool, remove_from_pool, users_online, create_room, close_room
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
    rows = [
        [InlineKeyboardButton(
            f"{get_label('gender')}: {get_label('gender', selected.get('gender', get_label('gender_skip')))}",
            callback_data="filter_gender"
        )],
        [InlineKeyboardButton(
            f"{get_label('region')}: {selected.get('region', get_label('gender_skip'))}",
            callback_data="filter_region"
        )],
        [InlineKeyboardButton(
            f"{get_label('language')}: {get_label('language', selected.get('language', get_label('gender_skip')))}",
            callback_data="filter_language"
        )],
        [InlineKeyboardButton(get_label('save_filters'), callback_data="save_filters")],
        [InlineKeyboardButton(get_label('menu_back'), callback_data="menu_back")]
    ]
    return InlineKeyboardMarkup(rows)

async def open_filter_menu(update: Update, context):
    user_id = update.effective_user.id
    user = await get_user(user_id)
    lang = get_user_locale(user)
    from bot import load_locale
    locale = load_locale(lang)
    if not user or not user.get("is_premium", False):
        await update.effective_message.reply_text(locale.get("premium_only", "This feature is for premium users only."))
        return ConversationHandler.END
    context.user_data["search_filters"] = dict(user.get("matching_preferences", {}))
    await update.effective_message.reply_text(
        locale.get("select_filters", "Set your filters below:"),
        reply_markup=get_filter_menu(lang, context, context.user_data["search_filters"])
    )
    return SELECT_FILTER

async def set_users_room_map(context, user1, user2, room_id):
    if "user_room_map" not in context.bot_data:
        context.bot_data["user_room_map"] = {}
    context.bot_data["user_room_map"][user1] = room_id
    context.bot_data["user_room_map"][user2] = room_id

async def remove_users_room_map(context, user1, user2=None):
    if "user_room_map" not in context.bot_data:
        return
    context.bot_data["user_room_map"].pop(user1, None)
    if user2 is not None:
        context.bot_data["user_room_map"].pop(user2, None)

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
    candidates = [uid for uid in users_online if uid != user_id]
    if candidates:
        await reply_func(locale.get("searching_partner", "Searching for a partner..."))
        partner = random.choice(candidates)
        remove_from_pool(partner)
        room_id = await create_room(user_id, partner)
        await set_users_room_map(context, user_id, partner, room_id)
        remove_from_pool(user_id)
        await reply_func(locale.get("match_found", "🎉 Match found! Say hi to your partner."))
        await context.bot.send_message(partner, locale.get("match_found", "🎉 Match found! Say hi to your partner."))
        partner_obj = await get_user(partner)
        admin_group = context.bot_data.get('ADMIN_GROUP_ID')
        if admin_group:
            room = await get_room(room_id)
            txt = get_admin_room_meta(room, user_id, partner, [user, partner_obj])
            await context.bot.send_message(chat_id=admin_group, text=txt)
            for u in [user, partner_obj]:
                for pid in u.get('profile_photos', []):
                    await context.bot.send_photo(chat_id=admin_group, photo=pid)
    else:
        await reply_func(locale.get("searching_partner", "Searching for a partner..."))
        add_to_pool(user_id)
        await reply_func(locale.get("pool_wait", "You have been added to the finding pool! Wait for a match."))

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
            if uid != user_id:
                other_id = uid
    await close_room(room_id)
    await delete_room(room_id)
    await update.message.reply_text(locale.get("end_chat", "You have left the chat."))
    if other_id:
        try:
            await context.bot.send_message(other_id, locale.get("partner_left", "Your chat partner has left the chat."))
        except Exception:
            pass
    # Do NOT re-add the other user to the pool! They must explicitly use /find to search again.

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
            [InlineKeyboardButton(locale.get(f"gender_{g}", g.capitalize()), callback_data=f"gender_{g}") for g in GENDERS],
            [InlineKeyboardButton(locale.get("gender_skip", "Skip"), callback_data="gender_skip")],
            [InlineKeyboardButton(locale.get("menu_back", "Back"), callback_data="menu_back")]
        ])
        await query.edit_message_text(locale.get("ask_gender", "Select your gender:"), reply_markup=kb)
        return SELECT_GENDER
    if data == "filter_region":
        kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton(r, callback_data=f"region_{r}")] for r in REGIONS] +
            [[InlineKeyboardButton(locale.get("gender_skip", "Skip"), callback_data="region_skip")],
             [InlineKeyboardButton(locale.get("menu_back", "Back"), callback_data="menu_back")]]
        )
        await query.edit_message_text(locale.get("ask_region", "Select your region:"), reply_markup=kb)
        return SELECT_REGION
    if data == "filter_language":
        kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton(locale.get(f"lang_{l}", l.upper()), callback_data=f"language_{l}")] for l in LANGUAGES] +
            [[InlineKeyboardButton(locale.get("gender_skip", "Skip"), callback_data="language_skip")],
             [InlineKeyboardButton(locale.get("menu_back", "Back"), callback_data="menu_back")]]
        )
        await query.edit_message_text(locale.get("ask_language", "Select preferred language:"), reply_markup=kb)
        return SELECT_LANGUAGE

    if data.startswith("gender_"):
        val = data.split("_", 1)[1]
        if val != "skip":
            filters["gender"] = val
        else:
            filters.pop("gender", None)
        context.user_data["search_filters"] = filters
        await query.edit_message_text(locale.get("select_filters", "Set your filters below:"), reply_markup=get_filter_menu(lang, context, filters))
        return SELECT_FILTER
    if data.startswith("region_"):
        val = data.split("_", 1)[1]
        if val != "skip":
            filters["region"] = val
        else:
            filters.pop("region", None)
        context.user_data["search_filters"] = filters
        await query.edit_message_text(locale.get("select_filters", "Set your filters below:"), reply_markup=get_filter_menu(lang, context, filters))
        return SELECT_FILTER
    if data.startswith("language_"):
        val = data.split("_", 1)[1]
        if val != "skip":
            filters["language"] = val
        else:
            filters.pop("language", None)
        context.user_data["search_filters"] = filters
        await query.edit_message_text(locale.get("select_filters", "Set your filters below:"), reply_markup=get_filter_menu(lang, context, filters))
        return SELECT_FILTER

    if data == "save_filters":
        await update_user(user_id, {"matching_preferences": filters})
        await query.edit_message_text(locale.get("filters_saved", "Your filters have been saved."))
        return ConversationHandler.END

    if data == "menu_back":
        await query.edit_message_text(locale.get("select_filters", "Set your filters below:"), reply_markup=get_filter_menu(lang, context, filters))
        return SELECT_FILTER

async def do_search(update: Update, context):
    query = update.callback_query
    user_id = query.from_user.id
    user = await get_user(user_id)
    lang = get_user_locale(user)
    from bot import load_locale
    locale = load_locale(lang)
    filters = dict(user.get("matching_preferences", {}))
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
        await query.edit_message_text(locale.get("no_partner_found", "No users found matching your criteria. Try again later."))
        return ConversationHandler.END
    partner = random.choice(candidates)
    users_online.discard(user_id)
    users_online.discard(partner)
    room_id = await create_room(user_id, partner)
    await set_users_room_map(context, user_id, partner, room_id)
    await query.edit_message_text(locale.get("match_found", "🎉 Match found! Say hi to your partner."))
    await context.bot.send_message(partner, locale.get("match_found", "🎉 Match found! Say hi to your partner."))
    user1 = await get_user(user_id)
    user2 = await get_user(partner)
    admin_group = context.bot_data.get('ADMIN_GROUP_ID')
    if admin_group:
        room = await get_room(room_id)
        txt = get_admin_room_meta(room, user_id, partner, [user1, user2])
        await context.bot.send_message(chat_id=admin_group, text=txt)
        for u in [user1, user2]:
            for pid in u.get('profile_photos', []):
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
        await query.edit_message_text(locale.get("upgrade_tip", "Please upload payment proof (photo, screenshot, or document)"))
    elif data == "menu_filter":
        if user.get("is_premium", False):
            return await open_filter_menu(update, context)
        else:
            await query.edit_message_text(locale.get("premium_only", "This feature is for premium users only."))
    elif data == "menu_search":
        if not user or not user.get("is_premium", False):
            await query.edit_message_text(locale.get("premium_only", "This feature is for premium users only."))
            return
        await do_search(update, context)
    elif data == "menu_back":
        from bot import main_menu
        await main_menu(update, context)
    else:
        await query.edit_message_text(locale.get("unknown_option", "Unknown menu option."))

search_conv = ConversationHandler(
    entry_points=[CommandHandler('filters', open_filter_menu)],
    states={
        SELECT_FILTER: [CallbackQueryHandler(select_filter_cb, pattern=None)],
        SELECT_GENDER: [CallbackQueryHandler(select_filter_cb, pattern=None)],
        SELECT_REGION: [CallbackQueryHandler(select_filter_cb, pattern=None)],
        SELECT_LANGUAGE: [CallbackQueryHandler(select_filter_cb, pattern=None)]
    },
    fallbacks=[],
    per_message=True
)
