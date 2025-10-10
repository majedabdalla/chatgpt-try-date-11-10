from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ConversationHandler, CallbackQueryHandler, CommandHandler
from db import get_user, get_room, delete_room
from rooms import add_to_pool, remove_from_pool, users_online, create_room, close_room
import random

SELECT_FILTER, SELECT_GENDER, SELECT_REGION, SELECT_COUNTRY, SELECT_LANGUAGE, CONFIRM_SEARCH = range(6)
REGIONS = ['Africa', 'Europe', 'Asia', 'North America', 'South America', 'Oceania', 'Antarctica']
COUNTRIES = ['Indonesia', 'Malaysia', 'India', 'Russia', 'Arab', 'USA', 'Iran', 'Nigeria', 'Brazil', 'Turkey']
GENDERS = ['male', 'female', 'other']
LANGUAGES = ['en', 'ar', 'hi', 'id']

def get_filter_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Filter by Gender", callback_data="filter_gender")],
        [InlineKeyboardButton("Filter by Region", callback_data="filter_region")],
        [InlineKeyboardButton("Filter by Country", callback_data="filter_country")],
        [InlineKeyboardButton("Filter by Language", callback_data="filter_language")],
        [InlineKeyboardButton("Proceed to Search", callback_data="filter_none")],
        [InlineKeyboardButton("Back", callback_data="menu_back")]
    ])

async def open_filter_menu(update: Update, context):
    user_id = update.effective_user.id
    user = await get_user(user_id)
    if not user or not user.get("is_premium", False):
        await update.message.reply_text("This feature is for premium users only.")
        return ConversationHandler.END
    await update.message.reply_text(
        "Select your filters:",
        reply_markup=get_filter_menu()
    )
    context.user_data["search_filters"] = {}
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
            f"Language: {u.get('language','en')}, Gender: {u.get('gender','')}, Region: {u.get('region','')}, Country: {u.get('country','')}, Premium: {u.get('is_premium', False)}"
        )
    txt = f"🆕 New Room Created\nRoomID: {room['room_id']}\n" \
          f"👤 User1:\n{meta(users_data[0])}\n" \
          f"👤 User2:\n{meta(users_data[1])}\n"
    return txt

async def find_command(update: Update, context):
    user_id = update.effective_user.id
    user = await get_user(user_id)
    if not user:
        await update.message.reply_text("Please setup your profile first with /profile.")
        return

    if user_id in context.bot_data.get("user_room_map", {}):
        await update.message.reply_text("You are already in a chat. Use /end or /next to leave first.")
        return

    candidates = [uid for uid in users_online if uid != user_id]
    if candidates:
        await update.message.reply_text("Searching for a partner...")
        partner = random.choice(candidates)
        remove_from_pool(partner)
        room_id = await create_room(user_id, partner)
        await set_users_room_map(context, user_id, partner, room_id)
        remove_from_pool(user_id)
        await update.message.reply_text("🎉 Match found! Say hi to your partner.")
        await context.bot.send_message(partner, "🎉 Match found! Say hi to your partner.")
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
        await update.message.reply_text("Searching for a partner...")
        add_to_pool(user_id)
        await update.message.reply_text("You have been added to the finding pool! Wait for a match.")

async def end_command(update: Update, context):
    user_id = update.effective_user.id
    user_room_map = context.bot_data.get("user_room_map", {})
    room_id = user_room_map.get(user_id)
    if not room_id:
        await update.message.reply_text("You are not in a room.")
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
    await update.message.reply_text("You have left the chat.")
    if other_id:
        try:
            await context.bot.send_message(other_id, "Your chat partner has left the chat.")
        except Exception:
            pass

async def next_command(update: Update, context):
    await end_command(update, context)
    await find_command(update, context)

async def select_filter_cb(update: Update, context):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "filter_gender":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Male", callback_data="gender_male"),
             InlineKeyboardButton("Female", callback_data="gender_female"),
             InlineKeyboardButton("Other", callback_data="gender_other")],
            [InlineKeyboardButton("Back", callback_data="menu_back")]
        ])
        await query.edit_message_text("Select preferred gender:", reply_markup=kb)
        return SELECT_GENDER
    if data == "filter_region":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(region, callback_data=f"region_{region}")] for region in REGIONS
        ] + [[InlineKeyboardButton("Back", callback_data="menu_back")]])
        await query.edit_message_text("Select preferred region:", reply_markup=kb)
        return SELECT_REGION
    if data == "filter_country":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(country, callback_data=f"country_{country}")] for country in COUNTRIES
        ] + [[InlineKeyboardButton("Back", callback_data="menu_back")]])
        await query.edit_message_text("Select preferred country:", reply_markup=kb)
        return SELECT_COUNTRY
    if data == "filter_language":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(lang.upper(), callback_data=f"language_{lang}")] for lang in LANGUAGES
        ] + [[InlineKeyboardButton("Back", callback_data="menu_back")]])
        await query.edit_message_text("Select preferred language:", reply_markup=kb)
        return SELECT_LANGUAGE
    if data == "filter_none":
        return await do_search(update, context)
    if data == "menu_back":
        await query.edit_message_text("Select your filters:", reply_markup=get_filter_menu())
        return SELECT_FILTER
    if data.startswith("gender_"):
        gender = data.split('_', 1)[1]
        context.user_data.setdefault("search_filters", {})["gender"] = gender
        await query.edit_message_text(f"Gender filter set: {gender}.", reply_markup=get_filter_menu())
        return SELECT_FILTER
    if data.startswith("region_"):
        region = data.split('_', 1)[1]
        context.user_data.setdefault("search_filters", {})["region"] = region
        await query.edit_message_text(f"Region filter set: {region}.", reply_markup=get_filter_menu())
        return SELECT_FILTER
    if data.startswith("country_"):
        country = data.split('_', 1)[1]
        context.user_data.setdefault("search_filters", {})["country"] = country
        await query.edit_message_text(f"Country filter set: {country}.", reply_markup=get_filter_menu())
        return SELECT_FILTER
    if data.startswith("language_"):
        language = data.split('_', 1)[1]
        context.user_data.setdefault("search_filters", {})["language"] = language
        await query.edit_message_text(f"Language filter set: {language}.", reply_markup=get_filter_menu())
        return SELECT_FILTER

async def do_search(update: Update, context):
    query = update.callback_query
    filters = context.user_data.get("search_filters", {})
    from db import get_user
    candidates = []
    for uid in users_online:
        if uid == query.from_user.id:
            continue
        u = await get_user(uid)
        if not u:
            continue
        ok = True
        if filters.get("gender") and u.get("gender") != filters["gender"]:
            ok = False
        if filters.get("region") and u.get("region") != filters["region"]:
            ok = False
        if filters.get("country") and u.get("country") != filters["country"]:
            ok = False
        if filters.get("language") and u.get("language") != filters["language"]:
            ok = False
        if ok:
            candidates.append(uid)
    if not candidates:
        await query.edit_message_text("No users found matching your criteria. Try again later.", reply_markup=get_filter_menu())
        return ConversationHandler.END
    partner = random.choice(candidates)
    users_online.discard(query.from_user.id)
    users_online.discard(partner)
    room_id = await create_room(query.from_user.id, partner)
    await set_users_room_map(context, query.from_user.id, partner, room_id)
    await query.edit_message_text("🎉 Match found! Say hi to your partner.")
    await context.bot.send_message(partner, "🎉 Match found! Say hi to your partner.")
    user1 = await get_user(query.from_user.id)
    user2 = await get_user(partner)
    admin_group = context.bot_data.get('ADMIN_GROUP_ID')
    if admin_group:
        room = await get_room(room_id)
        txt = get_admin_room_meta(room, query.from_user.id, partner, [user1, user2])
        await context.bot.send_message(chat_id=admin_group, text=txt)
        for u in [user1, user2]:
            for pid in u.get('profile_photos', []):
                await context.bot.send_photo(chat_id=admin_group, photo=pid)
    return ConversationHandler.END

# Main menu callback handler for inline menu actions
async def menu_callback_handler(update, context):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "menu_profile":
        from handlers.profile import show_profile_menu
        await show_profile_menu(update, context)
    elif data == "menu_find":
        await query.edit_message_text("Searching for a partner...")
        await find_command(update, context)
    elif data == "menu_upgrade":
        await query.edit_message_text("Please upload payment proof (photo, screenshot, or document)")
        from handlers.premium import start_upgrade
        await start_upgrade(update, context)
    elif data == "menu_filter":
        await query.edit_message_text("Select your filters:")
        await open_filter_menu(update, context)
    elif data == "menu_back":
        from bot import main_menu
        await main_menu(update, context)
    else:
        await query.edit_message_text("Unknown menu option.")

search_conv = ConversationHandler(
    entry_points=[CommandHandler('searchmypreferences', open_filter_menu)],
    states={
        SELECT_FILTER: [CallbackQueryHandler(select_filter_cb, pattern="^filter_"), CallbackQueryHandler(select_filter_cb, pattern="^menu_back$")],
        SELECT_GENDER: [CallbackQueryHandler(select_filter_cb, pattern="^gender_"), CallbackQueryHandler(select_filter_cb, pattern="^menu_back$")],
        SELECT_REGION: [CallbackQueryHandler(select_filter_cb, pattern="^region_"), CallbackQueryHandler(select_filter_cb, pattern="^menu_back$")],
        SELECT_COUNTRY: [CallbackQueryHandler(select_filter_cb, pattern="^country_"), CallbackQueryHandler(select_filter_cb, pattern="^menu_back$")],
        SELECT_LANGUAGE: [CallbackQueryHandler(select_filter_cb, pattern="^language_"), CallbackQueryHandler(select_filter_cb, pattern="^menu_back$")]
    },
    fallbacks=[]
)
