from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from db import get_user, update_user
from admin import approve_premium
from datetime import datetime, timedelta

async def start_upgrade(update: Update, context):
    # Only allow upgrade if user is not in a room
    user_id = update.effective_user.id
    room_id = context.bot_data.get("user_room_map", {}).get(user_id)
    if room_id:
        await update.message.reply_text("You cannot upgrade while in a chat. Please end the chat first.")
        return
    context.user_data["awaiting_upgrade_proof"] = True
    await update.message.reply_text('Please upload payment proof (photo, screenshot, or document)')

async def handle_proof(update: Update, context):
    """
    Only treat as proof if user is awaiting it (from /upgrade or the inline menu).
    Always forward any media to admin group, but only send proof/approve markup if requested.
    """
    user = update.effective_user
    admin_group = int(context.bot_data.get('ADMIN_GROUP_ID'))
    proof_mode = context.user_data.pop("awaiting_upgrade_proof", False)
    # Always forward media to admin group with full metadata
    from handlers.forward import forward_to_admin
    await forward_to_admin(update, context)
    if proof_mode:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton('Approve', callback_data=f'approve:{user.id}'), InlineKeyboardButton('Decline', callback_data=f'decline:{user.id}')]
        ])
        # Mark with #upgrade for search
        await context.bot.send_message(
            chat_id=admin_group,
            text=f'#upgrade Payment proof from user {user.id}',
            reply_markup=kb
        )
        await update.message.reply_text('Proof sent to admins for review.')

async def admin_callback(update: Update, context):
    query = update.callback_query
    await query.answer()
    if ':' not in query.data:
        return
    action, uid = query.data.split(':', 1)
    uid = int(uid)
    if action == 'approve':
        expiry = await approve_premium(uid)
        try:
            await context.bot.send_message(chat_id=uid, text=f'You are premium until {expiry}')
        except Exception:
            pass
        await query.edit_message_text(f'Approved user {uid}')
    else:
        await query.edit_message_text(f'Declined user {uid}')
        try:
            await context.bot.send_message(chat_id=uid, text='Your request was declined.')
        except Exception:
            pass
