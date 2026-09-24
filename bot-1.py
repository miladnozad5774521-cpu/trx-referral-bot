import os
import sqlite3
from html import escape

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

CHANNEL = "@bitpin9"
REWARD_TRX = 0.5

BOT_TOKEN = os.getenv("BOT_TOKEN")
BASE_URL = os.getenv("BASE_URL", "").rstrip("/")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
PORT = int(os.getenv("PORT", "10000"))

DB_PATH = "bot.db"


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            referrer_id INTEGER,
            balance REAL NOT NULL DEFAULT 0,
            referrals INTEGER NOT NULL DEFAULT 0,
            rewarded INTEGER NOT NULL DEFAULT 0,
            is_member INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()


def get_user(user_id):
    conn = db()
    row = conn.execute(
        "SELECT * FROM users WHERE user_id = ?", (user_id,)
    ).fetchone()
    conn.close()
    return row


def create_or_update_user(user_id, username, referrer_id=None):
    conn = db()
    row = conn.execute(
        "SELECT * FROM users WHERE user_id = ?", (user_id,)
    ).fetchone()

    if row is None:
        if referrer_id == user_id:
            referrer_id = None

        conn.execute(
            """
            INSERT INTO users
            (user_id, username, referrer_id, balance, referrals, rewarded, is_member)
            VALUES (?, ?, ?, 0, 0, 0, 0)
            """,
            (user_id, username or "", referrer_id),
        )
    else:
        conn.execute(
            "UPDATE users SET username = ? WHERE user_id = ?",
            (username or "", user_id),
        )

        # Only save a referral source if the user did not already have one.
        if row["referrer_id"] is None and referrer_id and referrer_id != user_id:
            conn.execute(
                "UPDATE users SET referrer_id = ? WHERE user_id = ?",
                (referrer_id, user_id),
            )

    conn.commit()
    conn.close()


async def is_channel_member(context, user_id):
    try:
        member = await context.bot.get_chat_member(CHANNEL, user_id)

        if member.status in ("member", "administrator", "creator"):
            return True

        # Covers restricted members whose is_member flag is true.
        return bool(getattr(member, "is_member", False))
    except Exception:
        return False


def reward_referrer_if_needed(user_id):
    conn = db()
    user = conn.execute(
        "SELECT * FROM users WHERE user_id = ?", (user_id,)
    ).fetchone()

    if not user or not user["referrer_id"] or user["rewarded"]:
        conn.close()
        return None

    referrer = conn.execute(
        "SELECT * FROM users WHERE user_id = ?",
        (user["referrer_id"],),
    ).fetchone()

    if not referrer:
        conn.close()
        return None

    conn.execute(
        """
        UPDATE users
        SET balance = balance + ?, referrals = referrals + 1
        WHERE user_id = ?
        """,
        (REWARD_TRX, user["referrer_id"]),
    )
    conn.execute(
        "UPDATE users SET rewarded = 1 WHERE user_id = ?",
        (user_id,),
    )
    conn.commit()
    conn.close()
    return user["referrer_id"]


def set_member(user_id):
    conn = db()
    conn.execute(
        "UPDATE users SET is_member = 1 WHERE user_id = ?",
        (user_id,),
    )
    conn.commit()
    conn.close()


def menu_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔗 لینک دعوت من", callback_data="referral"),
            InlineKeyboardButton("💰 موجودی من", callback_data="balance"),
        ],
        [
            InlineKeyboardButton("✅ بررسی عضویت", callback_data="check_membership"),
        ],
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    referrer_id = None

    if context.args:
        try:
            referrer_id = int(context.args[0])
        except ValueError:
            referrer_id = None

    create_or_update_user(user.id, user.username, referrer_id)

    member = await is_channel_member(context, user.id)

    if member:
        set_member(user.id)
        reward_referrer_if_needed(user.id)

        await update.message.reply_text(
            "🎉 عضویت شما تأیید شد.\n\n"
            "از منوی زیر می‌تونی لینک دعوتت و موجودیت رو ببینی.",
            reply_markup=menu_keyboard(),
        )
    else:
        await update.message.reply_text(
            "سلام 👋\n\n"
            "برای استفاده از ربات ابتدا در کانال عضو شو، "
            "بعد روی «بررسی عضویت» بزن.\n\n"
            f"📢 کانال: {CHANNEL}",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "📢 ورود به کانال",
                        url="https://t.me/bitpin9",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "✅ بررسی عضویت",
                        callback_data="check_membership",
                    )
                ],
            ]),
        )


async def referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    me = await context.bot.get_me()
    link = f"https://t.me/{me.username}?start={user.id}"

    row = get_user(user.id)
    referrals = row["referrals"] if row else 0

    text = (
        "🔗 لینک دعوت اختصاصی شما:\n\n"
        f"{link}\n\n"
        f"👥 تعداد دعوت موفق: {referrals}\n"
        f"🎁 پاداش هر دعوت: {REWARD_TRX} TRX"
    )

    await update.message.reply_text(text)


async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    row = get_user(update.effective_user.id)

    if not row:
        await update.message.reply_text("ابتدا /start را بزن.")
        return

    await update.message.reply_text(
        f"💰 موجودی: {row['balance']:.1f} TRX\n"
        f"👥 دعوت موفق: {row['referrals']}"
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user

    if query.data == "referral":
        me = await context.bot.get_me()
        link = f"https://t.me/{me.username}?start={user.id}"
        row = get_user(user.id)
        referrals = row["referrals"] if row else 0

        await query.message.reply_text(
            "🔗 لینک دعوت اختصاصی شما:\n\n"
            f"{link}\n\n"
            f"👥 تعداد دعوت موفق: {referrals}\n"
            f"🎁 پاداش هر دعوت: {REWARD_TRX} TRX"
        )

    elif query.data == "balance":
        row = get_user(user.id)

        if not row:
            await query.message.reply_text("ابتدا /start را بزن.")
            return

        await query.message.reply_text(
            f"💰 موجودی: {row['balance']:.1f} TRX\n"
            f"👥 دعوت موفق: {row['referrals']}"
        )

    elif query.data == "check_membership":
        member = await is_channel_member(context, user.id)

        if not member:
            await query.message.reply_text(
                "❌ هنوز عضویتت تأیید نشد.\n"
                "اول در کانال عضو شو و دوباره روی بررسی عضویت بزن."
            )
            return

        set_member(user.id)
        referrer_id = reward_referrer_if_needed(user.id)

        if referrer_id:
            await query.message.reply_text(
                "✅ عضویت تأیید شد.\n"
                "🎉 دعوت با موفقیت ثبت شد و 0.5 TRX به معرف تعلق گرفت.",
                reply_markup=menu_keyboard(),
            )
        else:
            await query.message.reply_text(
                "✅ عضویت شما تأیید شد.",
                reply_markup=menu_keyboard(),
            )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    print("Telegram error:", context.error)


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable is missing.")

    if not BASE_URL:
        raise RuntimeError(
            "BASE_URL environment variable is missing. "
            "Example: https://your-service.onrender.com"
        )

    if not WEBHOOK_SECRET:
        raise RuntimeError("WEBHOOK_SECRET environment variable is missing.")

    init_db()

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("referral", referral))
    application.add_handler(CommandHandler("balance", balance))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_error_handler(error_handler)

    webhook_url = f"{BASE_URL}/{WEBHOOK_SECRET}"

    print(f"Starting webhook on 0.0.0.0:{PORT}")
    print(f"Webhook URL: {webhook_url}")

    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=WEBHOOK_SECRET,
        webhook_url=webhook_url,
        secret_token=WEBHOOK_SECRET,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
