import asyncio
import os
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

TELEGRAM_TOKEN = os.getenv("8729302934:AAGTTdfV8lPAR2hg4_zVVqT2ipLG1-lAV4s")
SSID = os.getenv("%22%3Bs%3A32%3A%227b2905945d5265888be620a3a83ced5%22%3Bs%3A10%3A%22")

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

def create_client():
    return AsyncPocketOptionClient(
        ssid=SSID,
        is_demo=(ACCOUNT_MODE=="DEMO")
    )

client=create_client()

# =========================
# INDICATORS
# =========================

def ema(prices,p):
    e=prices[0]
    m=2/(p+1)

    for price in prices[1:]:
        e=((price-e)*m)+e

    return e


def rsi(prices,p=14):

    gains=[]
    losses=[]

    for i in range(1,len(prices)):

        c=prices[i]-prices[i-1]

        if c>0:
            gains.append(c)
        else:
            losses.append(abs(c))

    if len(losses)==0:
        return 100

    ag=sum(gains[-p:])/p if gains else 0
    al=sum(losses[-p:])/p

    if al==0:
        return 100

    rs=ag/al

    return 100-(100/(1+rs))


def macd(prices):
    return ema(prices,12)-ema(prices,26)


def analyze_market(candles):

    closes=[float(x["close"]) for x in candles]

    if len(closes)<30:
        return "WAIT",50

    ef=ema(closes[-20:],9)
    es=ema(closes[-30:],21)
    r=rsi(closes)
    m=macd(closes)

    if ef>es and m>0 and r<70:
        return "BUY",85

    if ef<es and m<0 and r>30:
        return "SELL",85

    return "WAIT",50

# =========================
# SEND MESSAGE
# =========================

async def send_message(msg):

    if AUTHORIZED_CHAT_ID:

        await bot.send_message(
            chat_id=AUTHORIZED_CHAT_ID,
            text=msg,
            reply_markup=reply_markup
        )

# =========================
# ACCOUNT SWITCH
# =========================

async def switch_account(mode):

    global ACCOUNT_MODE
    global client

    ACCOUNT_MODE=mode

    try:
        client=create_client()
        await client.connect()
        return True

    except Exception as e:
        print(e)
        return False

# =========================
# PLACE TRADE
# =========================

async def place_trade(pair,signal):

    try:

        await client.buy(
            asset=pair,
            amount=current_amount,
            action=signal.lower(),
            duration=EXPIRY
        )

        await send_message(
            f"🤖 AUTO TRADE\nPAIR:{pair}\nSIGNAL:{signal}"
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

    try:
        await client.connect()
        await send_message("✅ PocketOption Connected")

    except Exception as e:
        print(e) 

    while True:

        try:

            if not BOT_RUNNING:
                await asyncio.sleep(5)
                continue

            balance=await client.get_balance()

            for pair in PAIRS:

                try:

                    candles=await client.get_candles(
                        asset=pair,
                        period=TIMEFRAME,
                        offset=0
                    )

                    signal,confidence=analyze_market(candles)

                    if signal!="WAIT" and confidence>=MIN_CONFIDENCE:

                        now=datetime.now()
                        ex=now+timedelta(seconds=EXPIRY)

                        if not AUTO_TRADE:

                            await send_message(
                                f"📢 SIGNAL\n\nPAIR:{pair}\nSIGNAL:{signal}\nENTRY:{now.strftime('%H:%M:%S')}\nEXPIRY:{ex.strftime('%H:%M:%S')}\nBALANCE:${balance}"
                            )
                        else:
                            await place_trade(pair,signal)

                    await asyncio.sleep(SCAN_DELAY)

                except Exception as e:
                    print(e)

            await asyncio.sleep(60)

        except Exception as e:
            print(e)
            await asyncio.sleep(10)

# =========================
# BUTTON HANDLER
# =========================

async def button_handler(update:Update,context:ContextTypes.DEFAULT_TYPE):

    global AUTO_TRADE
    global AUTHORIZED_CHAT_ID
    global BOT_RUNNING

    AUTHORIZED_CHAT_ID=update.effective_chat.id

    text=update.message.text

    if text=="🤖 AUTO":
        AUTO_TRADE=True
        await update.message.reply_text("🤖 AUTO ENABLED",reply_markup=reply_markup)

    elif text=="📢 MANUAL":
        AUTO_TRADE=False
        await update.message.reply_text("📢 MANUAL ENABLED",reply_markup=reply_markup)

    elif text=="🎮 DEMO":
        if await switch_account("DEMO"):
            await update.message.reply_text("🎮 DEMO ENABLED",reply_markup=reply_markup)

    elif text=="💵 REAL":
        if await switch_account("REAL"):
            await update.message.reply_text("💵 REAL ENABLED",reply_markup=reply_markup)

    elif text=="💰 BALANCE":
        b=await client.get_balance()
        await update.message.reply_text(f"💰 Balance:${b}",reply_markup=reply_markup)

    elif text=="📊 STATUS":
        mode="AUTO" if AUTO_TRADE else "MANUAL"
        await update.message.reply_text(f"📊 STATUS\nMODE:{mode}\nACCOUNT:{ACCOUNT_MODE}",reply_markup=reply_markup)

    elif text=="▶ START":
        BOT_RUNNING=True
        await update.message.reply_text("▶ BOT STARTED",reply_markup=reply_markup)

    elif text=="⛔ STOP":
        BOT_RUNNING=False
        AUTO_TRADE=False
        await update.message.reply_text("⛔ BOT STOPPED",reply_markup=reply_markup)

# =========================
# MAIN
# =========================

async def start_background(app):
    asyncio.create_task(trading_loop())


def main():

    app=(
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

    print("Bot Running")

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
