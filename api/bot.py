import os
import json
import logging
from dotenv import load_dotenv
import psycopg2
from telegram import Update, Bot
from telegram.ext import Dispatcher, CommandHandler, CallbackQueryHandler, MessageHandler, Filters, ConversationHandler

# Import all handlers from main bot.py
import sys
sys.path.append('..')
from bot import (
    start, sell_start, received_offered_asset, received_offered_amount,
    received_requested_asset, received_requested_amount_and_save,
    list_orders, my_orders, handle_button_clicks, cancel,
    OFFERED_ASSET, OFFERED_AMOUNT, REQUESTED_ASSET, REQUESTED_AMOUNT
)

# Load environment variables
load_dotenv()

# Initialize bot
bot = Bot(token=os.getenv("BOT_TOKEN"))

# Setup dispatcher
dispatcher = Dispatcher(bot, None, workers=0, use_context=True)

# Add handlers
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

def handler(request):
    """Vercel serverless function handler"""
    try:
        # Set webhook on first request if not set
        webhook_url = "https://orderbook-iota.vercel.app/api/bot"
        current_webhook = bot.get_webhook_info()
        if current_webhook.url != webhook_url:
            bot.set_webhook(url=webhook_url)
            
        # Parse the request
        if hasattr(request, 'method'):
            if request.method == "POST":
                update = Update.de_json(json.loads(request.body), bot)
                dispatcher.process_update(update)
        else:
            # Vercel request format
            if request.get('method') == 'POST':
                body = request.get('body', '{}')
                if isinstance(body, str):
                    update_data = json.loads(body)
                else:
                    update_data = body
                update = Update.de_json(update_data, bot)
                dispatcher.process_update(update)
            
        return {
            'statusCode': 200,
            'body': json.dumps({'status': 'ok'})
        }
    except Exception as e:
        logging.error(f"Error in handler: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }

# For Vercel
def app(request):
    return handler(request)