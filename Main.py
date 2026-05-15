import os
import asyncio
import nest_asyncio

from datetime import datetime, timedelta
from pocketoptionapi_async import AsyncPocketOptionClient

from telegram import (
    Update,
    Bot,
    ReplyKeyboardMarkup
)

from telegram.ext import (
    Application,
    ContextTypes,
    MessageHandler,
    filters
)

# =========================
# CONFIG
# =========================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
SSID = os.getenv("SSID")

TIMEFRAME = 60
EXPIRY = 60

ACCOUNT_MODE = "DEMO"

AUTO_TRADE = False

INITIAL_AMOUNT = 11
current_amount = INITIAL_AMOUNT

MIN_CONFIDENCE = 85

BOT_RUNNING = True
AUTHORIZED_CHAT_ID = None

# =========================
# TELEGRAM
# =========================

bot = Bot(token=TELEGRAM_TOKEN)

keyboard = [
    ["🤖 AUTO", "📢 MANUAL"],
    ["🎮 DEMO", "💵 REAL"],
    ["💰 BALANCE", "📊 STATUS"],
    ["▶ START", "⛔ STOP"]
]

reply_markup = ReplyKeyboardMarkup(
    keyboard,
    resize_keyboard=True
)

# =========================
# PAIRS
# =========================

PAIRS = [
    "EURUSD_otc",
    "GBPUSD_otc",
    "USDJPY_otc",
    "AUDUSD_otc",
    "USDCAD_otc",
    "USDCHF_otc",
    "EURJPY_otc",
    "GBPJPY_otc"
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
    multiplier = 2 / (period + 1)

    for price in prices[1:]:
        e = ((price - e) * multiplier) + e

    return e

def rsi(prices, period=14):

    gains = []
    losses = []

    for i in range(1, len(prices)):

        change = prices[i] - prices[i - 1]

        if change > 0:
            gains.append(change)
        else:
            losses.append(abs(change))

    if len(losses) == 0:
        return 100

    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss

    return 100 - (100 / (1 + rs))

def macd(prices):

    return ema(prices, 12) - ema(prices, 26)

def analyze_market(candles):

    closes = [float(c["close"]) for c in candles]

    if len(closes) < 30:
        return "WAIT", 50

    ema_fast = ema(closes[-20:], 9)
    ema_slow = ema(closes[-30:], 21)

    r = rsi(closes)
    m = macd(closes)

    if ema_fast > ema_slow and m > 0 and r < 70:
        return "BUY", 85

    if ema_fast < ema_slow and m < 0 and r > 30:
        return "SELL", 85

    return "WAIT", 50

# =========================
# WAIT FOR NEW CANDLE
# =========================

async def wait_for_new_candle():

    while True:

        current_second = datetime.now().second

        if current_second == 0:
            return

        await asyncio.sleep(0.5)

# =========================
# SEND MESSAGE
# =========================

async def send_message(message):

    global AUTHORIZED_CHAT_ID

    if AUTHORIZED_CHAT_ID:

        try:

            await bot.send_message(
                chat_id=AUTHORIZED_CHAT_ID,
                text=message,
                reply_markup=reply_markup
            )

        except Exception as e:

            print(f"Telegram Error: {e}")

# =========================
# SWITCH ACCOUNT
# =========================

async def switch_account(mode):

    global ACCOUNT_MODE
    global client

    ACCOUNT_MODE = mode

    try:

        client = create_client()

        await client.connect()

        return True

    except Exception as e:

        print(f"Switch Account Error: {e}")

        return False

# =========================
# PLACE TRADE
# =========================

async def place_trade(pair, signal):

    global client
    global current_amount

    while True:

        try:

            now = datetime.now()

            await send_message(
                f"🤖 AUTO TRADE\n\n"
                f"PAIR: {pair}\n"
                f"SIGNAL: {signal}\n"
                f"AMOUNT: ${current_amount}\n"
                f"ENTRY: {now.strftime('%H:%M:%S')}"
            )

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

            # =========================
            # WIN
            # =========================

            if result > 0:

                await send_message(
                    f"✅ WIN\n\n"
                    f"PAIR: {pair}\n"
                    f"PROFIT: ${result}\n"
                    f"RESET TO INITIAL AMOUNT"
                )

                current_amount = INITIAL_AMOUNT

                break

            # =========================
            # LOSS
            # =========================

            else:

                await send_message(
                    f"❌ LOSS\n\n"
                    f"PAIR: {pair}\n"
                    f"CONTINUING MARTINGALE..."
                )

                current_amount = current_amount * 2

                await send_message(
                    f"♻️ NEXT AMOUNT\n\n"
                    f"${current_amount}"
                )

                # =========================
                # WAIT FOR NEXT CANDLE
                # =========================

                await wait_for_new_candle()

        except Exception as e:

            await send_message(
                f"❌ TRADE ERROR\n{e}"
            )

            await asyncio.sleep(5)

# =========================
# TRADING LOOP
# =========================

async def trading_loop():

    global BOT_RUNNING
    global client

    while True:

        try:

            if client is None:

                client = create_client()

                await client.connect()

                await send_message(
                    "✅ PocketOption Connected"
                )

            if not BOT_RUNNING:

                await asyncio.sleep(5)
                continue

            # =========================
            # WAIT FOR FRESH CANDLE
            # =========================

            await wait_for_new_candle()

            try:

                balance = await client.get_balance()

            except:

                balance = "Unknown"

            for pair in PAIRS:

                try:

                    candles = await client.get_candles(
                        asset=pair,
                        period=TIMEFRAME,
                        offset=0
                    )

                    signal, confidence = analyze_market(candles)

                    if signal != "WAIT" and confidence >= MIN_CONFIDENCE:

                        now = datetime.now()
                        expiry_time = now + timedelta(seconds=EXPIRY)

                        if not AUTO_TRADE:

                            await send_message(
                                f"📢 SIGNAL\n\n"
                                f"PAIR: {pair}\n"
                                f"SIGNAL: {signal}\n"
                                f"ENTRY: {now.strftime('%H:%M:%S')}\n"
                                f"EXPIRY: {expiry_time.strftime('%H:%M:%S')}\n"
                                f"BALANCE: ${balance}"
                            )

                        else:

                            await place_trade(pair, signal)

                    await asyncio.sleep(1)

                except Exception as e:

                    print(f"{pair} Error: {e}")

            await asyncio.sleep(1)

        except Exception as e:

            print(f"Trading Loop Error: {e}")

            await asyncio.sleep(5)

# =========================
# BUTTON HANDLER
# =========================

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    global AUTO_TRADE
    global AUTHORIZED_CHAT_ID
    global BOT_RUNNING

    AUTHORIZED_CHAT_ID = update.effective_chat.id

    text = update.message.text

    if text == "🤖 AUTO":

        AUTO_TRADE = True

        await update.message.reply_text(
            "🤖 AUTO ENABLED",
            reply_markup=reply_markup
        )

    elif text == "📢 MANUAL":

        AUTO_TRADE = False

        await update.message.reply_text(
            "📢 MANUAL ENABLED",
            reply_markup=reply_markup
        )

    elif text == "🎮 DEMO":

        if await switch_account("DEMO"):

            await update.message.reply_text(
                "🎮 DEMO ENABLED",
                reply_markup=reply_markup
            )

    elif text == "💵 REAL":

        if await switch_account("REAL"):

            await update.message.reply_text(
                "💵 REAL ENABLED",
                reply_markup=reply_markup
            )

    elif text == "💰 BALANCE":

        try:

            balance = await client.get_balance()

            await update.message.reply_text(
                f"💰 Balance: ${balance}",
                reply_markup=reply_markup
            )

        except Exception as e:

            await update.message.reply_text(
                f"❌ Balance Error\n{e}",
                reply_markup=reply_markup
            )

    elif text == "📊 STATUS":

        mode = "AUTO" if AUTO_TRADE else "MANUAL"

        await update.message.reply_text(
            f"📊 STATUS\n\n"
            f"MODE: {mode}\n"
            f"ACCOUNT: {ACCOUNT_MODE}\n"
            f"CURRENT AMOUNT: ${current_amount}\n"
            f"TIMEFRAME: 1 MINUTE"
        )

    elif text == "▶ START":

        BOT_RUNNING = True

        await update.message.reply_text(
            "▶ BOT STARTED",
            reply_markup=reply_markup
        )

    elif text == "⛔ STOP":

        BOT_RUNNING = False
        AUTO_TRADE = False

        current_amount = INITIAL_AMOUNT

        await update.message.reply_text(
            "⛔ BOT STOPPED",
            reply_markup=reply_markup
        )

# =========================
# START BACKGROUND
# =========================

async def start_background(app):

    asyncio.create_task(
        trading_loop()
    )

# =========================
# MAIN
# =========================

def main():

    nest_asyncio.apply()

    app = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .post_init(start_background)
        .build()
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT,
            button_handler
        )
    )

    print("Bot Running...")

    app.run_polling(
        drop_pending_updates=True
    )

if __name__ == "__main__":
    main()
