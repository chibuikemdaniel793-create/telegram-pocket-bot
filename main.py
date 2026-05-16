import os
import asyncio
import traceback

from pocketoptionapi_async import AsyncPocketOptionClient
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, ContextTypes, MessageHandler, filters

# ================= CONFIG =================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
SSID = os.getenv("SSID")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

if not TELEGRAM_TOKEN or not SSID or OWNER_ID == 0:
    raise ValueError("Missing environment variables")

TIMEFRAME = 60
EXPIRY = 60

ACCOUNT_MODE = "DEMO"

AUTO_TRADE = False
BOT_RUNNING = False

TRADE_AMOUNT = 10
current_amount = TRADE_AMOUNT

AUTHORIZED_CHAT_ID = None

# martingale
total_loss = 0
last_payout = 0.80  # fallback

# stats
wins = 0
losses = 0
total_trades = 0
profit = 0

client = None

# ================= TELEGRAM =================

keyboard = [
    ["🤖 AUTO", "📢 MANUAL"],
    ["🎮 DEMO", "💵 REAL"],
    ["💰 BALANCE", "📊 STATUS"],
    ["💲 AMOUNT"],
    ["▶ START", "⛔ STOP"],
    ["🔄 RECONNECT"]
]

reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ================= CLIENT =================

def create_client():
    return AsyncPocketOptionClient(
        ssid=SSID,
        is_demo=(ACCOUNT_MODE == "DEMO")
    )

async def ensure_connection():
    global client
    try:
        if client is None:
            client = create_client()
            await client.connect()
        return True
    except Exception as e:
        print("Connection error:", e)
        client = None
        return False

# ================= UTIL =================

async def send(context, msg):
    if AUTHORIZED_CHAT_ID:
        await context.bot.send_message(
            AUTHORIZED_CHAT_ID,
            msg,
            reply_markup=reply_markup
        )

def simple_signal(candles):
    if len(candles) < 3:
        return None

    closes = [float(c["close"]) for c in candles]

    if closes[-1] > closes[-2]:
        return "BUY"
    elif closes[-1] < closes[-2]:
        return "SELL"
    return None

# ================= TRADE =================

async def execute_trade(context, pair):
    global current_amount, wins, losses, total_trades, profit
    global total_loss, last_payout

    if not await ensure_connection():
        await send(context, "❌ Not connected")
        return

    try:
        candles = await client.get_candles(pair, TIMEFRAME, 0)
        signal = simple_signal(candles)

        if not signal:
            await send(context, "⚠ No signal")
            return

        await send(context, f"📊 {pair} → {signal} | ${round(current_amount,2)}")

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
            # WIN
            wins += 1
            profit += result

            payout_ratio = result / current_amount
            last_payout = payout_ratio

            await send(context, f"✅ WIN ${round(result,2)} ({round(payout_ratio*100,1)}%)")

            # RESET martingale
            total_loss = 0
            current_amount = TRADE_AMOUNT

        else:
            # LOSS
            losses += 1
            profit -= current_amount
            total_loss += current_amount

            payout_ratio = last_payout if last_payout > 0 else 0.80

            current_amount = (total_loss + TRADE_AMOUNT) / payout_ratio

            await send(
                context,
                f"❌ LOSS\nLoss: ${round(total_loss,2)}\nNext: ${round(current_amount,2)}"
            )

    except Exception:
        traceback.print_exc()
        await send(context, "❌ Trade error")

# ================= AUTO LOOP =================

async def trading_loop(app):
    global BOT_RUNNING

    while True:
        await asyncio.sleep(1)

        if not BOT_RUNNING or not AUTO_TRADE:
            continue

        try:
            await execute_trade(app, "EURUSD_otc")
        except:
            traceback.print_exc()
            await asyncio.sleep(5)

# ================= HANDLER =================

waiting_amount = False
manual_mode = False

async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global AUTO_TRADE, BOT_RUNNING, ACCOUNT_MODE
    global AUTHORIZED_CHAT_ID, TRADE_AMOUNT, current_amount
    global waiting_amount, manual_mode, client

    if update.effective_user.id != OWNER_ID:
        return

    AUTHORIZED_CHAT_ID = update.effective_chat.id
    text = update.message.text

    if text == "💲 AMOUNT":
        waiting_amount = True
        await update.message.reply_text("Enter amount (e.g. 50)")
        return

    if waiting_amount:
        try:
            TRADE_AMOUNT = float(text)
            current_amount = TRADE_AMOUNT
            waiting_amount = False
            await update.message.reply_text(f"Amount set to ${TRADE_AMOUNT}")
        except:
            await update.message.reply_text("Invalid amount")
        return

    if text == "🤖 AUTO":
        AUTO_TRADE = True
        manual_mode = False
        await update.message.reply_text("Auto ON")

    elif text == "📢 MANUAL":
        AUTO_TRADE = False
        manual_mode = True
        await update.message.reply_text("Send pair (e.g. EURUSD_otc)")

    elif text == "🎮 DEMO":
        ACCOUNT_MODE = "DEMO"
        client = None
        await update.message.reply_text("Demo mode")

    elif text == "💵 REAL":
        ACCOUNT_MODE = "REAL"
        client = None
        await update.message.reply_text("Real mode")

    elif text == "▶ START":
        BOT_RUNNING = True
        await update.message.reply_text("Bot started")

    elif text == "⛔ STOP":
        BOT_RUNNING = False
        await update.message.reply_text("Bot stopped")

    elif text == "🔄 RECONNECT":
        client = None
        await update.message.reply_text("Reconnecting...")

    elif text == "💰 BALANCE":
        if not await ensure_connection():
            await update.message.reply_text("Not connected")
            return
        try:
            bal = await client.get_balance()
            await update.message.reply_text(f"Balance: ${bal}")
        except:
            await update.message.reply_text("Balance error")

    elif text == "📊 STATUS":
        await update.message.reply_text(
            f"Trades: {total_trades}\nWins: {wins}\nLosses: {losses}\nProfit: ${round(profit,2)}"
        )

    elif manual_mode:
        await execute_trade(context, text)

# ================= MAIN =================

async def start_bg(app):
    asyncio.create_task(trading_loop(app))

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