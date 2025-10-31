# main.py
import os
import io
import csv
import time
import pytz
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputFile, Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, ConversationHandler,
    MessageHandler, ContextTypes, filters
)
import httpx

# ====== CONFIG ======
BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = "https://alvvqmbaiqpcbqjoqnuc.supabase.co"
SERVICE_ROLE_KEY = "YOUR_SERVICE_ROLE_KEY"
# ===================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

HEADERS = {
    "apikey": SERVICE_ROLE_KEY,
    "Authorization": f"Bearer {SERVICE_ROLE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

# Conversation states
(C_TITLE, C_TEXT, C_PASS, C_TARGET, C_CONFIRM) = range(5)
(S_NAME, S_CITY) = range(5, 7)
(SEARCH_QUERY,) = range(7, 8)
(EXP_CAMPAIGN, EXP_PASSWORD) = range(8, 10)
(ADMIN_PASSWORD,) = range(10, 11)


# ---------- Supabase async helpers ----------
async def sb_post(table: str, obj):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(url, json=obj, headers=HEADERS)
        r.raise_for_status()
        return r.json()

async def sb_get(table: str, params: dict | None = None):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url, params=params, headers=HEADERS)
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


# ---------- Utility ----------
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
    if args:
        param = args[0]
        if param.startswith("cmp_"):
            cid = param
            rows = await sb_get("campaigns", params={"id": f"eq.{cid}"})
            if not rows:
                await update.message.reply_text("کارزار پیدا نشد.")
                return
            c = rows[0]
            text = f"📣 *{c['title']}*\n\n{c.get('text','')}\n\n👥 هدف: {c.get('target','(مشخص نشده)')}\n\nوضعیت: {'پایان‌یافته' if c.get('finished') else 'در جریان'}"
            await update.message.reply_text(text, reply_markup=campaign_buttons(bot_username, cid), parse_mode="Markdown")
            return
    await update.message.reply_text("سلام! خوش آمدید. لطفاً یکی از گزینه‌های زیر را انتخاب کنید:", reply_markup=main_menu_buttons(context.bot.username))


# --- Callback router ---
async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    bot_username = context.bot.username

    if data == "create":
        await query.message.reply_text("لطفاً عنوانِ کارزار را وارد نمایید:")
        return C_TITLE

    if data == "search":
        await query.message.reply_text("لطفاً عنوان یا بخشی از عنوان کارزار را وارد کنید تا جستجو کنم:")
        return SEARCH_QUERY

    if data == "list_campaigns":
        camps = await sb_get("campaigns", params={"select":"id,title,created_at", "order":"created_at.desc", "limit":"50"})
        if not camps:
            await query.message.reply_text("فعلاً کارزاری ثبت نشده است.")
            return ConversationHandler.END
        lines = [f"• {c['title']}\nلینک: https://t.me/{bot_username}?start={c['id']}\n" for c in camps]
        await query.message.reply_text("\n".join(lines))
        return ConversationHandler.END

    if data.startswith("sign|"):
        _, cid = data.split("|",1)
        rows = await sb_get("campaigns", params={"id": f"eq.{cid}"})
        if not rows:
            await query.message.reply_text("کارزار پیدا نشد.")
            return ConversationHandler.END
        if rows[0].get("finished"):
            await query.message.reply_text("این کارزار قبلاً پایان یافته است.")
            return ConversationHandler.END
        context.user_data["campaign_id"] = cid
        await query.message.reply_text("لطفاً *نام و نام‌خانوادگی* خود را وارد نمایید:", parse_mode="Markdown")
        return S_NAME

    if data.startswith("admin|"):
        _, cid = data.split("|",1)
        context.user_data["admin_campaign"] = cid
        await query.message.reply_text("رمز مدیریتی کارزار را وارد نمایید:")
        return ADMIN_PASSWORD

    await query.message.reply_text("دستور نامشخص.")
    return ConversationHandler.END


# ---------- Build application ----------
def build_app():
    iran_tz = pytz.timezone("Asia/Tehran")
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.job_queue.scheduler.configure(timezone=iran_tz)

    # ConversationHandlers
    create_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(callback_router, pattern="^create$")],
        states={
            C_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, lambda u,c: u.message.reply_text("تکمیل نشده"))],  # نمونه
        },
        fallbacks=[],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_router, pattern="^(create|search|list_campaigns)$"))

    return app


if __name__ == "__main__":
    app = build_app()
    logger.info("Starting bot...")
    app.run_polling()
