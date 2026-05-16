import os
import logging
from io import BytesIO

from telegram import Update
from telegram.ext import (
    Application,
    MessageHandler,
    CommandHandler,
    ContextTypes,
    filters
)

from PIL import Image
import numpy as np

# ================= CONFIG =================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN missing")

# ================= LOGGING =================

logging.basicConfig(level=logging.INFO)

# ================= AI LOGIC =================

def analyze_chart(image: Image.Image) -> str:
    img = image.convert("L")
    arr = np.array(img)

    h, w = arr.shape
    section = w // 5

    values = []
    for i in range(5):
        part = arr[:, i * section:(i + 1) * section]
        values.append(np.mean(part))

    trend = values[3] - values[0]

    if trend > 0:
        return "BUY"
    else:
        return "SELL"

# ================= HANDLERS =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send chart screenshot 📸")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send screenshot 📸")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        photo = update.message.photo[-1]
        file = await photo.get_file()

        bio = BytesIO()
        await file.download_to_memory(out=bio)
        bio.seek(0)

        image = Image.open(bio)

        result = analyze_chart(image)

        await update.message.reply_text(result)

    except Exception as e:
        logging.error(e)
        await update.message.reply_text("Error")

# ================= MAIN =================

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # FIX: add handlers for EVERYTHING
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    print("Bot running...")

    app.run_polling()

if __name__ == "__main__":
    main()