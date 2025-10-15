import os
from dotenv import load_dotenv
from telegram import Bot, BotCommand

# Load environment variables from .env file
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

def set_bot_commands():
    """Sets the bot's command menu in English."""
    if not BOT_TOKEN:
        print("Error: BOT_TOKEN not found in .env file.")
        return

    try:
        bot = Bot(token=BOT_TOKEN)
        
        # Define the list of English commands
        commands = [
            BotCommand("start", "Restart the bot"),
            BotCommand("sell", "Create a new order"),
            BotCommand("orders", "View all active orders"),
            BotCommand("myorders", "Manage your active orders"), # New command
            BotCommand("cancel", "Cancel the current operation"),
        ]
        
        bot.set_my_commands(commands)
        
        print("Bot commands have been set successfully in English!")
        
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    set_bot_commands()