import os
import asyncio
import traceback
from datetime import datetime

from pocketoptionapi_async import AsyncPocketOptionClient
from telegram import Update, Bot, ReplyKeyboardMarkup
from telegram.ext import Application, ContextTypes, MessageHandler, filters

# ================= CONFIG =================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
SSID = os.getenv("SSID")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

TIMEFRAME = 60
EXPIRY = 60

ACCOUNT_MODE = "DEMO"

AUTO_TRADE = False
BOT_RUNNING = False

BASE_AMOUNT = 10
current_amount = BASE_AMOUNT

AUTHORIZED_CHAT_ID = None

# martingale
martingale_active = False
last_signal = None
last_pair = None

# stats
wins = 0
losses = 0
total_trades = 0

bot = Bot(token=TELEGRAM_TOKEN)

keyboard = [
    ["🤖 AUTO", "📢 MANUAL"],
    ["🎮 DEMO", "💵 REAL"],
    ["💰 BALANCE", "📊 STATUS"],
    ["▶ START", "⛔ STOP"]
]

reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ================= CLIENT =================

def create_client():
    return AsyncPocketOptionClient(
        ssid=SSID.strip(),
        is_demo=(ACCOUNT_MODE == "DEMO")
    )

# ================= UTIL =================

async def send(msg):
    if AUTHORIZED_CHAT_ID:
        await bot.send_message(AUTHORIZED_CHAT_ID, msg)

async def wait_new_candle():
    while datetime.now().second != 0:
        await asyncio.sleep(0.2)

# ================= STRATEGY =================

def simple_signal(candles):
    if not candles or len(candles) < 5:
        return "WAIT"

    closes = [float(c["close"]) for c in candles]

    if closes[-1] > closes[-2]:
        return "BUY"
    elif closes[-1] < closes[-2]:
        return "SELL"

    return "WAIT"

# ================= TRADE =================

async def execute_trade(pair, signal, amount):
    global current_amount, martingale_active
    global wins, losses, total_trades

    try:
        client = create_client()
        await client.connect()

        await send(f"{pair} → {signal} | ${amount}")

        trade = await client.buy(
            asset=pair,
            amount=amount,
            action=signal.lower(),
            duration=EXPIRY
        )

        await asyncio.sleep(EXPIRY + 3)

        result = await client.check_win(trade)
        await client.disconnect()

        total_trades += 1

        if result > 0:
            wins += 1
            await send(f"WIN ${result}")

            current_amount = BASE_AMOUNT
            martingale_active = False

        else:
            losses += 1
            await send(f"LOSS -${amount}")

            current_amount = amount * 2
            martingale_active = True

    except:
        traceback.print_exc()
        await send("Trade error")

# ================= LOOP =================

async def trading_loop():
    global last_pair, last_signal

    while True:
        try:
            if not BOT_RUNNING:
                await asyncio.sleep(2)
                continue

            await wait_new_candle()

            # martingale
            if martingale_active and last_pair:
                await execute_trade(last_pair, last_signal, current_amount)
                continue

            if not AUTO_TRADE:
                await asyncio.sleep(1)
                continue

            client = create_client()
            await client.connect()

            pair = "EURUSD_otc"
            candles = await client.get_candles(pair, TIMEFRAME, 0)

            signal = simple_signal(candles)

            if signal != "WAIT":
                last_pair = pair
                last_signal = signal

                await client.disconnect()
                await execute_trade(pair, signal, BASE_AMOUNT)

        except:
            traceback.print_exc()
            await asyncio.sleep(5)

# ================= HANDLER =================

manual_mode = False

async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global AUTO_TRADE, BOT_RUNNING, AUTHORIZED_CHAT_ID
    global BASE_AMOUNT, current_amount, manual_mode

    if update.effective_user.id != OWNER_ID:
        return

    AUTHORIZED_CHAT_ID = update.effective_chat.id
    text = update.message.text.strip()

    # SET AMOUNT
    if text.startswith("AMOUNT"):
        try:
            amt = float(text.split()[1])
            BASE_AMOUNT = amt
            current_amount = amt
            await update.message.reply_text(f"Amount set to ${amt}")
        except:
            await update.message.reply_text("Use: AMOUNT 50")
        return

    if text == "🤖 AUTO":
        AUTO_TRADE = True
        manual_mode = False
        await update.message.reply_text("Auto mode ON")

    elif text == "📢 MANUAL":
        AUTO_TRADE = False
        manual_mode = True
        await update.message.reply_text("Send: EURUSD_otc 50")
        return

    elif text == "▶ START":
        BOT_RUNNING = True
        await update.message.reply_text("Bot started")

    elif text == "⛔ STOP":
        BOT_RUNNING = False
        await update.message.reply_text("Bot stopped")

    elif text == "💰 BALANCE":
        try:
            client = create_client()
            await client.connect()
            bal = await client.get_balance()
            await client.disconnect()
            await update.message.reply_text(f"Balance: ${bal}")
        except:
            await update.message.reply_text("Balance error")
        return

    # MANUAL SIGNAL ONLY
    elif manual_mode:
        try:
            pair, amt = text.split()
            amt = float(amt)

            client = create_client()
            await client.connect()

            candles = await client.get_candles(pair, TIMEFRAME, 0)
            signal = simple_signal(candles)

            await client.disconnect()

            await update.message.reply_text(
                f"{pair} → {signal}\nAmount: ${amt}"
            )

        except:
            await update.message.reply_text("Format: EURUSD_otc 50")

        return

# ================= MAIN =================

async def start_bg(app):
    asyncio.create_task(trading_loop())

def main():
    app = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .post_init(start_bg)
        .build()
    )

    app.add_handler(MessageHandler(filters.TEXT, handler))

    print("Bot Running...")
    app.run_polling()

if __name__ == "__main__":
    main()