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

last_trade_time = None

# tracking
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
        await bot.send_message(AUTHORIZED_CHAT_ID, msg, reply_markup=reply_markup)

async def wait_new_candle():
    while True:
        now = datetime.now()
        if now.second == 0:
            return
        await asyncio.sleep(0.3)

# =========================
# BALANCE
# =========================

async def get_balance():
    try:
        bal = await client.get_balance()
        return bal
    except:
        return "Error"

# =========================
# SIGNAL (SIMPLE REAL FILTER)
# =========================

async def get_signal(pair):
    try:
        candles = await client.get_candles(pair, TIMEFRAME, 0)
        closes = [float(c["close"]) for c in candles]

        if len(closes) < 10:
            return "WAIT"

        if closes[-1] > closes[-2]:
            return "BUY"
        else:
            return "SELL"

    except:
        return "WAIT"

# =========================
# MARTINGALE (SMART RECOVERY)
# =========================

def calculate_next_amount(loss_amount, payout=0.9):
    # recover loss + profit target
    return round((loss_amount / payout) + INITIAL_AMOUNT, 2)

# =========================
# TRADE
# =========================

async def trade(pair, signal):
    global current_amount, wins, losses, total_trades, cycle_profit

    while True:
        try:
            await send(f"📊 {pair} → {signal} | ${current_amount}")

            trade = await client.buy(
                asset=pair,
                amount=current_amount,
                action=signal.lower(),
                duration=EXPIRY
            )

            await asyncio.sleep(EXPIRY + 3)

            result = await client.check_win(trade)

            total_trades += 1

            if result > 0:
                wins += 1
                cycle_profit += result

                await send(f"✅ WIN ${result} | Total ${
