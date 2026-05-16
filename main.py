import os
import cv2
import numpy as np
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# --------- ANALYSIS (SAFE + STABLE) ----------
def analyze_chart(path):
    img = cv2.imread(path)

    # Safety check
    if img is None:
        return "SELL"

    try:
        # Resize for speed and stability
        img = cv2.resize(img, (400, 250))
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape

        prices = []

        # Extract price path from image
        for x in range(0, w, 10):
            column = gray[:, x]
            if column.size == 0:
                continue

            y = int(np.argmax(column))
            prices.append(y)

        # Need at least 5 points (4 movements)
        if len(prices) < 5:
            return "SELL"

        last = prices[-5:]

        buyers_force = 0
        sellers_force = 0

        # Measure movement strength (control)
        for i in range(1, len(last)):
            move = last[i-1] - last[i]

            if move > 0:
                buyers_force += move
            else:
                sellers_force += abs(move)

        # Final decision
        if buyers_force > sellers_force:
            return "BUY"
        else:
            return "SELL"

    except:
        return "SELL"


# --------- TELEGRAM HANDLERS ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send screenshot")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        msg = await update.message.reply