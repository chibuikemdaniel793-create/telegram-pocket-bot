import cv2
import numpy as np
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
import os

TOKEN = os.getenv("TELEGRAM_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

def analyze_chart(path):
    img = cv2.imread(path)

    if img is None:
        return "BUY"

    h, w, _ = img.shape

    # ===== MAIN CHART AREA =====
    chart = img[int(h*0.2):int(h*0.75), int(w*0.4):int(w*0.95)]

    hsv = cv2.cvtColor(chart, cv2.COLOR_BGR2HSV)

    # Candle colors
    green_mask = cv2.inRange(hsv, (35,50,50), (85,255,255))
    red_mask1 = cv2.inRange(hsv, (0,70,50), (10,255,255))
    red_mask2 = cv2.inRange(hsv, (170,70,50), (180,255,255))
    red_mask = red_mask1 + red_mask2

    # ===== SPLIT LAST 4 CANDLES =====
    sections = np.array_split(range(chart.shape[1]), 4)

    bulls = 0
    bears = 0

    for sec in sections:
        g = np.sum(green_mask[:, sec] > 0)
        r = np.sum(red_mask[:, sec] > 0)

        if g > r:
            bulls += 1
        else:
            bears += 1

    candle_signal = "BUY" if bulls >= 3 else "SELL"

    # ===== EMA (trend direction via line slope) =====
    gray = cv2.cvtColor(chart, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)

    lines = cv2.HoughLinesP(edges, 1, np.pi/180, 50, minLineLength=50, maxLineGap=10)

    ema_signal = "BUY"
    if lines is not None:
        slopes = []
        for line in lines[:10]:
            x1,y1,x2,y2 = line[0]
            if x2 != x1:
                slope = (y2 - y1) / (x2 - x1)
                slopes.append(slope)

        if slopes:
            avg = np.mean(slopes)
            ema_signal = "BUY" if avg < 0 else "SELL"

    # ===== RSI AREA (bottom strip) =====
    rsi_area = img[int(h*0.75):int(h*0.9), int(w*0.4):int(w*0.95)]

    avg_color = np.mean(rsi_area)

    if avg_color > 140:
        rsi_signal = "SELL"   # overbought
    elif avg_color < 90:
        rsi_signal = "BUY"    # oversold
    else:
        rsi_signal = "BUY"

    # ===== BOLLINGER (price position) =====
    top_band = np.mean(chart[0:int(chart.shape[0]*0.2)])
    bottom_band = np.mean(chart[int(chart.shape[0]*0.8):])

    if top_band > bottom_band:
        boll_signal = "SELL"
    else:
        boll_signal = "BUY"

    # ===== FINAL DECISION =====
    signals = [candle_signal, ema_signal, rsi_signal, boll_signal]

    buy_count = signals.count("BUY")
    sell_count = signals.count("SELL")

    if buy_count >= 3:
        return "BUY"
    else:
        return "SELL"

# ===== TELEGRAM =====
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return

    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)

    path = "chart.jpg"
    await file.download_to_drive(path)

    result = analyze_chart(path)

    await update.message.reply_text(result)

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.PHOTO, handle))

    print("Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()