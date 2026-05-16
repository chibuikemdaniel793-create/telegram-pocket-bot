import cv2
import numpy as np
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

import os

TOKEN = os.getenv("TELEGRAM_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

def analyze_chart(image_path):
    img = cv2.imread(image_path)

    if img is None:
        return "BUY"

    h, w, _ = img.shape

    crop = img[int(h*0.2):int(h*0.8), int(w*0.2):int(w*0.8)]

    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)

    green_lower = np.array([35, 50, 50])
    green_upper = np.array([85, 255, 255])
    green_mask = cv2.inRange(hsv, green_lower, green_upper)

    red_lower1 = np.array([0, 70, 50])
    red_upper1 = np.array([10, 255, 255])
    red_lower2 = np.array([170, 70, 50])
    red_upper2 = np.array([180, 255, 255])

    red_mask1 = cv2.inRange(hsv, red_lower1, red_upper1)
    red_mask2 = cv2.inRange(hsv, red_lower2, red_upper2)
    red_mask = red_mask1 + red_mask2

    green_pixels = cv2.countNonZero(green_mask)
    red_pixels = cv2.countNonZero(red_mask)

    if green_pixels > red_pixels:
        return "BUY"
    else:
        return "SELL"

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return

    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)

    file_path = "chart.jpg"
    await file.download_to_drive(file_path)

    result = analyze_chart(file_path)

    await update.message.reply_text(result)

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    print("Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()