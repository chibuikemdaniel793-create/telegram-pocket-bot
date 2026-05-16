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

# AUTO amount + martingale
BASE_AMOUNT = 10
current_amount = BASE_AMOUNT

AUTHORIZED_CHAT_ID = None

# martingale tracking
martingale_active = False
last_signal = None
last_pair = None

# stats
wins = 0
losses = 0
total_trades = 0
cycle_profit = 0

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

def create_client():
    return AsyncPocketOptionClient(
        ssid=SSID.strip(),
        is_demo=(ACCOUNT_MODE == "DEMO")
    )

# ================= UTIL =================

async def send(msg):
    if AUTHORIZED_CHAT_ID:
        try:
            await bot.send_message(AUTHORIZED_CHAT_ID, msg, reply_markup=reply_markup)
        except Exception as e:
            print(e)

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
    global wins, losses, total_trades, cycle_profit
    global current_amount, martingale_active

    try:
        client = create_client()
        await client.connect()

        await send(f"{pair} {signal} ${amount}")

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
            cycle_profit += result
            await send(f"WIN ${result}")

            # reset martingale
            current_amount = BASE_AMOUNT
            martingale_active = False

        else:
            losses += 1
            cycle_profit -= amount
            await send(f"LOSS -${amount}")

            # martingale
            current_amount = amount * 2
            martingale_active = True

    except Exception:
        traceback.print_exc()
        await send("Trade error")

# ================= LOOP =================

async def trading_loop():
    global last_pair, last_signal, current_amount

    while True:
        try:
            if not BOT_RUNNING:
                await asyncio.sleep(2)
                continue

            await wait_new_candle()

            # continue martingale immediately
            if martingale_active and last_pair and last_signal:
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
    global ACCOUNT_MODE, manual_mode
    global BASE_AMOUNT, current_amount

    if update.effective_user.id != OWNER_ID:
        return

    AUTHORIZED_CHAT_ID = update.effective_chat.id
    text = update.message.text.strip()

    # set auto amount
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

    elif text == "📢 MANUAL":
        AUTO_TRADE = False
        manual_mode = True
        await update.message.reply_text("Format:\nEURUSD_otc 50 BUY")
        return

    elif text == "🎮 DEMO":
        ACCOUNT_MODE = "DEMO"

    elif text == "💵 REAL":
        ACCOUNT_MODE = "REAL"

    elif text == "▶ START":
        BOT_RUNNING = True

    elif text == "⛔ STOP":
        BOT_RUNNING = False

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

    elif text == "📊 STATUS":
        await update.message.reply_text(
            f"Trades: {total_trades}\nWins: {wins}\nLosses: {losses}\nProfit: ${cycle_profit}"
        )
        return

    elif text == "🔄 RECONNECT":
        await update.message.reply_text("Reconnect requested")
        return

    # manual trade: PAIR AMOUNT BUY/SELL
    elif manual_mode:
        try:
            pair, amt, direction = text.split()
            amt = float(amt)
            direction = direction.upper()

            if direction not in ["BUY", "SELL"]:
                await update.message.reply_text("Use BUY or SELL")
                return

            await execute_trade(pair, direction, amt)

        except:
            await update.message.reply_text("Format:\nEURUSD_otc 50 BUY")

        return

    await update.message.reply_text("OK", reply_markup=reply_markup)

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