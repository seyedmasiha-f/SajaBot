# main.py
import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# توکن ربات رو از Environment Variable بخون
BOT_TOKEN = os.getenv("BOT_TOKEN")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# هندلر ساده /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("سلام! ربات آماده است.")

if __name__ == "__main__":
    # فقط ApplicationBuilder بدون هیچ Updater
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # اضافه کردن هندلر
    app.add_handler(CommandHandler("start", start))
    
    logger.info("Bot is starting...")
    
    # اجرای polling (نیازی به Updater نیست)
    app.run_polling()
