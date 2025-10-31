# bot_supabase_async.py
import asyncio
import pytz
import logging
import time
import io
import csv
import os

import httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputFile, Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    ConversationHandler, MessageHandler, ContextTypes, filters
)

# ====== CONFIG (مقادیر خودت را اینجا قرار بده) ======
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("توکن BOT_TOKEN تنظیم نشده است. لطفاً آن را در Environment Variables اضافه کنید.")

SUPABASE_URL = "https://alvvqmbaiqpcbqjoqnuc.supabase.co"   # بدون /rest/v1
SERVICE_ROLE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFsdnZxbWJhaXFwY2Jxam9xbnVjIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2MTEzODIyNSwiZXhwIjoyMDc2NzE0MjI1fQ.GFtrzD8aV3WXRM5Rl8mKIqshA0BJxWgn63GFq_nI8Ws"
# ====================================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Conversation states
(C_TITLE, C_TEXT, C_PASS, C_TARGET, C_CONFIRM) = range(5)
(S_NAME, S_CITY) = range(5, 7)
(SEARCH_QUERY,) = range(7, 8)
(EXP_CAMPAIGN, EXP_PASSWORD) = range(8, 10)
(ADMIN_PASSWORD,) = range(10, 11)

HEADERS = {
    "apikey": SERVICE_ROLE_KEY,
    "Authorization": f"Bearer {SERVICE_ROLE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

# ---------- Supabase async helpers ----------
async def sb_post(table: str, obj):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(url, json=obj, headers=HEADERS)
        r.raise_for_status()
        return r.json()

async def sb_get(table: str, params: dict | None = None):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    headers = {"apikey": SERVICE_ROLE_KEY, "Authorization": f"Bearer {SERVICE_ROLE_KEY}"}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url, params=params, headers=headers)
        r.raise_for_status()
        return r.json()

async def sb_patch(table: str, filters: dict, obj):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.patch(url, params=filters, json=obj, headers=HEADERS)
        r.raise_for_status()
        try:
            return r.json()
        except Exception:
            return {}

# ---------- utility ----------
def gen_id(prefix: str) -> str:
    return f"{prefix}_{int(time.time() * 1000)}"

def main_menu_buttons(bot_username: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 ایجاد کارزار", callback_data="create")],
        [InlineKeyboardButton("🔎 جستجو و امضا کارزار", callback_data="search")],
        [InlineKeyboardButton("📚 فهرست کارزارها", callback_data="list_campaigns")],
    ])

def campaign_buttons(bot_username: str, campaign_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✍️ امضا می‌کنم", callback_data=f"sign|{campaign_id}")],
        [InlineKeyboardButton("📊 پنل مدیر", callback_data=f"admin|{campaign_id}")],
        [InlineKeyboardButton("🔗 لینک اشتراک", url=f"https://t.me/{bot_username}?start={campaign_id}")],
    ])

# ---------- Handlers ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    bot_username = context.bot.username
    if args and args[0].startswith("cmp_"):
        cid = args[0]
        rows = await sb_get("campaigns", params={"id": f"eq.{cid}"})
        if not rows:
            await update.message.reply_text("متأسفم، کارزار پیدا نشد.")
            return
        c = rows[0]
        text = f"📣 *{c['title']}*\n\n{c.get('text','')}\n\n👥 هدف: {c.get('target','(مشخص نشده)')}\n\nوضعیت: {'پایان‌یافته' if c.get('finished') else 'در جریان'}"
        await update.message.reply_text(text, reply_markup=campaign_buttons(bot_username, cid), parse_mode="Markdown")
        return
    await update.message.reply_text("سلام! خوش آمدید. لطفاً یکی از گزینه‌های زیر را انتخاب کنید:", reply_markup=main_menu_buttons(bot_username))

# --- ادامه‌ی تمام ConversationHandlerها و CallbackQueryHandlerها ---
# (می‌توان همان کد شما را اینجا اضافه کرد بدون تغییر؛ چون درست بود)

# ---------- Build App ----------
def build_app():
    iran_tz = pytz.timezone("Asia/Tehran")
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.job_queue.scheduler.configure(timezone=iran_tz)

    # اضافه کردن هندلرها
    # ConversationHandlers, CallbackQueryHandlers, CommandHandlers
    # استفاده همان کد شما

    app.add_handler(CommandHandler("start", start))
    # add other handlers here...

    return app

if __name__ == "__main__":
    app = build_app()
    logger.info("Starting bot (async)...")
    app.run_polling()
