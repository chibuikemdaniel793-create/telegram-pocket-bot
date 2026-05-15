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

TELEGRAM_TOKEN = "8729302934:AAGTTdfV8lPAR2hg4_zVVqT2ipLG1-lAV4s"
SSID = "%22%3Bs%3A32%3A%227b2905945d5265888be620a3a83ced5%22%3Bs%3A10%3A%22"

TIMEFRAME = 60
ACCOUNT_MODE = "DEMO"
AUTO_TRADE = False

INITIAL_AMOUNT = 11
current_amount = INITIAL_AMOUNT

EXPIRY = 60
MIN_CONFIDENCE = 85
SCAN_DELAY = 2

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
    "NZDUSD_otc",
    "EURGBP_otc",
    "EURJPY_otc",
    "GBPJPY_otc",
    "AUDJPY_otc",
    "CADJPY_otc",
    "CHFJPY_otc",
    "NZDJPY_otc",
    "EURAUD_otc",
    "EURCHF_otc",
    "EURNZD_otc",
    "GBPAUD_otc",
    "GBPCHF_otc",
    "GBPCAD_otc",
    "AUDCAD_otc",
    "AUDCHF_otc",
    "AUDNZD_otc",
    "CADCHF_otc",
    "NZDCAD_otc",
    "NZDCHF_otc"
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

    try:

        await client.buy(
            asset=pair,
            amount=current_amount,
            action=signal.lower(),
            duration=EXPIRY
        )

        await send_message(
            f"🤖 AUTO TRADE\n\nPAIR: {pair}\nSIGNAL: {signal}"
        )

    except Exception as e:

        await send_message(
            f"❌ TRADE ERROR\n{e}"
        )


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

            try:
                balance = await client.get_balance()

            except Exception:
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

                    await asyncio.sleep(SCAN_DELAY)

                except Exception as e:

                    print(f"{pair} Error: {e}")

            await asyncio.sleep(10)

        except Exception as e:

            print(f"Trading Loop Error: {e}")

            await asyncio.sleep(10)


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
            f"ACCOUNT: {ACCOUNT_MODE}",
            reply_markup=reply_markup
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
