"""Run this once after deploying, to point Telegram at your /webhook route.

Usage:
    TELEGRAM_BOT_TOKEN=xxx PUBLIC_BASE_URL=https://yourapp.onrender.com python set_webhook.py
"""
import os
import requests

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
BASE_URL = os.environ["PUBLIC_BASE_URL"].rstrip("/")

r = requests.post(
    f"https://api.telegram.org/bot{TOKEN}/setWebhook",
    json={"url": f"{BASE_URL}/webhook"},
)
print(r.status_code, r.json())
