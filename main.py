
import nest_asyncio
nest_asyncio.apply()

import asyncio
import traceback

from datetime import datetime, timedelta

from api_pocket import AsyncPocketOptionClient

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

# ==========================================
# TELEGRAM SETTINGS
# ==========================================

TELEGRAM_TOKEN = "8729302934:AAGTTdfV8lPAR2hg4_zVVqT2ipLG1-lAV4s"

# ==========================================
# POCKET OPTION SETTINGS
# ==========================================

SSID = "%22%3Bs%3A32%3A%227b2905945d5265888be620a3a83ced5%22%3Bs%3A10%3A%22"

TIMEFRAME = 60

# ==========================================
# ACCOUNT MODES
# ==========================================

ACCOUNT_MODE = "DEMO"

# ==========================================
# TRADING SETTINGS
# ==========================================

AUTO_TRADE = False

INITIAL_AMOUNT = 11

current_amount = INITIAL_AMOUNT

EXPIRY = 60

PAYOUT_PERCENT = 92

MIN_CONFIDENCE = 85

MAX_MARTINGALE_LEVEL = 3

SCAN_DELAY = 2

loss_level = 0

BOT_RUNNING = True

# ==========================================
# TELEGRAM CHAT
# ==========================================

AUTHORIZED_CHAT_ID = None

# ==========================================
# TELEGRAM BOT
# ==========================================

bot = Bot(token=TELEGRAM_TOKEN)

# ==========================================
# TELEGRAM BUTTONS
# ==========================================

keyboard = [

    ["🤖 AUTO", "📢 MANUAL"],

    ["🎮 DEMO", "💵 REAL"],

    ["🏆 TOURNAMENT", "💰 BALANCE"],

    ["📊 STATUS", "▶ START"],

    ["⛔ STOP"]

]

reply_markup = ReplyKeyboardMarkup(
    keyboard,
    resize_keyboard=True,
    persistent=True
)

# ==========================================
# OTC PAIRS
# ==========================================

PAIRS = [

    "EURUSD_otc",
    "GBPUSD_otc",
    "USDJPY_otc",
    "AUDUSD_otc",
    "USDCAD_otc",

    "EURGBP_otc",
    "EURJPY_otc",
    "GBPJPY_otc",
    "AUDJPY_otc",
    "NZDUSD_otc",

    "USDCHF_otc",
    "EURAUD_otc",
    "GBPAUD_otc",
    "CADJPY_otc",
    "CHFJPY_otc",

    "AUDCAD_otc",
    "AUDCHF_otc",
    "GBPCHF_otc",
    "NZDJPY_otc",
    "EURCHF_otc"

]

# ==========================================
# CREATE CLIENT
# ==========================================

def create_client():

    global ACCOUNT_MODE

    if ACCOUNT_MODE == "DEMO":

        return AsyncPocketOptionClient(
            ssid=SSID,
            is_demo=True
        )

    elif ACCOUNT_MODE == "REAL":

        return AsyncPocketOptionClient(
            ssid=SSID,
            is_demo=False
        )

    elif ACCOUNT_MODE == "TOURNAMENT":

        return AsyncPocketOptionClient(
            ssid=SSID,
            is_demo=False
        )

# ==========================================
# INITIAL CLIENT
# ==========================================

client = create_client()

# ==========================================
# LIGHTWEIGHT INDICATORS
# ==========================================

def calculate_ema(prices, period):

    ema = prices[0]

    multiplier = 2 / (period + 1)

    for price in prices[1:]:

        ema = (
            (price - ema) * multiplier
        ) + ema

    return ema


def calculate_rsi(prices, period=14):

    gains = []
    losses = []

    for i in range(1, len(prices)):

        change = prices[i] - prices[i - 1]

        if change > 0:
            gains.append(change)
        else:
            losses.append(abs(change))

    if len(gains) == 0:
        return 0

    avg_gain = sum(gains[-period:]) / period

    avg_loss = sum(losses[-period:]) / period

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss

    return 100 - (100 / (1 + rs))


def calculate_macd(prices):

    ema_fast = calculate_ema(prices, 12)

    ema_slow = calculate_ema(prices, 26)

    return ema_fast - ema_slow

# ==========================================
# LIGHTWEIGHT AI ANALYSIS
# ==========================================

def analyze_market(candles):

    closes = []

    for candle in candles:

        closes.append(float(candle['close']))

    if len(closes) < 30:

        return "WAIT", 50

    ema_fast = calculate_ema(closes[-20:], 9)

    ema_slow = calculate_ema(closes[-30:], 21)

    rsi = calculate_rsi(closes)

    macd = calculate_macd(closes)

    signal = "WAIT"

    confidence = 50

    if (
        ema_fast > ema_slow
        and macd > 0
        and rsi < 70
    ):

        signal = "BUY"
        confidence = 85

    elif (
        ema_fast < ema_slow
        and macd < 0
        and rsi > 30
    ):

        signal = "SELL"
        confidence = 85

    return signal, confidence

# ==========================================
# SEND MESSAGE
# ==========================================

async def send_message(message):

    global AUTHORIZED_CHAT_ID

    if AUTHORIZED_CHAT_ID:

        await bot.send_message(
            chat_id=AUTHORIZED_CHAT_ID,
            text=message,
            reply_markup=reply_markup
        )

# ==========================================
# SWITCH ACCOUNT
# ==========================================

async def switch_account(mode):

    global ACCOUNT_MODE
    global client

    ACCOUNT_MODE = mode

    try:

        try:
            await client.disconnect()
        except:
            pass

        client = create_client()

        await client.connect()

        return True

    except Exception as e:

        print(e)
        traceback.print_exc()

        return False

# ==========================================
# MARTINGALE
# ==========================================

def calculate_martingale_amount(
    previous_amount,
    payout_percent,
    target_profit
):

    payout = payout_percent / 100

    new_amount = (
        previous_amount + target_profit
    ) / payout

    return round(new_amount + 1)

# ==========================================
# AUTO TRADE
# ==========================================

async def place_trade(pair, signal):

    global current_amount
    global loss_level

    try:

        direction = signal.lower()

        trade_amount = current_amount

        result = await client.buy(
            asset=pair,
            amount=trade_amount,
            action=direction,
            duration=EXPIRY
        )

        await send_message(
            f"""
🤖 AUTO TRADE EXECUTED

PAIR: {pair}

DIRECTION: {signal}

AMOUNT: ${trade_amount}

ACCOUNT: {ACCOUNT_MODE}

EXPIRY: {EXPIRY} Seconds
"""
        )

        await asyncio.sleep(EXPIRY + 5)

        profit = result.get("profit", 0)

        if profit > 0:

            current_amount = INITIAL_AMOUNT

            loss_level = 0

            await send_message(
                f"""
✅ TRADE WON

PAIR: {pair}

PROFIT: ${profit}

NEXT TRADE: ${INITIAL_AMOUNT}
"""
            )

        else:

            loss_level += 1

            if loss_level > MAX_MARTINGALE_LEVEL:

                current_amount = INITIAL_AMOUNT

                loss_level = 0

                await send_message(
                    "🛑 MAX MARTINGALE REACHED"
                )

            else:

                next_amount = calculate_martingale_amount(
                    previous_amount=trade_amount,
                    payout_percent=PAYOUT_PERCENT,
                    target_profit=INITIAL_AMOUNT
                )

                current_amount = next_amount

                await send_message(
                    f"""
❌ TRADE LOST

NEXT TRADE: ${next_amount}

MARTINGALE LEVEL: {loss_level}
"""
                )

    except Exception as e:

        await send_message(
            f"❌ TRADE ERROR:\n{e}"
        )

# ==========================================
# TRADING LOOP
# ==========================================

async def trading_loop():

    global AUTO_TRADE
    global BOT_RUNNING

    await client.connect()

    await send_message(
        "✅ PocketOption AI Bot Connected"
    )
  while True:                                   
     if not BOT_RUNNING:

                await asyncio.sleep(5)

                continue
                                                              balance = await client.get_balance()

            for pair in PAIRS:                    
                try:

                    candles = await client.get_candles(
                        asset=pair,                                       period=TIMEFRAME,
                        offset=0
                    )

                    signal, confidence = analyze_market(candles)                                    
                    if (
                        signal != "WAIT"                                  and confidence >= MIN_CONFIDENCE                                                                ):

                        entry_time = datetime.now()
                                                                          expiry_time = (
                            entry_time +                                      timedelta(seconds=EXPIRY)                                                                       )
                                                                          if not AUTO_TRADE:
                                                                              await send_message(
                                f"""              📢 OTC MANUAL SIGNAL
                                                  PAIR: {pair}
                                                  DIRECTION: {signal}

ENTRY:                                            {entry_time.strftime('%H:%M:%S')}
                                                  EXPIRY:
{expiry_time.strftime('%H:%M:%S')}                
CONFIDENCE: {confidence}%                         
BALANCE: ${balance}                               """
                            )                     
                        else:                     
                            await place_trade(                                    pair,
                                signal                                        )
                                                                      await asyncio.sleep(SCAN_DELAY)                                                 
                except Exception as pair_error:   
                    print(pair_error)             
            await asyncio.sleep(60)               
        except Exception as e:                    
            print(e)                              
            await asyncio.sleep(10)               
# ==========================================      # BUTTON HANDLER
# ==========================================      
async def button_handler(                             update: Update,
    context: ContextTypes.DEFAULT_TYPE            ):
                                                      global AUTO_TRADE
    global AUTHORIZED_CHAT_ID
    global BOT_RUNNING                            
    AUTHORIZED_CHAT_ID = update.effective_chat.id 
    text = update.message.text                    
    if text == "🤖 AUTO":                         
        AUTO_TRADE = True
                                                          await update.message.reply_text(
            "🤖 AUTO ENABLED",                                reply_markup=reply_markup
        )                                         
    elif text == "📢 MANUAL":
                                                          AUTO_TRADE = False
                                                          await update.message.reply_text(
            "📢 MANUAL ENABLED",                              reply_markup=reply_markup
        )                                         
    elif text == "🎮 DEMO":                       
        result = await switch_account("DEMO")     
        if result:                                
            await update.message.reply_text(                      "🎮 DEMO ACCOUNT ENABLED",
                reply_markup=reply_markup                     )
                                                      elif text == "💵 REAL":

        result = await switch_account("REAL")     
        if result:                                
            await update.message.reply_text(                      "💵 REAL ACCOUNT ENABLED",
                reply_markup=reply_markup
            )                                     
    elif text == "🏆 TOURNAMENT":                 
        result = await switch_account("TOURNAMENT")
                                                          if result:

            await update.message.reply_text(                      "🏆 TOURNAMENT ENABLED",
                reply_markup=reply_markup                     )
                                                      elif text == "💰 BALANCE":
                                                          balance = await client.get_balance()
                                                          await update.message.reply_text(
            f"💰 Balance: ${balance}",                        reply_markup=reply_markup
        )                                         
    elif text == "📊 STATUS":                     
        mode = "AUTO" if AUTO_TRADE else "MANUAL" 
        await update.message.reply_text(
            f"""
📊 STATUS
                                                  MODE: {mode}

ACCOUNT: {ACCOUNT_MODE}                           
BOT: {BOT_RUNNING}

CURRENT TRADE: ${current_amount}

MARTINGALE: {loss_level}                          """,
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
            reply_markup=reply_markup                     )

# ==========================================      # MAIN
# ==========================================      
async def main():                                 
    app = Application.builder().token(                    TELEGRAM_TOKEN
    ).build()                                     
    app.add_handler(                                      MessageHandler(
            filters.TEXT,                                     button_handler
        )                                             )
                                                      asyncio.create_task(
        trading_loop()                                )
                                                      print("Telegram Bot Running...")              
    await app.run_polling()                       
# ==========================================      # START
# ==========================================
