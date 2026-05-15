import os
import asyncio
import nest_asyncio
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

EXPIRY = 60

AUTO_TRADE = False
BOT_RUNNING = True
AUTHORIZED_CHAT_ID = None

INITIAL_AMOUNT = 11
current_amount = INITIAL_AMOUNT

cycle_profit = 0

wins = 0
losses = 0
total_trades = 0

client = None

# ================= TELEGRAM =================

bot = Bot(token=TELEGRAM_TOKEN)

keyboard = [
    ["🤖 AUTO", "📢 MANUAL"],
    ["💰 BALANCE", "📊 STATUS"],
    ["▶ START", "⛔ STOP"],
    ["🔄 RECONNECT"]
]

reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ================= CLIENT =================

def create_client():
    return AsyncPocketOptionClient(ssid=SSID, is_demo=True)

# ================= UTIL =================

async def wait_for_new_candle():
    while True:
        if datetime.now().second == 0:
            return
        await asyncio.sleep(0.5)

async def send_message(msg):
    if AUTHORIZED_CHAT_ID:
        try:
            await bot.send_message(AUTHORIZED_CHAT_ID, msg)
        except:
            pass

# ================= SMART MARTINGALE =================

def calculate_next_amount(loss_total, base_amount, payout):
    # avoid division issues
    if payout <= 0:
        payout = 0.80

    needed = abs(loss_total) + base_amount
    return round(needed / payout, 2)

# ================= TRADE =================

async def place_trade(pair, signal):
    global current_amount, wins, losses, total_trades, cycle_profit

    while True:
        try:
            await send_message(f"{pair} → {signal} | ${current_amount}")

            # 🔥 get payout dynamically
            try:
                payout_info = await client.get_payout(pair)
                payout = payout_info / 100 if payout_info > 1 else payout_info
            except:
                payout = 0.92  # fallback

            trade = await client.buy(
                asset=pair,
                amount=current_amount,
                action=signal,
                duration=EXPIRY
            )

            await asyncio.sleep(EXPIRY + 2)

            result = await client.check_win(trade)

            total_trades += 1

            if result > 0:
                wins += 1
                cycle_profit += result

                await send_message(f"WIN ${result}")

                # reset after win
                current_amount = INITIAL_AMOUNT
                cycle_profit = 0

                await send_message("Cycle complete. Restarting fresh.")
                break

            else:
                losses += 1
                cycle_profit -= current_amount

                # 🔥 SMART MARTINGALE
                next_amount = calculate_next_amount(
                    cycle_profit,
                    INITIAL_AMOUNT,
                    payout
                )

                await send_message(
                    f"LOSS → next ${next_amount} (payout {round(payout*100)}%)"
                )

                current_amount = next_amount

                await wait_for_new_candle()

        except Exception as e:
            traceback.print_exc()
            await asyncio.sleep(3)

# ================= LOOP =================

async def trading_loop():
    global client

    while True:
        try:
            if client is None:
                client = create_client()
                await client.connect()
                await send_message("Connected")

            if not BOT_RUNNING:
                await asyncio.sleep(5)
                continue

            await wait_for_new_candle()

            if AUTO_TRADE:
                await place_trade("EURUSD_otc", "buy")

        except:
            traceback.print_exc()
            await asyncio.sleep(5)

# ================= BUTTONS =================

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global AUTO_TRADE, BOT_RUNNING, AUTHORIZED_CHAT_ID
    global current_amount, INITIAL_AMOUNT

    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("Unauthorized")
        return

    AUTHORIZED_CHAT_ID = update.effective_chat.id
    text = update.message.text

    # 💰 manual amount
    if text.startswith("SET"):
        try:
            amount = float(text.split()[1])
            current_amount = amount
            INITIAL_AMOUNT = amount
            await update.message.reply_text(f"Amount set to ${amount}")
        except:
            await update.message.reply_text("Use: SET 10")
        return

    if text == "🤖 AUTO":
        AUTO_TRADE = True

    elif text == "📢 MANUAL":
        AUTO_TRADE = False

    elif text == "▶ START":
        BOT_RUNNING = True

    elif text == "⛔ STOP":
        BOT_RUNNING = False

    elif text == "💰 BALANCE":
        try:
            temp_client = create_client()
            await temp_client.connect()

            balance = await temp_client.get_balance()

            await update.message.reply_text(f"Balance: ${balance}")

            await temp_client.close()
        except:
            await update.message.reply_text("Balance error")

    elif text == "📊 STATUS":
        await update.message.reply_text(
            f"Trades: {total_trades}\nWins: {wins}\nLosses: {losses}"
        )
        return

    await update.message.reply_text("Updated", reply_markup=reply_markup)

# ================= MAIN =================

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
