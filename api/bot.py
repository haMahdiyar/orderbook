import os
import asyncio
import json
import logging
from dotenv import load_dotenv
import psycopg2
from flask import Flask, request
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)

# Load environment variables
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# --- Environment Variables ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
VERCEL_URL = os.getenv("VERCEL_URL") # We'll set this in Vercel settings

# --- Flask App ---
# This is the 'app' variable that Vercel looks for
app = Flask(__name__)

# --- Database Connection ---
def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL)
    return conn

# --- Conversation States ---
OFFERED_ASSET, OFFERED_AMOUNT, REQUESTED_ASSET, REQUESTED_AMOUNT = range(4)

# --- All Bot Handlers (your existing async functions) ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        'Welcome to the Order Book Bot!\n\n'
        'Use /sell to create a new order.\n'
        'Use /orders to view all active orders.\n'
        'Use /myorders to manage your own orders.'
    )

async def sell_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [
        [InlineKeyboardButton("Million Toman", callback_data="Million Toman")],
        [InlineKeyboardButton("Clean USD", callback_data="Clean USD")],
        [InlineKeyboardButton("Dirty USD", callback_data="Dirty USD")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('Please choose the asset you are OFFERING:', reply_markup=reply_markup)
    return OFFERED_ASSET

async def received_offered_asset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data['asset_offered'] = query.data
    await query.edit_message_text(text=f"You are offering: {query.data}.\n\nPlease enter the AMOUNT you are offering:")
    return OFFERED_AMOUNT

async def received_offered_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        amount = float(update.message.text)
        if amount <= 0: raise ValueError
        context.user_data['amount_offered'] = amount
        keyboard = [
            [InlineKeyboardButton("Million Toman", callback_data="Million Toman")],
            [InlineKeyboardButton("Clean USD", callback_data="Clean USD")],
            [InlineKeyboardButton("Dirty USD", callback_data="Dirty USD")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text('Now, please choose the asset you are REQUESTING:', reply_markup=reply_markup)
        return REQUESTED_ASSET
    except ValueError:
        await update.message.reply_text('Invalid number. Please enter a positive amount.')
        return OFFERED_AMOUNT

async def received_requested_asset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == context.user_data['asset_offered']:
        await query.edit_message_text("The requested asset cannot be the same as the offered asset. Please start over with /sell.")
        return ConversationHandler.END
    context.user_data['asset_requested'] = query.data
    await query.edit_message_text(text=f"You are requesting: {query.data}.\n\nPlease enter the AMOUNT you are requesting:")
    return REQUESTED_AMOUNT

async def received_requested_amount_and_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        amount = float(update.message.text)
        if amount <= 0: raise ValueError
        context.user_data['amount_requested'] = amount
    except ValueError:
        await update.message.reply_text('Invalid number. Please enter a positive amount.')
        return REQUESTED_AMOUNT
    ud = context.user_data
    user = update.effective_user
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO orders (seller_id, seller_username, asset_offered, amount_offered, asset_requested, amount_requested) 
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (user.id, f"@{user.username}", ud['asset_offered'], ud['amount_offered'], ud['asset_requested'], ud['amount_requested'])
        )
        conn.commit()
        final_message = (
            f"✅ Order created successfully!\n\n"
            f"🔹 You Offer: {ud['amount_offered']:,.0f} {ud['asset_offered']}\n"
            f"🔸 You Request: {ud['amount_requested']:,.0f} {ud['asset_requested']}"
        )
        await update.message.reply_text(final_message)
    except Exception as e:
        logging.error(f"DB Error on order save: {e}")
        await update.message.reply_text("An error occurred. Could not save the order.")
    finally:
        if 'cur' in locals(): cur.close()
        if 'conn' in locals(): conn.close()
        ud.clear()
    return ConversationHandler.END

async def list_orders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("Million Toman", callback_data="filter_Million Toman")],
        [InlineKeyboardButton("Clean USD", callback_data="filter_Clean USD")],
        [InlineKeyboardButton("Dirty USD", callback_data="filter_Dirty USD")],
        [InlineKeyboardButton("All Orders", callback_data="filter_All")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('Please choose which asset you want to see offers for:', reply_markup=reply_markup)

async def show_filtered_orders(query, asset_filter, context):
    conn = get_db_connection()
    cur = conn.cursor()
    if asset_filter == "All":
        cur.execute("SELECT id, amount_offered, asset_offered, amount_requested, asset_requested FROM orders WHERE status = 'active' ORDER BY created_at DESC")
        title = "--- All Active Orders ---"
    else:
        cur.execute("SELECT id, amount_offered, asset_offered, amount_requested, asset_requested FROM orders WHERE status = 'active' AND asset_offered = %s ORDER BY created_at DESC", (asset_filter,))
        title = f"--- Orders Offering {asset_filter} ---"
    orders = cur.fetchall()
    cur.close()
    conn.close()
    if not orders:
        await query.edit_message_text(f'There are currently no orders offering {asset_filter}.')
        return
    await query.edit_message_text(title)
    for order in orders:
        order_id, amount_off, asset_off, amount_req, asset_req = order
        text = (f"🛒 **Order ID: {order_id}**\n\n🔹 **Offering:** `{amount_off:,.0f} {asset_off}`\n🔸 **Requesting:** `{amount_req:,.0f} {asset_req}`")
        keyboard = [[InlineKeyboardButton("I want this deal", callback_data=f"buy_{order_id}")]]
        await context.bot.send_message(chat_id=query.message.chat_id, text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, amount_offered, asset_offered, amount_requested, asset_requested FROM orders WHERE seller_id = %s AND status = 'active' ORDER BY created_at DESC", (user_id,))
    orders = cur.fetchall()
    cur.close()
    conn.close()
    if not orders:
        await update.message.reply_text("You don't have any active orders.")
        return
    await update.message.reply_text("--- Your Active Orders ---")
    for order in orders:
        order_id, amount_off, asset_off, amount_req, asset_req = order
        text = (f"📋 **Order ID: {order_id}**\n🔹 **Offering:** `{amount_off:,.0f} {asset_off}`\n🔸 **Requesting:** `{amount_req:,.0f} {asset_req}`")
        keyboard = [[InlineKeyboardButton("❌ Delete this Order", callback_data=f"delete_{order_id}")]]
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def handle_button_clicks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    action, data = query.data.split('_', 1)
    if action == "filter":
        await show_filtered_orders(query, data, context)
        return
    conn = get_db_connection()
    cur = conn.cursor()
    if action == "delete":
        order_id = int(data)
        user_id = query.from_user.id
        cur.execute("UPDATE orders SET status = 'cancelled' WHERE id = %s AND seller_id = %s RETURNING id", (order_id, user_id))
        if cur.fetchone():
            conn.commit()
            await query.edit_message_text(f"✅ Order #{order_id} has been successfully deleted.")
        else:
            await query.edit_message_text("Error: Order not found or you don't have permission.")
    elif action == "buy":
        order_id = int(data)
        buyer = query.from_user
        cur.execute("UPDATE orders SET status = 'pending' WHERE id = %s AND status = 'active' RETURNING seller_id, amount_offered, asset_offered, amount_requested, asset_requested", (order_id,))
        order_details = cur.fetchone()
        conn.commit()
        if order_details:
            seller_id, ao, aso, ar, asr = order_details
            text_to_seller = (f"🔔 Buyer found!\n\n🔸 Order: Offer `{ao:,.0f} {aso}` for `{ar:,.0f} {asr}`\n👤 Buyer: @{buyer.username}\n\nConfirm deal?")
            keyboard = [[InlineKeyboardButton("✅ Confirm", callback_data=f"confirm_{order_id}_{buyer.id}"), InlineKeyboardButton("❌ Reject", callback_data=f"reject_{order_id}_{buyer.id}")]]
            await context.bot.send_message(seller_id, text_to_seller, reply_markup=InlineKeyboardMarkup(keyboard))
            await query.edit_message_text("✅ Your purchase request has been sent! Please wait for the seller to respond.")
        else:
            await query.edit_message_text("❌ This order is no longer available.")
    elif action == "confirm":
        order_id, buyer_id = map(int, data.split('_'))
        cur.execute("UPDATE orders SET status = 'closed', closed_at = NOW() WHERE id = %s RETURNING seller_username", (order_id,))
        seller_username_tuple = cur.fetchone()
        if seller_username_tuple:
            seller_username = seller_username_tuple[0]
            conn.commit()
            buyer_info = await context.bot.get_chat(buyer_id)
            await query.edit_message_text(f"✅ Deal confirmed. This order is now closed.")
            await context.bot.send_message(query.from_user.id, f"👤 Buyer's Username: @{buyer_info.username}")
            await context.bot.send_message(buyer_id, f"✅ The seller has confirmed your deal.\n👤 Seller's Username: {seller_username}")
        else:
            conn.rollback()
            await query.edit_message_text("Error: Order could not be confirmed.")
    elif action == "reject":
        order_id, buyer_id = map(int, data.split('_'))
        cur.execute("UPDATE orders SET status = 'active' WHERE id = %s", (order_id,))
        conn.commit()
        await query.edit_message_text("❌ Request rejected. Your order is active again.")
        await context.bot.send_message(buyer_id, f"❌ The seller has rejected your request for order #{order_id}.")
    cur.close()
    conn.close()

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text('Operation cancelled.')
    context.user_data.clear()
    return ConversationHandler.END

# --- Bot Application Setup ---
ptb_app = Application.builder().token(BOT_TOKEN).build()

# Add all handlers to the application
sell_conv_handler = ConversationHandler(
    entry_points=[CommandHandler('sell', sell_start)],
    states={
        OFFERED_ASSET: [CallbackQueryHandler(received_offered_asset)],
        OFFERED_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_offered_amount)],
        REQUESTED_ASSET: [CallbackQueryHandler(received_requested_asset)],
        REQUESTED_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_requested_amount_and_save)],
    },
    fallbacks=[CommandHandler('cancel', cancel)],
)
ptb_app.add_handler(CommandHandler("start", start))
ptb_app.add_handler(sell_conv_handler)
ptb_app.add_handler(CommandHandler("orders", list_orders))
ptb_app.add_handler(CommandHandler("myorders", my_orders))
ptb_app.add_handler(CallbackQueryHandler(handle_button_clicks))

# --- Flask Webhook Route ---
@app.route('/', methods=['POST'])
def webhook():
    """Webhook endpoint to receive updates from Telegram."""
    asyncio.run(ptb_app.initialize())
    update_data = json.loads(request.data.decode())
    asyncio.run(ptb_app.process_update(Update.de_json(update_data, ptb_app.bot)))
    return 'ok', 200

# Optional: A route to set the webhook
@app.route('/set_webhook', methods=['GET'])
def set_webhook():
    """Sets the webhook for the bot."""
    webhook_url = f"https://{VERCEL_URL}"
    asyncio.run(ptb_app.bot.set_webhook(url=webhook_url))
    return f"Webhook set to {webhook_url}", 200