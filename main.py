# ================= FIXED VERSION =================

import os
import asyncio
import traceback
from datetime import datetime

from pocketoptionapi_async import AsyncPocketOptionClient
from telegram import Update, Bot, ReplyKeyboardMarkup
from telegram.ext import Application, ContextTypes, MessageHandler, filters

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
SSID = os.getenv("SSID")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

TIMEFRAME = 60
EXPIRY = 60

ACCOUNT_MODE = "DEMO"
BOT_RUNNING = False
AUTO_TRADE = False

current_amount = 10
TARGET_PROFIT = 100
cycle_profit = 0

AUTHORIZED_CHAT_ID = None

client = None

# ===== KEYBOARD =====
keyboard = [
    ["🤖 AUTO", "📢 MANUAL"],
    ["🎮 DEMO", "💵 REAL"],
    ["💰 BALANCE", "📊 STATUS"],
    ["💵 AMOUNT"],
    ["▶ START", "⛔ STOP"],
    ["🔄 RECONNECT"]
]

reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

bot = Bot(token=TELEGRAM_TOKEN)

# ===== CREATE CLIENT =====
def create_client():
    return AsyncPocketOptionClient(
        ssid=SSID,
        is_demo=(ACCOUNT_MODE == "DEMO")
    )

# ===== SEND =====
async def send(msg):
    if AUTHORIZED_CHAT_ID:
        try:
            await bot.send_message(AUTHORIZED_CHAT_ID, msg, reply_markup=reply_markup)
        except:
            pass

# ===== STRATEGY =====
def signal(candles):
    if len(candles) < 2:
        return "WAIT"

    if candles[-1]["close"] > candles[-2]["close"]:
        return "BUY"
    else:
        return "SELL"

# ===== CONNECT =====
async def connect():
    global client
    try:
        client = create_client()
        await client.connect()
        await send("✅ Connected to PocketOption")
        return True
    except Exception as e:
        await send(f"❌ Connection failed\n{str(e)}")
        return False

# ===== BALANCE =====
async def get_balance():
    try:
        if client is None:
            await send("❌ Not connected")
            return

        bal = await client.get_balance()
        await send(f"💰 Balance: ${bal}")
    except Exception as e:
        await send(f"❌ Balance error\n{str(e)}")

# ===== TRADE =====
async def trade(pair):
    global current_amount, cycle_profit

    try:
        candles = await client.get_candles(pair, TIMEFRAME, 0)
        sig = signal(candles)

        await send(f"📊 {pair} → {sig} | ${current_amount}")

        t = await client.buy(
            asset=pair,
            amount=current_amount,
            action=sig.lower(),
            duration=EXPIRY
        )

        await asyncio.sleep(EXPIRY + 3)

        result = await client.check_win(t)

        if result > 0:
            cycle_profit += result
            await send(f"✅ WIN ${result}")

            current_amount = 10

        else:
            cycle_profit -= current_amount
            await send(f"❌ LOSS ${current_amount}")

            # MARTINGALE (recover loss + profit)
            current_amount = abs(cycle_profit) + 10

    except Exception as e:
        await send(f"❌ Trade error\n{str(e)}")

# ===== LOOP =====
async def loop():
    global BOT_RUNNING

    while True:
        if not BOT_RUNNING:
            await asyncio.sleep(2)
            continue

        if client is None:
            ok = await connect()
            if not ok:
                await asyncio.sleep(5)
                continue

        await trade("EURUSD_otc")
        await asyncio.sleep(5)

# ===== HANDLER =====
setting_amount = False
manual_mode = False

async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global BOT_RUNNING, AUTO_TRADE, ACCOUNT_MODE
    global AUTHORIZED_CHAT_ID, current_amount
    global setting_amount, manual_mode

    if update.effective_user.id != OWNER_ID:
        return

    AUTHORIZED_CHAT_ID = update.effective_chat.id
    text = update.message.text

    # ===== AMOUNT INPUT =====
    if setting_amount:
        try:
            current_amount = float(text)
            await update.message.reply_text(f"✅ Amount set: ${current_amount}")
        except:
            await update.message.reply_text("❌ Invalid amount")

        setting_amount = False
        return

    # ===== MANUAL INPUT =====
    if manual_mode:
        try:
            pair = text.strip()
            await trade(pair)
        except:
            await update.message.reply_text("❌ Send only pair (e.g. EURUSD_otc)")
        return

    # ===== BUTTONS =====
    if text == "💵 AMOUNT":
        setting_amount = True
        await update.message.reply_text("Enter amount:")
        return

    elif text == "🤖 AUTO":
        AUTO_TRADE = True
        manual_mode = False
        await update.message.reply_text("Auto mode ON")

    elif text == "📢 MANUAL":
        manual_mode = True
        AUTO_TRADE = False
        await update.message.reply_text("Send pair only (e.g. EURUSD_otc)")

    elif text == "🎮 DEMO":
        ACCOUNT_MODE = "DEMO"
        await connect()

    elif text == "💵 REAL":
        ACCOUNT_MODE = "REAL"
        await connect()

    elif text == "▶ START":
        BOT_RUNNING = True
        await update.message.reply_text("Bot started")

    elif text == "⛔ STOP":
        BOT_RUNNING = False
        await update.message.reply_text("Bot stopped")

    elif text == "💰 BALANCE":
        await get_balance()

    elif text == "🔄 RECONNECT":
        ok = await connect()
        if ok:
            await update.message.reply_text("Reconnected")
        else:
            await update.message.reply_text("Reconnect failed")

# ===== MAIN =====
async def start_bg(app):
    asyncio.create_task(loop())

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).post_init(start_bg).build()
    app.add_handler(MessageHandler(filters.TEXT, handler))
    app.run_polling()

if __name__ == "__main__":
    main()