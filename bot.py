import os
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN", "PUT_YOUR_BOT_TOKEN_HERE")
CHANNEL = "@bitpin9"
REWARD_TRX = 0.5
DB = "bot.db"

def db():
    con = sqlite3.connect(DB)
    con.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        referrer_id INTEGER,
        balance REAL DEFAULT 0,
        referrals INTEGER DEFAULT 0,
        rewarded INTEGER DEFAULT 0
    )""")
    con.commit()
    return con

def add_user(user_id, username, referrer_id=None):
    con=db()
    row=con.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,)).fetchone()
    if not row:
        if referrer_id == user_id:
            referrer_id=None
        con.execute("INSERT INTO users(user_id,username,referrer_id) VALUES(?,?,?)",
                    (user_id, username or "", referrer_id))
        con.commit()
    con.close()

async def is_member(context, user_id):
    try:
        m = await context.bot.get_chat_member(CHANNEL, user_id)
        return m.status in ("member", "administrator", "creator")
    except Exception:
        return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u=update.effective_user
    ref=None
    if context.args:
        try: ref=int(context.args[0])
        except ValueError: pass
    add_user(u.id, u.username, ref)

    kb=[
        [InlineKeyboardButton("📢 عضویت در کانال", url="https://t.me/bitpin9")],
        [InlineKeyboardButton("✅ بررسی عضویت", callback_data="check")]
    ]
    await update.message.reply_text(
        "سلام 👋\nبرای فعال شدن سیستم زیرمجموعه، ابتدا در کانال عضو شو و سپس «بررسی عضویت» را بزن.",
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query
    await q.answer()
    uid=q.from_user.id
    if not await is_member(context, uid):
        await q.edit_message_text(
            "❌ هنوز عضویتت در کانال تأیید نشده.\nابتدا عضو @bitpin9 شو و دوباره بررسی کن.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📢 عضویت در کانال", url="https://t.me/bitpin9")],
                [InlineKeyboardButton("🔄 بررسی دوباره", callback_data="check")]
            ])
        )
        return

    con=db()
    row=con.execute("SELECT referrer_id, rewarded FROM users WHERE user_id=?", (uid,)).fetchone()
    if row and row[0] and not row[1]:
        ref=row[0]
        # فقط وقتی پاداش می‌دهیم که دعوت‌کننده واقعاً کاربر دیگری باشد.
        ref_exists=con.execute("SELECT user_id FROM users WHERE user_id=?", (ref,)).fetchone()
        if ref_exists:
            con.execute("UPDATE users SET balance=balance+?, referrals=referrals+1 WHERE user_id=?",
                        (REWARD_TRX, ref))
        con.execute("UPDATE users SET rewarded=1 WHERE user_id=?", (uid,))
        con.commit()
    con.close()

    await q.edit_message_text(
        "✅ عضویت شما تأیید شد.\n\n"
        "برای دریافت زیرمجموعه، لینک دعوت اختصاصی خودت را از /referral بگیر."
    )

async def referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u=update.effective_user
    add_user(u.id, u.username)
    me=await context.bot.get_me()
    link=f"https://t.me/{me.username}?start={u.id}"
    con=db()
    row=con.execute("SELECT balance, referrals FROM users WHERE user_id=?", (u.id,)).fetchone()
    con.close()
    bal, refs = row if row else (0,0)
    await update.message.reply_text(
        f"🔗 لینک دعوت اختصاصی تو:\n{link}\n\n"
        f"👥 زیرمجموعه‌ها: {refs}\n"
        f"💰 موجودی: {bal:.1f} TRX\n\n"
        "هر کاربر واجد شرایط که با لینک تو وارد شود و عضویت کانال او تأیید شود، "
        "۰٫۵ TRX به موجودی تو اضافه می‌کند."
    )

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u=update.effective_user
    add_user(u.id, u.username)
    con=db()
    row=con.execute("SELECT balance, referrals FROM users WHERE user_id=?", (u.id,)).fetchone()
    con.close()
    await update.message.reply_text(
        f"💰 موجودی: {row[0]:.1f} TRX\n👥 زیرمجموعه‌ها: {row[1]}"
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/start - شروع\n"
        "/referral - لینک دعوت و آمار\n"
        "/balance - موجودی و تعداد زیرمجموعه"
    )

def main():
    if BOT_TOKEN == "PUT_YOUR_BOT_TOKEN_HERE":
        raise RuntimeError("BOT_TOKEN را در متغیر محیطی تنظیم کنید.")
    db()
    app=Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("referral", referral))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CallbackQueryHandler(check, pattern="^check$"))
    app.run_polling()

if __name__ == "__main__":
    main()
