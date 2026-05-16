import os
import cv2
import numpy as np
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# --------- IMPROVED ANALYSIS ----------
def analyze_chart(path):
    img = cv2.imread(path)

    if img is None:
        return "SELL"

    try:
        # Resize for consistency
        img = cv2.resize(img, (400, 250))
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        h, w = gray.shape

        candles = []

        # Split chart into segments (each ~1 candle)
        segments = 12
        step = w // segments

        for i in range(segments):
            region = gray[:, i*step:(i+1)*step]

            if region.size == 0:
                continue

            # Top and bottom of "price"
            top = np.argmax(np.mean(region, axis=1))
            bottom = np.argmin(np.mean(region, axis=1))

            candles.append((top, bottom))

        if len(candles) < 6:
            return "SELL"

        # Focus on last 5 candles → analyze 4
        last = candles[-5:]

        buyers = 0
        sellers = 0

        for i in range(1, len(last)):
            prev_top, prev_bot = last[i-1]
            curr_top, curr_bot = last[i]

            # Movement direction
            if curr_top < prev_top:
                buyers += 1
            else:
                sellers += 1

            # Strength (body size)
            prev_body = abs(prev_top - prev_bot)
            curr_body = abs(curr_top - curr_bot)

            if curr_body > prev_body:
                if curr_top < prev_top:
                    buyers += 1
                else:
                    sellers += 1

        # Final control decision
        if buyers > sellers:
            return "BUY"
        else:
            return "SELL"

    except:
        return "SELL"


# --------- TELEGRAM ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send screenshot")

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
        await update.message.reply_text("Error")


# --------- MAIN ----------
if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    print("Bot running...")
    app.run_polling()