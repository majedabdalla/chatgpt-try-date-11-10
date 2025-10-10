from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from db import get_user, update_user
from admin import approve_premium
from datetime import datetime, timedelta

async def start_upgrade(update: Update, context):
    await update.message.reply_text('Please upload payment proof (photo, screenshot, or document)')

async def handle_proof(update: Update, context):
    user = update.effective_user
    admin_group = int(context.bot_data.get('ADMIN_GROUP_ID'))
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton('Approve', callback_data=f'approve:{user.id}'), InlineKeyboardButton('Decline', callback_data=f'decline:{user.id}')]
    ])
    await context.bot.send_message(chat_id=admin_group, text=f'Payment proof from user {user.id}', reply_markup=kb)
    if update.message.photo or update.message.document:
        await context.bot.copy_message(chat_id=admin_group, from_chat_id=update.effective_chat.id, message_id=update.message.message_id)
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
