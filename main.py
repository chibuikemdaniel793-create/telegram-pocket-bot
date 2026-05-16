import os
import cv2
import numpy as np
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# --------- INDICATORS FROM IMAGE ---------
def calculate_rsi(prices):
    gains = []
    losses = []

    for i in range(1, len(prices)):
        diff = prices[i] - prices[i - 1]
        if diff > 0:
            gains.append(diff)
        else:
            losses.append(abs(diff))

    avg_gain = np.mean(gains) if gains else 0
    avg_loss = np.mean(losses) if losses else 1

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def analyze_chart(image_path):
    img = cv2.imread(image_path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    h, w = gray.shape
    sections = 20  # simulate candles
    step = w // sections

    closes = []

    # --------- EXTRACT PRICE LINE (approx) ---------
    for i in range(sections):
        region = gray[:, i * step:(i + 1) * step]

        # find brightest row (price line approx)
        row_means = np.mean(region, axis=1)
        price_level = np.argmax(row_means)

        closes.append(price_level)

    closes = np.array(closes)

    # --------- LAST 4 CANDLES ----------
    last4 = closes[-5:]

    buyers = 0
    sellers = 0

    for i in range(1, len(last4)):
        if last4[i] < last4[i - 1]:
            buyers += 1   # price going up (chart inverted)
        else:
            sellers += 1

    # --------- EMA 50 (approx) ----------
    ema50 = np.mean(closes[-50:]) if len(closes) >= 50 else np.mean(closes)

    # --------- RSI ----------
    rsi = calculate_rsi(closes[-14:])

    # --------- Bollinger Bands ----------
    mean = np.mean(closes)
    std = np.std(closes)
    upper = mean + 2 * std
    lower = mean - 2 * std

    current = closes[-1]

    # --------- APPLY YOUR STRATEGY ----------

    # EMA logic
    if current < ema50:
        buyers += 1
    else:
        sellers += 1

    # RSI logic
    if rsi < 50:
        buyers += 1
    else:
        sellers += 1

    # Bollinger logic
    if current < lower:
        buyers += 1
    elif current > upper:
        sellers += 1

    # --------- FINAL DECISION ----------
    if buyers > sellers:
        return "BUY"
    else:
        return "SELL"


# --------- TELEGRAM ---------
async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = await update.message.photo[-1].get_file()
    path = "chart.jpg"
    await file.download_to_drive(path)

    result = analyze_chart(path)

    await update.message.reply_text(result)


# --------- MAIN ---------
if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(MessageHandler(filters.PHOTO, handle_image))

    print("AI Strategy Bot Running...")
    app.run_polling()