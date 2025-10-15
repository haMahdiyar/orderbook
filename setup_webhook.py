import os
import requests
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = "https://orderbook-iota.vercel.app/api/bot"

# Set webhook
response = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook", {
    "url": WEBHOOK_URL
})

print("Webhook setup response:", response.json())

# Check webhook info
response = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getWebhookInfo")
print("Webhook info:", response.json())