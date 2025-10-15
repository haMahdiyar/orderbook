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
    """Establishes a connection to the database."""
    conn = psycopg2.connect(DATABASE_URL)
    return conn

# --- Conversation States ---
AMOUNT, OFFERED, REQUESTED = range(3)

# --- Bot Handlers ---

def start(update: Update, context: CallbackContext) -> None:
    """Sends a welcome message."""
    update.message.reply_text(
        'Welcome to the order bot!\n'
        'Use /sell to create a new order.\n'
        'Use /orders to view all active orders.'
    )

def sell_start(update: Update, context: CallbackContext) -> int:
    """Starts the conversation to create a sell order."""
    update.message.reply_text('Please enter the transaction amount:')
    return AMOUNT

def receive_amount(update: Update, context: CallbackContext) -> int:
    """Receives the transaction amount and asks for the offered asset."""
    try:
        amount = float(update.message.text)
        if amount <= 0:
            raise ValueError
        context.user_data['amount'] = amount
        
        keyboard = [
            [InlineKeyboardButton("Rial", callback_data="Rial")],
            [InlineKeyboardButton("Clean USD", callback_data="Clean USD")],
            [InlineKeyboardButton("Dirty USD", callback_data="Dirty USD")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        update.message.reply_text('What asset are you «offering»?', reply_markup=reply_markup)
        
        return OFFERED
    except ValueError:
        update.message.reply_text('Invalid amount. Please enter a positive number.')
        return AMOUNT

def receive_offered(update: Update, context: CallbackContext) -> int:
    """Receives the offered asset and asks for the requested asset."""
    query = update.callback_query
    query.answer()
    
    context.user_data['asset_offered'] = query.data
    
    keyboard = [
        [InlineKeyboardButton("Rial", callback_data="Rial")],
        [InlineKeyboardButton("Clean USD", callback_data="Clean USD")],
        [InlineKeyboardButton("Dirty USD", callback_data="Dirty USD")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    query.edit_message_text(text=f"You are offering «{query.data}».\n\nNow, what asset are you «requesting»?", reply_markup=reply_markup)
    
    return REQUESTED

def receive_requested_and_save(update: Update, context: CallbackContext) -> int:
    """Receives the requested asset and saves the complete order to the database."""
    query = update.callback_query
    query.answer()

    asset_requested = query.data
    asset_offered = context.user_data['asset_offered']
    amount = context.user_data['amount']
    user = query.from_user

    if asset_requested == asset_offered:
        query.edit_message_text("The offered and requested assets cannot be the same. Please try again with /sell.")
        return ConversationHandler.END

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO orders (seller_id, seller_username, amount, asset_offered, asset_requested) VALUES (%s, %s, %s, %s, %s)",
            (user.id, f"@{user.username}", amount, asset_offered, asset_requested)
        )
        conn.commit()
    except Exception as e:
        logging.error(f"Database error: {e}")
        query.edit_message_text("An error occurred while saving the order. Please try again later.")
    finally:
        if 'cur' in locals(): cur.close()
        if 'conn' in locals(): conn.close()
        context.user_data.clear()

    final_message = f"✅ Your order has been successfully created:\n\n"
    final_message += f"💰 Amount: {amount:,.0f}\n"
    final_message += f"👈 You Offer: {asset_offered}\n"
    final_message += f"👉 You Request: {asset_requested}"
    
    query.edit_message_text(text=final_message)
    
    return ConversationHandler.END

def list_orders(update: Update, context: CallbackContext) -> None:
    """Lists all active orders."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, amount, asset_offered, asset_requested FROM orders WHERE status = 'active' ORDER BY created_at DESC")
    active_orders = cur.fetchall()
    cur.close()
    conn.close()

    if not active_orders:
        update.message.reply_text('There are currently no active orders.')
        return

    update.message.reply_text('--- List of Active Orders ---')
    for order in active_orders:
        order_id, amount, offered, requested = order
        text = (
            f"🛒 **Order ID: {order_id}**\n\n"
            f"💰 **Amount:** {amount:,.0f}\n"
            f"🔸 **Offering:** {offered}\n"
            f"🔹 **Requesting:** {requested}"
        )
        keyboard = [[InlineKeyboardButton("I want to buy", callback_data=f"buy_{order_id}")]]
        update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

def handle_button_clicks(update: Update, context: CallbackContext) -> None:
    """Handles clicks on all inline buttons."""
    query = update.callback_query
    query.answer()
    
    action, data = query.data.split('_', 1)
    
    conn = get_db_connection()
    cur = conn.cursor()

    if action == "buy":
        order_id = int(data)
        buyer = query.from_user
        
        cur.execute("UPDATE orders SET status = 'pending' WHERE id = %s AND status = 'active' RETURNING seller_id, amount, asset_offered, asset_requested", (order_id,))
        order_details = cur.fetchone()
        conn.commit()

        if order_details:
            seller_id, amount, offered, requested = order_details
            text_to_seller = (
                f"🔔 A buyer was found for your order!\n\n"
                f"🔸 Order: {amount:,.0f} ({offered} for {requested})\n"
                f"👤 Buyer's Username: @{buyer.username}\n\n"
                f"Do you confirm this transaction?"
            )
            keyboard = [[
                InlineKeyboardButton("✅ Confirm", callback_data=f"confirm_{order_id}_{buyer.id}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"reject_{order_id}_{buyer.id}")
            ]]
            context.bot.send_message(seller_id, text_to_seller, reply_markup=InlineKeyboardMarkup(keyboard))
            query.edit_message_text(f"Your request for order {order_id} has been sent to the seller. Please wait for confirmation.")
        else:
            query.edit_message_text("This order is no longer available or has been reserved by someone else.")

    elif action == "confirm":
        order_id, buyer_id = map(int, data.split('_'))
        
        # *** CHANGE: Update closed_at field as well ***
        cur.execute("UPDATE orders SET status = 'closed', closed_at = NOW() WHERE id = %s RETURNING seller_username", (order_id,))
        seller_username_tuple = cur.fetchone()
        
        if seller_username_tuple:
            seller_username = seller_username_tuple[0]
            conn.commit()

            buyer_info = context.bot.get_chat(buyer_id)
            query.edit_message_text(f"✅ Transaction confirmed. Buyer's info (@{buyer_info.username}) has been sent to you.\nThis order has been removed from the list.")
            context.bot.send_message(query.from_user.id, f"👤 Buyer's Username: @{buyer_info.username}")
            context.bot.send_message(buyer_id, f"✅ The seller ({seller_username}) has confirmed your transaction.\n👤 Seller's Username: {seller_username}")
        else:
            conn.rollback()
            query.edit_message_text("An error occurred or the order has already been processed.")


    elif action == "reject":
        order_id, buyer_id = map(int, data.split('_'))
        
        cur.execute("UPDATE orders SET status = 'active' WHERE id = %s", (order_id,))
        conn.commit()
        
        query.edit_message_text("❌ Request rejected. Your order is now visible to everyone again.")
        context.bot.send_message(buyer_id, f"❌ Unfortunately, the seller has rejected your request for order #{order_id}.")

    cur.close()
    conn.close()

def cancel(update: Update, context: CallbackContext) -> int:
    """Cancels and ends the conversation."""
    update.message.reply_text('Operation cancelled.')
    context.user_data.clear()
    return ConversationHandler.END


# --- Main Application Setup ---
# This part is for setting up the handlers. Vercel will manage the execution.
def main() -> None:
    pass

# The code inside this block is for local testing and will not run on Vercel.
if "VERCEL" not in os.environ:
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
    
    updater = Updater(os.getenv("BOT_TOKEN"))
    dispatcher = updater.dispatcher

    sell_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('sell', sell_start)],
        states={
            AMOUNT: [MessageHandler(Filters.text & ~Filters.command, receive_amount)],
            OFFERED: [CallbackQueryHandler(receive_offered, pattern='^.*$')],
            REQUESTED: [CallbackQueryHandler(receive_requested_and_save, pattern='^.*$')],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(sell_conv_handler)
    dispatcher.add_handler(CommandHandler("orders", list_orders))
    dispatcher.add_handler(CallbackQueryHandler(handle_button_clicks, pattern='^(buy|confirm|reject)_'))

    print("Bot is polling locally...")
    updater.start_polling()
    updater.idle()