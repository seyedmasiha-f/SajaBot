# bot_supabase_async.py
import asyncio
import pytz
import logging
import time
import io
import csv
from datetime import datetime

import httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputFile, Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    ConversationHandler, MessageHandler, ContextTypes, filters
)


# ====== CONFIG (مقادیر خودت را اینجا قرار بده) ======
BOT_TOKEN = "8305045668:AAEr88lQ5o3rhEkUsCLgP3O1anr3C1TqhbA"
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
        # may return [] depending on settings
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

# ---------- handlers ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    bot_username = context.bot.username
    if args:
        param = args[0]
        if param.startswith("cmp_"):
            cid = param
            rows = await sb_get("campaigns", params={"id": f"eq.{cid}"})
            if not rows:
                await update.message.reply_text("متأسفم، کارزار پیدا نشد.")
                return
            c = rows[0]
            text = f"📣 *{c['title']}*\n\n{c.get('text','')}\n\n👥 هدف: {c.get('target','(مشخص نشده)')}\n\nوضعیت: {'پایان‌یافته' if c.get('finished') else 'در جریان'}"
            await update.message.reply_text(text, reply_markup=campaign_buttons(bot_username, cid), parse_mode="Markdown")
            return
    await update.message.reply_text("سلام! خوش آمدید. لطفاً یکی از گزینه‌های زیر را انتخاب کنید:", reply_markup=main_menu_buttons(context.bot.username))

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
        lines = []
        for c in camps:
            lines.append(f"• {c['title']}\nلینک: https://t.me/{bot_username}?start={c['id']}\n")
        await query.message.reply_text("\n".join(lines))
        return ConversationHandler.END

    if data.startswith("sign|"):
        _, cid = data.split("|",1)
        rows = await sb_get("campaigns", params={"id": f"eq.{cid}"})
        if not rows:
            await query.message.reply_text("کارزار پیدا نشد.")
            return ConversationHandler.END
        if rows[0].get("finished"):
            await query.message.reply_text("این کارزار قبلاً پایان یافته و امکان امضا وجود ندارد.")
            return ConversationHandler.END
        context.user_data["campaign_id"] = cid
        await query.message.reply_text("لطفاً *نام و نام‌خانوادگی* خود را وارد نمایید:", parse_mode="Markdown")
        return S_NAME

    if data.startswith("admin|"):
        _, cid = data.split("|",1)
        context.user_data["admin_campaign"] = cid
        await query.message.reply_text("برای ورود به پنلِ مدیر، لطفاً رمز مدیریتیِ کارزار را وارد نمایید:")
        return ADMIN_PASSWORD

    await query.message.reply_text("دستور نامشخص.")
    return ConversationHandler.END

# --- Create campaign steps ---
async def c_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["c_title"] = update.message.text.strip()
    await update.message.reply_text("متن کاملِ کارزار را لطفاً وارد کنید:")
    return C_TEXT

async def c_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["c_text"] = update.message.text.strip()
    await update.message.reply_text("یک رمزِ مدیریتی برایِ کارزار تعیین کنید (این رمز برای دریافت خروجی و مدیریت استفاده می‌شود):")
    return C_PASS

async def c_pass(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["c_pass"] = update.message.text.strip()
    await update.message.reply_text("افراد هدف کارزار (مثلاً: ساکنین شهر X، دانش‌آموزان، ...) را بنویسید (اختیاری):")
    return C_TARGET

async def c_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["c_target"] = update.message.text.strip()
    txt = (f"خلاصهٔ کارزار:\n\nعنوان: {context.user_data['c_title']}\n\n"
           f"متن: {context.user_data['c_text']}\n\nهدف: {context.user_data['c_target']}\n\n"
           "اگر تأیید می‌کنید لطفاً دستور /confirm را ارسال کنید؛ در غیر این صورت /cancel")
    await update.message.reply_text(txt)
    return C_CONFIRM

async def c_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = gen_id("cmp")
    obj = {
        "id": cid,
        "title": context.user_data['c_title'],
        "text": context.user_data['c_text'],
        "admin_pass": context.user_data['c_pass'],
        "target": context.user_data.get('c_target','')
    }
    await sb_post("campaigns", [obj])
    link = f"https://t.me/{context.bot.username}?start={cid}"
    await update.message.reply_text(f"کارزار با موفقیت ساخته شد ✅\nلینکِ اشتراک:\n{link}")
    for k in ["c_title","c_text","c_pass","c_target"]:
        context.user_data.pop(k, None)
    return ConversationHandler.END

# --- Sign steps ---
async def s_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    if not name:
        await update.message.reply_text("نام نباید خالی باشد. لطفاً نام و نام‌خانوادگی را وارد کنید:")
        return S_NAME
    context.user_data["sig_name"] = name
    await update.message.reply_text("لطفاً نامِ شهر یا محلِ اقامت خود را وارد نمایید (اختیاری):")
    return S_CITY

async def s_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    city = update.message.text.strip()
    cid = context.user_data.get("campaign_id")
    if not cid:
        await update.message.reply_text("خطا: شناسهٔ کارزار یافت نشد. لطفاً مجدداً تلاش کنید.")
        return ConversationHandler.END
    sid = gen_id("sig")
    obj = {"id": sid, "campaign_id": cid, "tg_user_id": update.effective_user.id, "name": context.user_data.get("sig_name"), "city": city}
    existing = await sb_get("signatures", params={"campaign_id": f"eq.{cid}", "tg_user_id": f"eq.{update.effective_user.id}"})
    if existing:
        await update.message.reply_text("شما پیش‌تر این کارزار را امضا کرده‌اید. متشکریم.")
        context.user_data.pop("campaign_id", None)
        context.user_data.pop("sig_name", None)
        return ConversationHandler.END
    await sb_post("signatures", [obj])
    await update.message.reply_text("با تشکر؛ امضای شما ثبت شد ✅")
    context.user_data.pop("campaign_id", None)
    context.user_data.pop("sig_name", None)
    return ConversationHandler.END

# --- Search ---
async def search_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.message.text.strip()
    if not q:
        await update.message.reply_text("لطفاً متنی برای جستجو وارد کنید.")
        return ConversationHandler.END
    params = {"title": f"ilike.*{q}*", "order":"created_at.desc", "limit":"8", "select":"id,title,created_at"}
    hits = await sb_get("campaigns", params=params)
    if not hits:
        await update.message.reply_text("چیزی پیدا نشد.")
        return ConversationHandler.END
    buttons = []
    for h in hits:
        buttons.append([InlineKeyboardButton(h['title'], callback_data=f"open|{h['id']}")])
    await update.message.reply_text("نتایجِ جستجو — یکی را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(buttons))
    return ConversationHandler.END

async def callback_open_campaign(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith("open|"):
        _, cid = data.split("|",1)
        rows = await sb_get("campaigns", params={"id": f"eq.{cid}"})
        if not rows:
            await query.message.reply_text("کارزار پیدا نشد.")
            return
        c = rows[0]
        text = f"📣 *{c['title']}*\n\n{c.get('text','')}\n\n👥 هدف: {c.get('target','(مشخص نشده)')}\n\nوضعیت: {'پایان‌یافته' if c.get('finished') else 'در جریان'}"
        await query.message.reply_text(text, reply_markup=campaign_buttons(context.bot.username, cid), parse_mode="Markdown")
    else:
        await query.message.reply_text("نامشخص.")

# --- Admin panel flow ---
async def admin_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pw = update.message.text.strip()
    cid = context.user_data.get("admin_campaign")
    if not cid:
        await update.message.reply_text("شناسهٔ کارزار موجود نیست.")
        return ConversationHandler.END
    rows = await sb_get("campaigns", params={"id": f"eq.{cid}"})
    if not rows:
        await update.message.reply_text("کارزار پیدا نشد.")
        return ConversationHandler.END
    c = rows[0]
    if c.get("admin_pass") != pw:
        await update.message.reply_text("رمز اشتباه است.")
        return ConversationHandler.END
    sigs = await sb_get("signatures", params={"campaign_id": f"eq.{cid}", "select":"id,name,city,created_at", "order":"created_at.asc"})
    txt = f"پنل مدیر — {c['title']}\n\nتعداد امضاها: {len(sigs)}"
    buttons = [
        [InlineKeyboardButton("📥 دریافت خروجی CSV", callback_data=f"export|{cid}")],
        [InlineKeyboardButton("✅ پایان دادن به کارزار", callback_data=f"finish|{cid}")],
        [InlineKeyboardButton("📋 نمایش امضاها", callback_data=f"list_sigs|{cid}")]
    ]
    await update.message.reply_text(txt, reply_markup=InlineKeyboardMarkup(buttons))
    return ConversationHandler.END

async def admin_actions_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith("export|"):
        _, cid = data.split("|",1)
        sigs = await sb_get("signatures", params={"campaign_id": f"eq.{cid}", "select":"id,tg_user_id,name,city,created_at", "order":"created_at.asc"})
        si = io.StringIO()
        writer = csv.writer(si)
        writer.writerow(["sig_id","campaign_id","tg_user_id","name","city","created_at"])
        for s in sigs:
            writer.writerow([s["id"], cid, s["tg_user_id"], s["name"], s.get("city",""), s["created_at"]])
        si.seek(0)
        bio = io.BytesIO(si.read().encode("utf-8"))
        bio.name = f"{cid}_signatures.csv"
        await query.message.reply_document(document=InputFile(bio, filename=bio.name))
        si.close()
        return
    if data.startswith("finish|"):
        _, cid = data.split("|",1)
        await sb_patch("campaigns", {"id": f"eq.{cid}"}, {"finished": True})
        await query.message.reply_text("کارزار با موفقیت پایان یافت. ثبت امضای جدید ممنوع است.")
        return
    if data.startswith("list_sigs|"):
        _, cid = data.split("|",1)
        sigs = await sb_get("signatures", params={"campaign_id": f"eq.{cid}", "select":"name,city,created_at", "order":"created_at.asc"})
        if not sigs:
            await query.message.reply_text("هیچ امضایی وجود ندارد.")
            return
        lines = [f"{i+1}. {s['name']} — {s.get('city','(نامشخص)')} — {s['created_at']}" for i,s in enumerate(sigs)]
        await query.message.reply_text("\n".join(lines))
        return
    await query.message.reply_text("عملیات نامشخص.")

# --- Export commands (alternative) ---
async def export_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("لطفاً شناسهٔ کارزار را وارد کنید (مانند cmp_xxxxxxx):")
    return EXP_CAMPAIGN

async def export_campaign(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = update.message.text.strip()
    context.user_data["exp_campaign"] = cid
    await update.message.reply_text("لطفاً رمز مدیریتی کارزار را وارد کنید:")
    return EXP_PASSWORD

async def export_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pw = update.message.text.strip()
    cid = context.user_data.get("exp_campaign")
    rows = await sb_get("campaigns", params={"id": f"eq.{cid}"})
    if not rows:
        await update.message.reply_text("کارزار پیدا نشد.")
        return ConversationHandler.END
    if rows[0].get("admin_pass") != pw:
        await update.message.reply_text("رمز اشتباه است.")
        return ConversationHandler.END
    sigs = await sb_get("signatures", params={"campaign_id": f"eq.{cid}", "select":"id,tg_user_id,name,city,created_at", "order":"created_at.asc"})
    si = io.StringIO()
    writer = csv.writer(si)
    writer.writerow(["sig_id","campaign_id","tg_user_id","name","city","created_at"])
    for s in sigs:
        writer.writerow([s["id"], cid, s["tg_user_id"], s["name"], s.get("city",""), s["created_at"]])
    si.seek(0)
    bio = io.BytesIO(si.read().encode("utf-8"))
    bio.name = f"{cid}_signatures.csv"
    await update.message.reply_document(document=InputFile(bio, filename=bio.name))
    context.user_data.pop("exp_campaign", None)
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("لغو شد. در صورت نیاز دوباره گزینهٔ مورد نظر را انتخاب کنید.")
    return ConversationHandler.END

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("متأسفم؛ متوجه نشدم. لطفاً از منوی اصلی یک گزینه انتخاب کنید یا /start را ارسال نمایید.")

def build_app():
    iran_tz = pytz.timezone("Asia/Tehran")
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.job_queue.scheduler.configure(timezone=iran_tz)



    create_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(callback_router, pattern="^create$")],
        states={
            C_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, c_title)],
            C_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, c_text)],
            C_PASS: [MessageHandler(filters.TEXT & ~filters.COMMAND, c_pass)],
            C_TARGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, c_target)],
            C_CONFIRM: [CommandHandler("confirm", c_confirm), CommandHandler("cancel", cancel)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    sign_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(callback_router, pattern="^sign\\|")],
        states={
            S_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, s_name)],
            S_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, s_city)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    search_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(callback_router, pattern="^search$")],
        states={SEARCH_QUERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_query)]},
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    admin_pw_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(callback_router, pattern="^admin\\|")],
        states={ADMIN_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_password)]},
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    export_conv = ConversationHandler(
        entry_points=[CommandHandler("export", export_start)],
        states={EXP_CAMPAIGN: [MessageHandler(filters.TEXT & ~filters.COMMAND, export_campaign)],
                EXP_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, export_password)]},
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(create_conv)
    app.add_handler(sign_conv)
    app.add_handler(search_conv)
    app.add_handler(admin_pw_conv)
    app.add_handler(export_conv)

    app.add_handler(CallbackQueryHandler(callback_open_campaign, pattern="^open\\|"))
    app.add_handler(CallbackQueryHandler(admin_actions_router, pattern="^(export\\||finish\\||list_sigs\\|)"))
    app.add_handler(CallbackQueryHandler(callback_router, pattern="^(create|search|list_campaigns)$"))

    app.add_handler(MessageHandler(filters.COMMAND, unknown))

    return app

if __name__ == "__main__":
    app = build_app()
    logger.info("Starting bot (async)...")
    app.run_polling()
