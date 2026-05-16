import os
import numpy as np
import cv2
from telegram import Update
from telegram.ext import Application, MessageHandler, ContextTypes, filters

# ================= CONFIG =================

TOKEN = os.getenv("TELEGRAM_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

if not TOKEN:
    raise ValueError("TELEGRAM_TOKEN missing")

# ================= IMAGE ANALYSIS =================

def calculate_rsi(prices, period=14):
    prices = np.array(prices)
    delta = np.diff(prices)

    gain = np.maximum(delta, 0)
    loss = -np.minimum(delta, 0)

    avg_gain = np.mean(gain[-period:])
    avg_loss = np.mean(loss[-period:])

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def analyze_chart(image_path):
    img = cv2.imread(image_path)

    if img is None:
        return None

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # detect edges (rough candle detection)
    edges = cv2.Canny(gray, 50, 150)

    # simulate candle extraction from brightness (simple approach)
    height, width = gray.shape

    # divide into 5 vertical zones (5 candles)
    step = width // 5
    closes = []

    for i in range(5):
        region = gray[:, i * step:(i + 1) * step]
        closes.append(np.mean(region))

    closes = np.array(closes)

    # ================= INDICATORS =================

    # EMA 50 (approx using simple average due to limited data)
    ema = np.mean(closes)

    # RSI
    rsi = calculate_rsi(closes)

    # Bollinger Bands
    mean = np.mean(closes)
    std = np.std(closes)
    upper = mean + 2 * std
    lower = mean - 2 * std

    last = closes[-1]

    # ================= LOGIC =================

    buyers = 0
    sellers = 0

    # last 4 candles trend
    for i in range(1, 5):
        if closes[i] > closes[i - 1]:
            buyers += 1
        else:
            sellers += 1

    # RSI logic
    if rsi > 50:
        buyers += 1
    else:
        sellers += 1

    # EMA logic
    if last > ema:
        buyers += 1
    else:
        sellers += 1

    # Bollinger logic
    if last < lower:
        buyers += 1
    elif last > upper:
        sellers += 1

    # ================= FINAL SIGNAL =================

    if buyers > sellers:
        return "BUY"
    else:
        return "SELL"


# ================= TELEGRAM HANDLER =================

async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return

    photo = update.message.photo[-1]
    file = await photo.get_file()

    path = "chart.jpg"
    await file.download_to_drive(path)

    result = analyze_chart(path)

    if result:
        await update.message.reply_text(result)
    else:
        await update.message.reply_text("Error")


# ================= MAIN =================

def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(MessageHandler(filters.PHOTO, handle_image))

    print("AI Bot Running...")
    app.run_polling()


if __name__ == "__main__":
    main()