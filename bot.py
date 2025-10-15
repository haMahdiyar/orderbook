import os
import logging
from dotenv import load_dotenv
import psycopg2
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Updater,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    Filters,
    CallbackContext,
    ConversationHandler,
)

# Load environment variables from .env file
load_dotenv()

# --- Database Connection ---
DATABASE_URL = os.getenv("DATABASE_URL")

def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL)
    return conn

# --- Conversation States for /sell command ---
OFFERED_ASSET, OFFERED_AMOUNT, REQUESTED_ASSET, REQUESTED_AMOUNT = range(4)

# --- Bot Handlers ---

def start(update: Update, context: CallbackContext) -> None:
    """Sends a welcome message."""
    update.message.reply_text(
        'Welcome to the Order Book Bot!\n\n'
        'Use /sell to create a new order.\n'
        'Use /orders to view all active orders.\n'
        'Use /myorders to manage your own orders.'
    )

def sell_start(update: Update, context: CallbackContext) -> int:
    """Starts the /sell conversation by asking for the asset to offer."""
    keyboard = [
        [InlineKeyboardButton("Million Toman", callback_data="Million Toman")],
        [InlineKeyboardButton("Clean USD", callback_data="Clean USD")],
        [InlineKeyboardButton("Dirty USD", callback_data="Dirty USD")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text('Please choose the asset you are OFFERING:', reply_markup=reply_markup)
    return OFFERED_ASSET

def received_offered_asset(update: Update, context: CallbackContext) -> int:
    """Stores the offered asset and asks for its amount."""
    query = update.callback_query
    query.answer()
    context.user_data['asset_offered'] = query.data
    query.edit_message_text(text=f"You are offering: {query.data}.\n\nPlease enter the AMOUNT you are offering:")
    return OFFERED_AMOUNT

def received_offered_amount(update: Update, context: CallbackContext) -> int:
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
        update.message.reply_text('Now, please choose the asset you are REQUESTING:', reply_markup=reply_markup)
        return REQUESTED_ASSET
    except ValueError:
        update.message.reply_text('Invalid number. Please enter a positive amount.')
        return OFFERED_AMOUNT

def received_requested_asset(update: Update, context: CallbackContext) -> int:
    """Stores the requested asset and asks for its amount."""
    query = update.callback_query
    query.answer()
    
    if query.data == context.user_data['asset_offered']:
        query.edit_message_text("The requested asset cannot be the same as the offered asset. Please start over with /sell.")
        return ConversationHandler.END
        
    context.user_data['asset_requested'] = query.data
    query.edit_message_text(text=f"You are requesting: {query.data}.\n\nPlease enter the AMOUNT you are requesting:")
    return REQUESTED_AMOUNT

def received_requested_amount_and_save(update: Update, context: CallbackContext) -> int:
    """Saves the complete order to the database."""
    try:
        amount = float(update.message.text)
        if amount <= 0: raise ValueError
        context.user_data['amount_requested'] = amount
    except ValueError:
        update.message.reply_text('Invalid number. Please enter a positive amount.')
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
        update.message.reply_text(final_message)
        
    except Exception as e:
        logging.error(f"DB Error on order save: {e}")
        update.message.reply_text("An error occurred. Could not save the order.")
    finally:
        if 'cur' in locals(): cur.close()
        if 'conn' in locals(): conn.close()
        ud.clear()

    return ConversationHandler.END

def list_orders(update: Update, context: CallbackContext) -> None:
    """Lists all active orders."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, amount_offered, asset_offered, amount_requested, asset_requested FROM orders WHERE status = 'active' ORDER BY created_at DESC")
    orders = cur.fetchall()
    cur.close()
    conn.close()

    if not orders:
        update.message.reply_text('There are currently no active orders.')
        return

    update.message.reply_text('--- List of Active Orders ---')
    for order in orders:
        order_id, amount_off, asset_off, amount_req, asset_req = order
        text = (
            f"🛒 **Order ID: {order_id}**\n\n"
            f"🔹 **Offering:** `{amount_off:,.0f} {asset_off}`\n"
            f"🔸 **Requesting:** `{amount_req:,.0f} {asset_req}`"
        )
        keyboard = [[InlineKeyboardButton("I want this deal", callback_data=f"buy_{order_id}")]]
        update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

def my_orders(update: Update, context: CallbackContext) -> None:
    """Lists the user's own active orders and provides an option to delete them."""
    user_id = update.effective_user.id
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, amount_offered, asset_offered, amount_requested, asset_requested FROM orders WHERE seller_id = %s AND status = 'active' ORDER BY created_at DESC", (user_id,))
    orders = cur.fetchall()
    cur.close()
    conn.close()

    if not orders:
        update.message.reply_text("You don't have any active orders.")
        return

    update.message.reply_text("--- Your Active Orders ---")
    for order in orders:
        order_id, amount_off, asset_off, amount_req, asset_req = order
        text = (
            f"📋 **Order ID: {order_id}**\n"
            f"🔹 **Offering:** `{amount_off:,.0f} {asset_off}`\n"
            f"🔸 **Requesting:** `{amount_req:,.0f} {asset_req}`"
        )
        keyboard = [[InlineKeyboardButton("❌ Delete this Order", callback_data=f"delete_{order_id}")]]
        update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

def handle_button_clicks(update: Update, context: CallbackContext) -> None:
    """Handles all button clicks (buy, confirm, reject, delete)."""
    query = update.callback_query
    query.answer()
    
    action, data = query.data.split('_', 1)
    
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
            query.edit_message_text(f"✅ Order #{order_id} has been successfully deleted.")
        else:
            query.edit_message_text("Error: Order not found or you don't have permission to delete it.")

    elif action == "buy":
        # ... [The rest of the logic for buy, confirm, reject is very similar and has been omitted for brevity,
        # but the full code block will contain it] ...
        pass # Placeholder for brevity, the full code has the logic

    # The full logic for buy/confirm/reject is included in the complete code.
    # It's similar to the previous version but adapted for the new table structure.

    # [The full implementation of buy, confirm, reject actions follows]
    if action == "buy":
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
            context.bot.send_message(seller_id, text_to_seller, reply_markup=InlineKeyboardMarkup(keyboard))
            query.edit_message_text(
                f"✅ Your purchase request has been sent!\n\n"
                f"📋 Order #{order_id}\n"
                f"🔹 You want: {ao:,.0f} {aso}\n"
                f"🔸 You will pay: {ar:,.0f} {asr}\n\n"
                f"⏳ Please wait for the seller to confirm or reject your request.\n"
                f"You will be notified as soon as they respond."
            )
        else:
            query.edit_message_text("❌ This order is no longer available.")

    elif action == "confirm":
        order_id, buyer_id = map(int, data.split('_'))
        
        cur.execute("UPDATE orders SET status = 'closed', closed_at = NOW() WHERE id = %s RETURNING seller_username", (order_id,))
        seller_username_tuple = cur.fetchone()
        
        if seller_username_tuple:
            seller_username = seller_username_tuple[0]
            conn.commit()
            buyer_info = context.bot.get_chat(buyer_id)
            query.edit_message_text(f"✅ Deal confirmed. This order is now closed.")
            context.bot.send_message(query.from_user.id, f"👤 Buyer's Username: @{buyer_info.username}")
            context.bot.send_message(buyer_id, f"✅ The seller has confirmed your deal.\n👤 Seller's Username: {seller_username}")
        else:
            conn.rollback()
            query.edit_message_text("Error: Order could not be confirmed.")

    elif action == "reject":
        order_id, buyer_id = map(int, data.split('_'))
        cur.execute("UPDATE orders SET status = 'active' WHERE id = %s", (order_id,))
        conn.commit()
        query.edit_message_text("❌ Request rejected. Your order is active again.")
        context.bot.send_message(buyer_id, f"❌ The seller has rejected your request for order #{order_id}.")

    cur.close()
    conn.close()

def cancel(update: Update, context: CallbackContext) -> int:
    """Cancels and ends the conversation."""
    update.message.reply_text('Operation cancelled.')
    context.user_data.clear()
    return ConversationHandler.END


# --- Main Application Setup ---
def main() -> None:
    pass

if "VERCEL" not in os.environ:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    updater = Updater(os.getenv("BOT_TOKEN"))
    dispatcher = updater.dispatcher

    sell_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('sell', sell_start)],
        states={
            OFFERED_ASSET: [CallbackQueryHandler(received_offered_asset)],
            OFFERED_AMOUNT: [MessageHandler(Filters.text & ~Filters.command, received_offered_amount)],
            REQUESTED_ASSET: [CallbackQueryHandler(received_requested_asset)],
            REQUESTED_AMOUNT: [MessageHandler(Filters.text & ~Filters.command, received_requested_amount_and_save)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(sell_conv_handler)
    dispatcher.add_handler(CommandHandler("orders", list_orders))
    dispatcher.add_handler(CommandHandler("myorders", my_orders))
    dispatcher.add_handler(CallbackQueryHandler(handle_button_clicks))

    print("Bot is polling locally...")
    updater.start_polling()
    updater.idle()