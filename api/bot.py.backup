import os
import json
import logging
from dotenv import load_dotenv
import psycopg2
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ConversationHandler, ContextTypes
from http.server import BaseHTTPRequestHandler

# Load environment variables
load_dotenv()

# Set environment variable for Vercel
os.environ["VERCEL"] = "1"

# --- Database Connection ---
DATABASE_URL = os.getenv("DATABASE_URL")

def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL)
    return conn

# --- Conversation States for /sell command ---
OFFERED_ASSET, OFFERED_AMOUNT, REQUESTED_ASSET, REQUESTED_AMOUNT = range(4)

# --- Bot Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message."""
    await update.message.reply_text(
        'Welcome to the Order Book Bot!\n\n'
        'Use /sell to create a new order.\n'
        'Use /orders to view all active orders.\n'
        'Use /myorders to manage your own orders.'
    )

async def sell_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the /sell conversation by asking for the asset to offer."""
    keyboard = [
        [InlineKeyboardButton("Million Toman", callback_data="Million Toman")],
        [InlineKeyboardButton("Clean USD", callback_data="Clean USD")],
        [InlineKeyboardButton("Dirty USD", callback_data="Dirty USD")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('Please choose the asset you are OFFERING:', reply_markup=reply_markup)
    return OFFERED_ASSET

async def received_offered_asset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the offered asset and asks for its amount."""
    query = update.callback_query
    await query.answer()
    context.user_data['asset_offered'] = query.data
    await query.edit_message_text(text=f"You are offering: {query.data}.\n\nPlease enter the AMOUNT you are offering:")
    return OFFERED_AMOUNT

async def received_offered_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the offered amount and asks for the requested asset."""
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
    """Stores the requested asset and asks for its amount."""
    query = update.callback_query
    await query.answer()
    
    if query.data == context.user_data['asset_offered']:
        await query.edit_message_text("The requested asset cannot be the same as the offered asset. Please start over with /sell.")
        return ConversationHandler.END
        
    context.user_data['asset_requested'] = query.data
    await query.edit_message_text(text=f"You are requesting: {query.data}.\n\nPlease enter the AMOUNT you are requesting:")
    return REQUESTED_AMOUNT

async def received_requested_amount_and_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Saves the complete order to the database."""
    try:
        amount = float(update.message.text)
        if amount <= 0: raise ValueError
        context.user_data['amount_requested'] = amount
    except ValueError:
        await update.message.reply_text('Invalid number. Please enter a positive amount.')
        return REQUESTED_AMOUNT

    # All data collected, now save to DB
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
    """Shows asset selection menu for filtering orders."""
    keyboard = [
        [InlineKeyboardButton("Million Toman", callback_data="filter_Million Toman")],
        [InlineKeyboardButton("Clean USD", callback_data="filter_Clean USD")],
        [InlineKeyboardButton("Dirty USD", callback_data="filter_Dirty USD")],
        [InlineKeyboardButton("All Orders", callback_data="filter_All")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('Please choose which asset you want to see offers for:', reply_markup=reply_markup)

async def show_filtered_orders(query, asset_filter, context):
    """Shows orders filtered by asset type."""
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
        if asset_filter == "All":
            await query.edit_message_text('There are currently no active orders.')
        else:
            await query.edit_message_text(f'There are currently no orders offering {asset_filter}.')
        return

    await query.edit_message_text(title)
    for order in orders:
        order_id, amount_off, asset_off, amount_req, asset_req = order
        text = (
            f"🛒 **Order ID: {order_id}**\n\n"
            f"🔹 **Offering:** `{amount_off:,.0f} {asset_off}`\n"
            f"🔸 **Requesting:** `{amount_req:,.0f} {asset_req}`"
        )
        keyboard = [[InlineKeyboardButton("I want this deal", callback_data=f"buy_{order_id}")]]
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

async def my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lists the user's own active orders and provides an option to delete them."""
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
        text = (
            f"📋 **Order ID: {order_id}**\n"
            f"🔹 **Offering:** `{amount_off:,.0f} {asset_off}`\n"
            f"🔸 **Requesting:** `{amount_req:,.0f} {asset_req}`"
        )
        keyboard = [[InlineKeyboardButton("❌ Delete this Order", callback_data=f"delete_{order_id}")]]
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def handle_button_clicks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles all button clicks (buy, confirm, reject, delete, filter)."""
    query = update.callback_query
    await query.answer()
    
    action, data = query.data.split('_', 1)
    
    if action == "filter":
        # Handle asset filtering for orders
        asset_filter = data
        await show_filtered_orders(query, asset_filter, context)
        return
    
    conn = get_db_connection()
    cur = conn.cursor()

    if action == "delete":
        order_id = int(data)
        user_id = query.from_user.id
        
        # Security check: Ensure the user owns this order
        cur.execute("UPDATE orders SET status = 'cancelled' WHERE id = %s AND seller_id = %s RETURNING id", (order_id, user_id))
        deleted_order = cur.fetchone()
        conn.commit()
        
        if deleted_order:
            await query.edit_message_text(f"✅ Order #{order_id} has been successfully deleted.")
        else:
            await query.edit_message_text("Error: Order not found or you don't have permission to delete it.")

    elif action == "buy":
        order_id = int(data)
        buyer = query.from_user
        
        cur.execute("UPDATE orders SET status = 'pending' WHERE id = %s AND status = 'active' RETURNING seller_id, amount_offered, asset_offered, amount_requested, asset_requested", (order_id,))
        order_details = cur.fetchone()
        conn.commit()

        if order_details:
            seller_id, ao, aso, ar, asr = order_details
            text_to_seller = (
                f"🔔 A buyer was found for your order!\n\n"
                f"🔸 Order: Offer `{ao:,.0f} {aso}` for `{ar:,.0f} {asr}`\n"
                f"👤 Buyer's Username: @{buyer.username}\n\n"
                f"Do you confirm this deal?"
            )
            keyboard = [[
                InlineKeyboardButton("✅ Confirm", callback_data=f"confirm_{order_id}_{buyer.id}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"reject_{order_id}_{buyer.id}")
            ]]
            await context.bot.send_message(seller_id, text_to_seller, reply_markup=InlineKeyboardMarkup(keyboard))
            await query.edit_message_text(
                f"✅ Your purchase request has been sent!\n\n"
                f"📋 Order #{order_id}\n"
                f"🔹 You want: {ao:,.0f} {aso}\n"
                f"🔸 You will pay: {ar:,.0f} {asr}\n\n"
                f"⏳ Please wait for the seller to confirm or reject your request.\n"
                f"You will be notified as soon as they respond."
            )
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
    """Cancels and ends the conversation."""
    await update.message.reply_text('Operation cancelled.')
    context.user_data.clear()
    return ConversationHandler.END

# Initialize bot
bot = Bot(token=os.getenv("BOT_TOKEN"))

# Create application
application = Application.builder().token(os.getenv("BOT_TOKEN")).build()

# Add handlers
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

application.add_handler(CommandHandler("start", start))
application.add_handler(sell_conv_handler)
application.add_handler(CommandHandler("orders", list_orders))
application.add_handler(CommandHandler("myorders", my_orders))
application.add_handler(CallbackQueryHandler(handle_button_clicks))

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            # Set webhook on first request if not set
            webhook_url = "https://orderbook-iota.vercel.app/api/bot"
            current_webhook = bot.get_webhook_info()
            if current_webhook.url != webhook_url:
                bot.set_webhook(url=webhook_url)
            
            # Read request body
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            
            # Parse update
            update_data = json.loads(post_data.decode('utf-8'))
            update = Update.de_json(update_data, bot)
            
            # Process update with application
            import asyncio
            asyncio.run(application.process_update(update))
            
            # Send response
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'ok'}).encode())
            
        except Exception as e:
            logging.error(f"Error in webhook handler: {e}")
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': str(e)}).encode())

    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'status': 'Bot is running'}).encode())