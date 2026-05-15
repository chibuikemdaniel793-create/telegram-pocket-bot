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

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN missing")

if not SSID:
    raise ValueError("SSID missing")

TIMEFRAME = 60
EXPIRY = 60

ACCOUNT_MODE = "DEMO"

AUTO_TRADE = False
BOT_RUNNING = False

INITIAL_AMOUNT = 10
current_amount = INITIAL_AMOUNT

TARGET_PROFIT = 1000
cycle_profit = 0

AUTHORIZED_CHAT_ID = None

# martingale tracking
last_signal = None
last_pair = None
martingale_active = False

# stats
wins = 0
losses = 0
total_trades = 0

# ================= TELEGRAM =================

bot = Bot(token=TELEGRAM_TOKEN)

keyboard = [
    ["🤖 AUTO", "📢 MANUAL"],
    ["🎮 DEMO", "💵 REAL"],
    ["💰 BALANCE", "📊 STATUS"],
    ["▶ START", "⛔ STOP"],
    ["🔄 RECONNECT"]
]

reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ================= CLIENT =================

client = None

def create_client():
    return AsyncPocketOptionClient(
        ssid=SSID,
        is_demo=(ACCOUNT_MODE == "DEMO")
    )

# ================= UTIL =================

async def send(msg):
    if AUTHORIZED_CHAT_ID:
        try:
            await bot.send_message(AUTHORIZED_CHAT_ID, msg, reply_markup=reply_markup)
        except Exception as e:
            print("Send error:", e)

async def wait_new_candle():
    while datetime.now().second != 0:
        await asyncio.sleep(0.2)

# ================= SIMPLE STRATEGY =================

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

async def execute_trade(pair, signal):
    global current_amount, wins, losses, total_trades
    global cycle_profit, martingale_active

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

            await send(f"✅ WIN ${result}\n💰 Profit: ${cycle_profit}")

            # reset martingale
            current_amount = INITIAL_AMOUNT
            martingale_active = False

            if cycle_profit >= TARGET_PROFIT:
                await send("🎯 TARGET HIT. STOPPED.")
                return

        else:
            losses += 1
            cycle_profit -= current_amount

            await send(f"❌ LOSS -${current_amount}")

            # martingale (recover loss + profit)
            current_amount = current_amount * 2
            martingale_active = True

    except Exception:
        traceback.print_exc()

# ================= LOOP =================

async def trading_loop():
    global client, last_signal, last_pair

    while True:
        try:
            if not BOT_RUNNING:
                await asyncio.sleep(2)
                continue

            if client is None:
                client = create_client()
                await client.connect()
                await send("✅ Connected")

            await wait_new_candle()

            # martingale continues same pair
            if martingale_active and last_pair and last_signal:
                await execute_trade(last_pair, last_signal)
                continue

            for pair in ["EURUSD_otc"]:
                candles = await client.get_candles(pair, TIMEFRAME, 0)
                signal = simple_signal(candles)

                if signal != "WAIT" and AUTO_TRADE:
                    last_signal = signal
                    last_pair = pair
                    await execute_trade(pair, signal)
                    break

        except Exception:
            traceback.print_exc()
            await asyncio.sleep(5)

# ================= HANDLER =================

manual_mode = False

async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global AUTO_TRADE, BOT_RUNNING, AUTHORIZED_CHAT_ID
    global ACCOUNT_MODE, client, manual_mode
    global current_amount

    if update.effective_user.id != OWNER_ID:
        return

    AUTHORIZED_CHAT_ID = update.effective_chat.id
    text = update.message.text

    if text == "🤖 AUTO":
        AUTO_TRADE = True
        manual_mode = False

    elif text == "📢 MANUAL":
        AUTO_TRADE = False
        manual_mode = True
        await update.message.reply_text("Send: PAIR AMOUNT\nExample:\nEURUSD_otc 50")
        return

    elif text == "🎮 DEMO":
        ACCOUNT_MODE = "DEMO"
        client = None

    elif text == "💵 REAL":
        ACCOUNT_MODE = "REAL"
        client = None

    elif text == "▶ START":
        BOT_RUNNING = True

    elif text == "⛔ STOP":
        BOT_RUNNING = False

    elif text == "💰 BALANCE":
        try:
            bal = await client.get_balance()
            await update.message.reply_text(f"💰 Balance: ${bal}")
        except:
            await update.message.reply_text("❌ Balance error")
        return

    elif text == "📊 STATUS":
        await update.message.reply_text(
            f"Trades: {total_trades}\nWins: {wins}\nLosses: {losses}\nProfit: ${cycle_profit}"
        )
        return

    elif text == "🔄 RECONNECT":
        client = None
        await update.message.reply_text("Reconnecting...")
        return

    # manual trade input
    elif manual_mode:
        try:
            pair, amt = text.split()
            amt = float(amt)

            current_amount = amt

            candles = await client.get_candles(pair, TIMEFRAME, 0)
            signal = simple_signal(candles)

            if signal != "WAIT":
                await execute_trade(pair, signal)
            else:
                await update.message.reply_text("No signal")

        except:
            await update.message.reply_text("Format: EURUSD_otc 50")

        return

    await update.message.reply_text("✅ Updated", reply_markup=reply_markup)

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
