import os
import cv2
import numpy as np
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# --------- CORE ANALYSIS ----------
def analyze_chart(path):
    img = cv2.imread(path)

    # Resize for speed + stability
    img = cv2.resize(img, (400, 250))

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape

    # Detect "price line" using brightest pixels per column
    prices = []

    for x in range(0, w, 10):
        column = gray[:, x]
        y = np.argmax(column)  # brightest point (approx price)
        prices.append(y)

    prices = np.array(prices)

    # Smooth noise
    prices = cv2.GaussianBlur(prices, (5, 5), 0)

    # Take last 5 points → gives 4 movements
    last = prices[-5:]

    buyers_force = 0
    sellers_force = 0

    for i in range(1, len(last)):
        move = last[i-1] - last[i]  # inverted (screen coordinates)

        if move > 0:
            buyers_force += abs(move)
        else:
            sellers_force += abs(move)

    # --------- FINAL DECISION ----------
    if buyers_force > sellers_force:
        return "BUY"
    else:
        return "SELL"


# --------- TELEGRAM ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send chart screenshot")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        msg = await update.message.reply_text("Analyzing...")

        photo = update.message.photo[-1]
        file = await photo.get_file()

        path = "chart.jpg"
        await file.download_to_drive(path)

        result = analyze_chart(path)

        await msg.edit_text(result)

    except:
        await update.message.reply_text("Error processing image")


# --------- MAIN ----------
if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    print("Bot running...")
    app.run_polling()