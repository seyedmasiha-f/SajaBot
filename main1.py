# main.py
import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# حتماً BOT_TOKEN رو در Environment Variables در Render تنظیم کن
BOT_TOKEN = os.getenv("BOT_TOKEN")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# هندلر ساده برای /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("سلام! ربات شما آماده است.")

if __name__ == "__main__":
    # ساخت اپلیکیشن بدون Updater
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # افزودن هندلر
    app.add_handler(CommandHandler("start", start))
    
    logger.info("Bot is starting...")
    
    # اجرا با polling
    app.run_polling()
