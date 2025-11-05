from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ConversationHandler, CallbackQueryHandler, CommandHandler
from db import get_user, get_room, delete_room, update_user, db
from rooms import add_to_pool, remove_from_pool, users_online, create_room, close_room
from handlers.profile import unified_profile_entry, ASK_GENDER
import random
from datetime import datetime

SELECT_FILTER, SELECT_GENDER, SELECT_REGION, SELECT_LANGUAGE = range(4)
REGIONS = ['Africa', 'Europe', 'Asia', 'North America', 'South America', 'Oceania', 'Antarctica']
GENDERS = ['male', 'female']
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
        [InlineKeyboardButton(f"💾 {locale.get('save_filters', 'Save & Back')}", callback_data="save_filters")]
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

async def set_users_room_map(context, user1, user2, room_id):
    if "user_room_map" not in context.bot_data:
        context.bot_data["user_room_map"] = {}
    context.bot_data["user_room_map"][user1] = room_id
    context.bot_data["user_room_map"][user2] = room_id
    if hasattr(context, "application"):
        context.application.user_data[user1]["room_id"] = room_id
        context.application.user_data[user2]["room_id"] = room_id
    context.user_data["room_id"] = room_id

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

async def add_to_premium_queue(user_id, filters):
    """Add user to premium search queue in MongoDB"""
    await db.premium_queue.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "user_id": user_id,
                "filters": filters,
                "added_at": datetime.utcnow(),
                "notified": False
            }
        },
        upsert=True
    )

async def remove_from_premium_queue(user_id):
    """Remove user from premium queue"""
    await db.premium_queue.delete_one({"user_id": user_id})

async def check_premium_queue_for_match(user_id):
    """Check if anyone in queue matches this user's profile"""
    user = await get_user(user_id)
    if not user:
        return None
    
    # Find users in queue whose filters match this user
    async for queued in db.premium_queue.find({"user_id": {"$ne": user_id}}):
        filters = queued.get("filters", {})
        match = True
        
        # Check if this user matches the queued user's filters
        for key, val in filters.items():
            if val and user.get(key) != val:
                match = False
                break
        
        if match:
            return queued["user_id"]
    
    return None

async def find_command(update: Update, context):
    user_id = update.effective_user.id
    user = await get_user(user_id)
    
    # Get proper reply function
    if hasattr(update, 'callback_query') and update.callback_query:
        reply_func = update.callback_query.edit_message_text
        is_callback = True
    elif hasattr(update, 'message') and update.message:
        reply_func = update.message.reply_text
        is_callback = False
    else:
        return
    
    # Check if user has profile setup
    if not user or not user.get('gender') or not user.get('region') or not user.get('country'):
        from bot import load_locale
        lang = user.get('language', 'en') if user else 'en'
        locale = load_locale(lang)
        
        context.user_data['from_find_command'] = True
        msg_text = f"📝 {locale.get('profile_setup_required', 'Please complete your profile first before you can start chatting!')}"
        
        if is_callback:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(msg_text)
        else:
            await update.message.reply_text(msg_text)
        
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(locale.get('gender_male', 'Male'), callback_data='gender_male'),
             InlineKeyboardButton(locale.get('gender_female', 'Female'), callback_data='gender_female')]
        ])
        
        if is_callback:
            await update.callback_query.message.reply_text(
                locale.get('ask_gender', 'Select your gender:'), 
                reply_markup=kb
            )
        else:
            await update.message.reply_text(
                locale.get('ask_gender', 'Select your gender:'), 
                reply_markup=kb
            )
        
        return ASK_GENDER
    
    lang = get_user_locale(user)
    from bot import load_locale
    locale = load_locale(lang)
    
    if user_id in context.bot_data.get("user_room_map", {}):
        await reply_func(locale.get("already_in_room", "You are already in a chat. Use /end or /next to leave first."))
        return
    
    # Check if user is already in waiting pool
    if user_id in users_online:
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton(f"❌ {locale.get('stop_searching', 'Stop Searching')}", callback_data="stop_search")
        ]])
        await reply_func(f"⏳ {locale.get('already_searching', 'You are already searching for a partner...')}", reply_markup=kb)
        return
    
    # Check if someone in premium queue matches this user
    queued_match = await check_premium_queue_for_match(user_id)
    if queued_match:
        # Match found with someone in queue
        await remove_from_premium_queue(queued_match)
        room_id = await create_room(user_id, queued_match)
        await set_users_room_map(context, user_id, queued_match, room_id)
        
        await reply_func(f"🎉 {locale.get('match_found', 'Match found! Say hi to your partner.')}")
        
        partner_obj = await get_user(queued_match)
        partner_lang = get_user_locale(partner_obj)
        partner_locale = load_locale(partner_lang)
        await context.bot.send_message(queued_match, f"🎉 {partner_locale.get('match_found', 'Match found! Say hi to your partner.')}")
        
        admin_group = context.bot_data.get('ADMIN_GROUP_ID')
        if admin_group:
            room = await get_room(room_id)
            txt = get_admin_room_meta(room, user_id, queued_match, [user, partner_obj])
            await context.bot.send_message(chat_id=admin_group, text=txt)
            for u in [user, partner_obj]:
                for pid in u.get('profile_photos', [])[:10]:
                    await context.bot.send_photo(chat_id=admin_group, photo=pid)
        return
    
    # Show searching message with cancel button
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton(f"❌ {locale.get('cancel_search', 'Cancel')}", callback_data="cancel_search")
    ]])
    
    searching_msg = await reply_func(
        f"🔍 {locale.get('searching_partner', 'Searching for a partner...')}",
        reply_markup=kb
    )
    
    if is_callback:
        search_message_id = searching_msg.message_id if hasattr(searching_msg, 'message_id') else update.callback_query.message.message_id
        search_chat_id = update.callback_query.message.chat_id
    else:
        search_message_id = searching_msg.message_id
        search_chat_id = update.message.chat_id
    
    candidates = [uid for uid in users_online if uid != user_id]
    if candidates:
        # Found match immediately
        partner = random.choice(candidates)
        remove_from_pool(partner)
        room_id = await create_room(user_id, partner)
        await set_users_room_map(context, user_id, partner, room_id)
        remove_from_pool(user_id)
        
        try:
            await context.bot.edit_message_text(
                chat_id=search_chat_id,
                message_id=search_message_id,
                text=f"🎉 {locale.get('match_found', 'Match found! Say hi to your partner.')}"
            )
        except:
            await context.bot.send_message(
                chat_id=search_chat_id,
                text=f"🎉 {locale.get('match_found', 'Match found! Say hi to your partner.')}"
            )
        
        partner_obj = await get_user(partner)
        partner_lang = get_user_locale(partner_obj)
        partner_locale = load_locale(partner_lang)
        await context.bot.send_message(partner, f"🎉 {partner_locale.get('match_found', 'Match found! Say hi to your partner.')}")
        
        admin_group = context.bot_data.get('ADMIN_GROUP_ID')
        if admin_group:
            room = await get_room(room_id)
            txt = get_admin_room_meta(room, user_id, partner, [user, partner_obj])
            await context.bot.send_message(chat_id=admin_group, text=txt)
            for u in [user, partner_obj]:
                for pid in u.get('profile_photos', [])[:10]:
                    await context.bot.send_photo(chat_id=admin_group, photo=pid)
    else:
        # No match found, add to pool
        add_to_pool(user_id)

async def stop_search_callback(update: Update, context):
    query = update.callback_query
    user_id = query.from_user.id
    user = await get_user(user_id)
    lang = get_user_locale(user)
    from bot import load_locale
    locale = load_locale(lang)
    
    await query.answer()
    
    if user_id in users_online:
        remove_from_pool(user_id)
        await query.edit_message_text(f"❌ {locale.get('search_cancelled', 'Search cancelled. Use /find to search again.')}")
    else:
        # Check if in premium queue
        in_queue = await db.premium_queue.find_one({"user_id": user_id})
        if in_queue:
            await remove_from_premium_queue(user_id)
            await query.edit_message_text(f"❌ {locale.get('search_cancelled', 'Search cancelled. Use /find to search again.')}")
        else:
            await query.edit_message_text(locale.get("not_searching", "You are not currently searching."))

async def end_command(update: Update, context):
    user_id = update.effective_user.id
    user_room_map = context.bot_data.get("user_room_map", {})
    room_id = user_room_map.get(user_id)
    user = await get_user(user_id)
    lang = get_user_locale(user)
    from bot import load_locale
    locale = load_locale(lang)
    
    # If not in room but in waiting pool or queue, remove
    if not room_id:
        if user_id in users_online:
            remove_from_pool(user_id)
            await update.message.reply_text(f"❌ {locale.get('search_stopped', 'Stopped searching for a partner.')}")
            return
        
        # Check premium queue
        in_queue = await db.premium_queue.find_one({"user_id": user_id})
        if in_queue:
            await remove_from_premium_queue(user_id)
            await update.message.reply_text(f"❌ {locale.get('search_stopped', 'Stopped searching for a partner.')}")
            return
            
        await update.message.reply_text(locale.get("not_in_room", "You are not in a room. Use /find to start a chat."))
        return
    
    room = await get_room(room_id)
    other_id = None
    if room and "users" in room:
        for uid in room["users"]:
            context.bot_data["user_room_map"].pop(uid, None)
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
            other_user = await get_user(other_id)
            other_lang = get_user_locale(other_user)
            other_locale = load_locale(other_lang)
            await context.bot.send_message(
                other_id, 
                f"💔 {other_locale.get('partner_left', 'Your chat partner has left the chat.')}"
            )
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
    
    # FIX #1: Handle filter selection properly (not profile editing)
    if data == "filter_gender":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"👨 {locale.get('gender_male', 'Male')}", callback_data="fgender_male"), 
             InlineKeyboardButton(f"👩 {locale.get('gender_female', 'Female')}", callback_data="fgender_female")],
            [InlineKeyboardButton(f"❌ {locale.get('gender_skip', 'Any')}", callback_data="fgender_skip")],
            [InlineKeyboardButton(f"🔙 {locale.get('menu_back', 'Back')}", callback_data="fmenu_back")]
        ])
        await query.edit_message_text(f"👤 {locale.get('ask_gender', 'Select preferred gender:')}", reply_markup=kb)
        return SELECT_GENDER
    
    if data == "filter_region":
        kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton(f"🌍 {r}", callback_data=f"fregion_{r}")] for r in REGIONS] +
            [[InlineKeyboardButton(f"❌ {locale.get('gender_skip', 'Any')}", callback_data="fregion_skip")],
             [InlineKeyboardButton(f"🔙 {locale.get('menu_back', 'Back')}", callback_data="fmenu_back")]]
        )
        await query.edit_message_text(f"🌍 {locale.get('ask_region', 'Select preferred region:')}", reply_markup=kb)
        return SELECT_REGION
    
    if data == "filter_language":
        lang_labels = {'en': '🇬🇧 English', 'ar': '🇸🇦 العربية', 'hi': '🇮🇳 हिंदी', 'id': '🇮🇩 Indonesia'}
        kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton(lang_labels.get(l, l.upper()), callback_data=f"flanguage_{l}")] for l in LANGUAGES] +
            [[InlineKeyboardButton(f"❌ {locale.get('gender_skip', 'Any')}", callback_data="flanguage_skip")],
             [InlineKeyboardButton(f"🔙 {locale.get('menu_back', 'Back')}", callback_data="fmenu_back")]]
        )
        await query.edit_message_text(f"💬 {locale.get('ask_language', 'Select preferred language:')}", reply_markup=kb)
        return SELECT_LANGUAGE

    # Handle filter selections (with 'f' prefix to differentiate from profile editing)
    if data.startswith("fgender_"):
        val = data.replace("fgender_", "")
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
    
    if data.startswith("fregion_"):
        val = data.replace("fregion_", "")
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
    
    if data.startswith("flanguage_"):
        val = data.replace("flanguage_", "")
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
        from bot import main_menu
        await main_menu(update, context)
        return ConversationHandler.END

    if data == "fmenu_back":
        await query.edit_message_text(
            f"🔍 {locale.get('select_filters', 'Set your filters below:')}",
            reply_markup=get_filter_menu(lang, context, filters)
        )
        return SELECT_FILTER

async def do_search(update: Update, context):
    """FIX #2: Advanced search with queue waiting"""
    query = update.callback_query
    user_id = query.from_user.id
    user = await get_user(user_id)
    lang = get_user_locale(user)
    from bot import load_locale
    locale = load_locale(lang)
    
    # Check profile completeness
    if not user or not user.get('gender') or not user.get('region') or not user.get('country'):
        await query.answer(locale.get('profile_setup_required', 'Please complete your profile first!'), show_alert=True)
        await query.message.reply_text(f"📝 {locale.get('profile_setup_required', 'Please complete your profile first before you can start chatting!')}")
        return await unified_profile_entry(update, context)
    
    if user_id in context.bot_data.get("user_room_map", {}):
        await query.answer(locale.get("already_in_room", "You are already in a chat!"), show_alert=True)
        return ConversationHandler.END
    
    filters = dict(user.get("matching_preferences", {}))
    
    await query.answer()
    
    # Add cancel button during search
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton(f"❌ {locale.get('cancel_search', 'Cancel')}", callback_data="cancel_search")
    ]])
    await query.edit_message_text(
        f"🔍 {locale.get('searching_partner', 'Searching for a partner with your filters...')}",
        reply_markup=kb
    )
    
    # First check current online users
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
    
    if candidates:
        # Found immediate match
        partner = random.choice(candidates)
        users_online.discard(user_id)
        users_online.discard(partner)
        room_id = await create_room(user_id, partner)
        await set_users_room_map(context, user_id, partner, room_id)
        
        await query.edit_message_text(f"🎉 {locale.get('match_found', 'Match found! Say hi to your partner.')}")
        
        partner_obj = await get_user(partner)
        partner_lang = get_user_locale(partner_obj)
        partner_locale = load_locale(partner_lang)
        await context.bot.send_message(partner, f"🎉 {partner_locale.get('match_found', 'Match found! Say hi to your partner.')}")
        
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
    else:
        # No immediate match - add to premium queue and wait
        await add_to_premium_queue(user_id, filters)
        await query.edit_message_text(
            f"⏳ {locale.get('queue_waiting', 'No matches right now. You are in the priority queue and will be matched as soon as someone matching your filters comes online!')}\n\n"
            f"💡 We'll notify you when a match is found!",
            reply_markup=kb
        )
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

search_conv = ConversationHandler(
    entry_points=[
        CommandHandler('filters', open_filter_menu),
        CallbackQueryHandler(open_filter_menu, pattern="^menu_filter$"),
    ],
    states={
        SELECT_FILTER: [CallbackQueryHandler(select_filter_cb, pattern="^(filter_gender|filter_region|filter_language|save_filters|fmenu_back)$")],
        SELECT_GENDER: [CallbackQueryHandler(select_filter_cb, pattern="^(fgender_male|fgender_female|fgender_skip|fmenu_back)$")],
        SELECT_REGION: [CallbackQueryHandler(select_filter_cb, pattern="^(fregion_.+|fmenu_back)$")],
        SELECT_LANGUAGE: [CallbackQueryHandler(select_filter_cb, pattern="^(flanguage_.+|fmenu_back)$")]
    },
    fallbacks=[],
    per_message=True,
)
