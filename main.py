import os
import asyncio
import nest_asyncio
import traceback
from datetime import datetime

from pocketoptionapi_async import AsyncPocketOptionClient
from telegram import Update, Bot, ReplyKeyboardMarkup
from telegram.ext import Application, ContextTypes, MessageHandler, filters

# =========================
# CONFIG
# =========================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
SSID = os.getenv("SSID")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

if not TELEGRAM_TOKEN:
    raise ValueError("Missing TELEGRAM_TOKEN")

if not SSID:
    raise ValueError("Missing SSID")

TIMEFRAME = 60
EXPIRY = 60

ACCOUNT_MODE = "DEMO"

AUTO_TRADE = False
BOT_RUNNING = False
AUTHORIZED_CHAT_ID = None

INITIAL_AMOUNT = 10
current_amount = INITIAL_AMOUNT

TARGET_PROFIT = 1000
cycle_profit = 0

last_trade_minute = None

wins = 0
losses = 0
total_trades = 0

client = None

bot = Bot(token=TELEGRAM_TOKEN)

keyboard = [
    ["🤖 AUTO", "📢 MANUAL"],
    ["🎮 DEMO", "💵 REAL"],
    ["💰 BALANCE", "📊 STATUS"],
    ["▶ START", "⛔ STOP"],
    ["🔄 RECONNECT"]
]

reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# =========================
# CLIENT
# =========================

def create_client():
    return AsyncPocketOptionClient(
        ssid=SSID,
        is_demo=(ACCOUNT_MODE == "DEMO")
    )

# =========================
# UTIL
# =========================

async def send(msg):
    if AUTHORIZED_CHAT_ID:
        try:
            await bot.send_message(AUTHORIZED_CHAT_ID, msg, reply_markup=reply_markup)
        except Exception as e:
            print("Send error:",
