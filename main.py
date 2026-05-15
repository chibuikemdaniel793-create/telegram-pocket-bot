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
    raise ValueError("TELEGRAM_TOKEN missing")

if not SSID:
    raise ValueError("SSID missing")

TIMEFRAME = 60
EXPIRY = 60

ACCOUNT_MODE = "DEMO"

AUTO_TRADE = False
AUTO_PAUSED = False

INITIAL_AMOUNT = 11
current_amount = INITIAL_AMOUNT
MAX_AMOUNT = 500

MIN_CONFIDENCE = 85

BOT_RUNNING = True
AUTHORIZED_CHAT_ID = None

# 📊 Tracking
wins = 0
losses = 0
total_trades = 0

# 💰 Profit cycle
TARGET_PROFIT = 50
cycle_profit = 0

# 🔄 SSID state
SSID_INVALID = False

# =========================
# TELEGRAM
# =========================

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
# PAIRS
# =========================

PAIRS = [
    "EURUSD_otc","GBPUSD_otc","USDJPY_otc","AUDUSD_otc",
    "USDCAD_otc","USDCHF_otc","EURJPY_otc","GBPJPY_otc"
]

# =========================
# CLIENT
# =========================

client = None

def create_client():
    return AsyncPocketOptionClient(
        ssid=SSID,
        is_demo=(ACCOUNT_MODE == "DEMO")
    )

# =========================
# INDICATORS
# =========================

def ema(prices, period):
    e = prices[0]
    m = 2 / (period + 1)
    for p in prices[1:]:
        e = ((p - e) * m) + e
    return e

def rsi(prices, period=14):
    gains, losses = [], []
    for i in range(1, len(prices)):
        d = prices[i] - prices[i-1]
        if d > 0:
            gains.append(d)
        else:
            losses.append(abs(d))

    if not losses:
        return 100

    ag = sum(gains[-period:]) / period
    al = sum(losses[-period:]) / period

    if al == 0:
        return 100

    rs = ag / al
    return 100 - (100 / (1 + rs))

def macd(prices):
    return ema(prices, 12) - ema(prices, 26)

def bollinger_bands(prices, period=20, deviation=2):
    if len(prices) < period:
        return None, None, None

    sma = sum(prices[-period:]) / period
    variance = sum((p - sma) ** 2 for p in prices[-period:]) / period
    std_dev = variance ** 0.5

    upper = sma + (deviation * std_dev)
    lower = sma - (deviation * std_dev)

    return upper, sma, lower

def analyze_market(candles):
    if not candles:
        return "WAIT", 0

    closes = [float(c["close"]) for c in candles]

    if len(closes) < 30:
        return "WAIT", 50

    ema_fast = ema(closes[-20:], 9)
    ema_slow = ema(closes[-30:], 21)

    r = rsi(closes)
    m = macd(closes)

    upper, middle, lower = bollinger_bands(closes)
    current_price = closes[-1]

    if (
        ema_fast > ema_slow and
        m > 0 and
        r < 70 and
        lower is not None and
        current_price <= lower
    ):
        return "BUY", 90

    if (
        ema_fast < ema_slow and
        m < 0 and
        r > 30 and
        upper is not None and
        current_price >= upper
    ):
        return "SELL", 90

    return "WAIT", 50

# =========================
# UTIL
# =========================

async def wait_for_new_candle():
    while True:
        if datetime.now().second == 0:
            return
        await asyncio.sleep(0.5)

async def send_message(msg):
    if not AUTHORIZED_CHAT_ID:
        return
    try:
        await bot.send_message(AUTHORIZED_CHAT_ID, msg, reply_markup=reply_markup)
    except Exception as e:
        print(e)

# =========================
# TRADE
# =========================

async def place_trade(pair, signal):
    global current_amount, wins, losses, total_trades
    global cycle_profit, AUTO_PAUSED, SSID_INVALID, client

    while True:
        try:
            await send_message(f"🤖 {pair} → {signal} | ${current_amount}")

            trade = await client.buy(
                asset=pair,
                amount=current_amount,
                action=signal.lower(),
                duration=EXPIRY
            )

            await asyncio.sleep(EXPIRY + 5)

            try:
                result = await client.check_win(trade)
            except:
                result = 0

            if result > 0:
                wins += 1
                total_trades += 1
                cycle_profit += result
                current_amount = INITIAL_AMOUNT

                await send_message(f"✅ WIN ${result}\n💰 ${cycle_profit:.2f}/{TARGET_PROFIT}")

                if cycle_profit >= TARGET_PROFIT:
                    AUTO_PAUSED = True
                    await send_message("🎯 Target reached. Auto paused.")
                    return

                break

            else:
                losses += 1
                total_trades += 1
                cycle_profit -= current_amount

                await send_message("❌ LOSS")

                current_amount *= 2

                if current_amount > MAX_AMOUNT:
                    await send_message("⚠️ Max reached. Reset.")
                    current_amount = INITIAL_AMOUNT
                    break

                await wait_for_new_candle()

        except Exception as e:
            traceback.print_exc()

            if "connect" in str(e).lower() or "session" in str(e).lower():
                SSID_INVALID = True
                client = None

                await send_message(
                    "❌ Connection lost.\n⚠️ SSID expired.\nUpdate & press RECONNECT."
                )
                return

            await asyncio.sleep(5)

# =========================
# LOOP
# =========================

async def trading_loop():
    global client, SSID_INVALID

    while True:
        try:
            if client is None:
                client = create_client()
                try:
                    await client.connect()
                    SSID_INVALID = False
                    await send_message("✅ Connected")
                except Exception as e:
                    client = None
                    SSID_INVALID = True

                    await send_message(
                        "❌ Connection failed.\n⚠️ SSID may be expired."
                    )

                    await asyncio.sleep(15)
                    continue

            if SSID_INVALID:
                await asyncio.sleep(10)
                continue

            if not BOT_RUNNING:
                await asyncio.sleep(5)
                continue

            await wait_for_new_candle()

            for pair in PAIRS:
                try:
                    candles = await client.get_candles(pair, TIMEFRAME, 0)
                    signal, conf = analyze_market(candles)

                    if signal != "WAIT" and conf >= MIN_CONFIDENCE:
                        if AUTO_TRADE and not AUTO_PAUSED:
                            await place_trade(pair, signal)
                        else:
                            await send_message(f"📢 {pair} → {signal}")

                    await asyncio.sleep(1)

                except:
                    traceback.print_exc()

        except:
            traceback.print_exc()
            await asyncio.sleep(5)

# =========================
# BUTTONS
# =========================

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global AUTO_TRADE, BOT_RUNNING, AUTHORIZED_CHAT_ID
    global current_amount, cycle_profit, AUTO_PAUSED
    global client, SSID_INVALID, wins, losses, total_trades

    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Unauthorized")
        return

    AUTHORIZED_CHAT_ID = update.effective_chat.id
    text = update.message.text

    if text == "🤖 AUTO":
        AUTO_TRADE = True

    elif text == "📢 MANUAL":
        AUTO_TRADE = False

    elif text == "▶ START":
        BOT_RUNNING = True
        AUTO_PAUSED = False
        cycle_profit = 0

    elif text == "⛔ STOP":
        BOT_RUNNING = False
        AUTO_TRADE = False
        current_amount = INITIAL_AMOUNT

    elif text == "🔄 RECONNECT":
        client = None
        SSID_INVALID = False
        await update.message.reply_text("🔄 Reconnecting...")

    elif text == "📊 STATUS":
        winrate = (wins / total_trades * 100) if total_trades else 0
        state = "PAUSED" if AUTO_PAUSED else "RUNNING"

        await update.message.reply_text(
            f"📊 STATUS\n\n"
            f"STATE: {state}\n"
            f"MODE: {'AUTO' if AUTO_TRADE else 'MANUAL'}\n\n"
            f"Trades: {total_trades}\n"
            f"Wins: {wins}\n"
            f"Losses: {losses}\n"
            f"WR: {winrate:.1f}%\n\n"
            f"💰 Profit: ${cycle_profit:.2f}/{TARGET_PROFIT}",
            reply_markup=reply_markup
        )
        return

    await update.message.reply_text("✅ Updated", reply_markup=reply_markup)

# =========================
# MAIN
# =========================

async def start_background(app):
    asyncio.create_task(trading_loop())

def main():
    nest_asyncio.apply()

    app = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .post_init(start_background)
        .build()
    )

    app.add_handler(MessageHandler(filters.TEXT, button_handler))

    print("Bot Running...")
    app.run_polling()

if __name__ == "__main__":
    main()
