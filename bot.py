import logging
import sqlite3
from datetime import datetime, timedelta, time

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ===== CONFIG =====
ADMIN_ID = 6021933432
TOKEN = "8370065008:AAGIcf9711pA7_qle7Cx4GSXmDVY50OVBRo"

logging.basicConfig(level=logging.INFO)

# ===== DATABASE =====
conn = sqlite3.connect("attendance.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    name TEXT,
    streak INTEGER DEFAULT 0,
    last_pray_date TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    start_time TEXT,
    end_time TEXT,
    duration_seconds INTEGER
)
""")

conn.commit()

# ===== ACTIVE SESSIONS =====
active_sessions = {}

# ===== BUTTON MENU =====
menu = ReplyKeyboardMarkup(
    [
        ["🔥 Pray", "⛔ Stop"],
        ["📊 My Time", "🏆 Leaderboard"],
        ["📍 Status"]
    ],
    resize_keyboard=True
)

# ===== HELPERS =====
def get_today_total(user_id):
    today = datetime.utcnow().date()

    cursor.execute("""
        SELECT SUM(duration_seconds)
        FROM sessions
        WHERE user_id = ?
        AND DATE(start_time) = ?
    """, (user_id, str(today)))

    result = cursor.fetchone()[0]
    return result or 0


def update_streak(user_id):
    today = datetime.utcnow().date()

    cursor.execute("SELECT streak, last_pray_date FROM users WHERE user_id=?", (user_id,))
    result = cursor.fetchone()

    if not result:
        return

    streak, last_date = result

    if last_date:
        last_date = datetime.fromisoformat(last_date).date()

        if today == last_date:
            return
        elif today == last_date + timedelta(days=1):
            streak += 1
        else:
            streak = 1
    else:
        streak = 1

    cursor.execute(
        "UPDATE users SET streak=?, last_pray_date=? WHERE user_id=?",
        (streak, today.isoformat(), user_id)
    )
    conn.commit()


def get_rank(total_seconds):
    hours = total_seconds // 3600

    if hours < 5:
        return "🪖 Recruit"
    elif hours < 20:
        return "🔥 Soldier"
    elif hours < 50:
        return "⚔️ Warrior"
    elif hours < 100:
        return "🛡️ Captain"
    else:
        return "👑 General"


# ===== COMMANDS =====

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔥 Welcome to DGC Abuja Prayer WatchLog\n\nChoose an option:",
        reply_markup=menu
    )


async def join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not context.args:
        await update.message.reply_text("❌ Use /join YourName")
        return

    name = " ".join(context.args)

    cursor.execute(
        "INSERT OR REPLACE INTO users (user_id, name) VALUES (?, ?)",
        (user_id, name)
    )
    conn.commit()

    await update.message.reply_text(f"✅ Registered as {name}")


async def pray(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id in active_sessions:
        await update.message.reply_text("⚠️ Already praying")
        return

    active_sessions[user_id] = datetime.utcnow()

    await update.message.reply_text("🔥 Prayer started")


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in active_sessions:
        await update.message.reply_text("❌ You have not started praying")
        return

    start_time = active_sessions.pop(user_id)
    end_time = datetime.utcnow()

    duration = (end_time - start_time).total_seconds()

    cursor.execute(
        "INSERT INTO sessions VALUES (NULL, ?, ?, ?, ?)",
        (user_id, start_time.isoformat(), end_time.isoformat(), int(duration))
    )
    conn.commit()

    update_streak(user_id)

    h = int(duration // 3600)
    m = int((duration % 3600) // 60)
    s = int(duration % 60)

    total_today = get_today_total(user_id)

    if total_today >= 7200:
        msg = (
            f"✅ You stopped at {h}h {m}m {s}s\n\n"
            "🔥 You have completed your 2 hours today.\n"
            "👏 Well done Soldier!"
        )
    else:
        remaining = 7200 - total_today

        msg = (
            f"⛔ You stopped at {h}h {m}m {s}s\n\n"
            "⚠️ You have NOT reached 2 hours yet.\n"
            f"⏳ Remaining: {int(remaining//60)} minutes\n\n"
            "💪 Do not leave the altar incomplete.\n"
            "🔥 Continue pressing until you finish your assignment!"
        )

    await update.message.reply_text(msg)


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in active_sessions:
        await update.message.reply_text("❌ You are not currently praying.")
        return

    start_time = active_sessions[user_id]
    elapsed = (datetime.utcnow() - start_time).total_seconds()

    h = int(elapsed // 3600)
    m = int((elapsed % 3600) // 60)
    s = int(elapsed % 60)

    await update.message.reply_text(
        f"🔥 You are currently praying\n\n⏱ {h}h {m}m {s}s"
    )


async def mytime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    cursor.execute("SELECT SUM(duration_seconds) FROM sessions WHERE user_id=?", (user_id,))
    total = cursor.fetchone()[0] or 0

    h = int(total // 3600)
    m = int((total % 3600) // 60)
    s = int(total % 60)

    cursor.execute("SELECT streak FROM users WHERE user_id=?", (user_id,))
    streak = cursor.fetchone()[0]

    rank = get_rank(total)

    await update.message.reply_text(
        f"📊 Your Stats:\n\n"
        f"⏱ Total: {h}h {m}m {s}s\n"
        f"🔥 Streak: {streak} days\n"
        f"🏆 Rank: {rank}"
    )


async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("""
        SELECT users.name, SUM(sessions.duration_seconds)
        FROM sessions
        JOIN users ON sessions.user_id = users.user_id
        GROUP BY sessions.user_id
        ORDER BY SUM(sessions.duration_seconds) DESC
        LIMIT 10
    """)

    rows = cursor.fetchall()

    message = "🏆 Leaderboard\n\n"

    for i, (name, total) in enumerate(rows, 1):
        h = int(total // 3600)
        m = int((total % 3600) // 60)
        message += f"{i}. {name} — {h}h {m}m\n"

    await update.message.reply_text(message)


# ===== BUTTON HANDLER (FIXED) =====
async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if text == "🔥 Pray":
        await pray(update, context)

    elif text == "⛔ Stop":
        await stop(update, context)

    elif text == "📊 My Time":
        await mytime(update, context)

    elif text == "🏆 Leaderboard":
        await leaderboard(update, context)

    elif text == "📍 Status":
        await status(update, context)


# ===== DAILY REPORT =====
async def send_daily_report(context: ContextTypes.DEFAULT_TYPE):
    today = datetime.utcnow().date()

    cursor.execute("""
        SELECT users.name, sessions.start_time, sessions.end_time, sessions.duration_seconds
        FROM sessions
        JOIN users ON sessions.user_id = users.user_id
        WHERE DATE(sessions.start_time) = ?
    """, (str(today),))

    rows = cursor.fetchall()

    if not rows:
        return

    message = f"📅 Daily Report ({today})\n\n"

    for name, start, end, duration in rows:
        h = int(duration // 3600)
        m = int((duration % 3600) // 60)
        s = int(duration % 60)

        message += (
            f"👤 {name}\n"
            f"🕘 Start: {start}\n"
            f"🕚 End: {end}\n"
            f"⏱ Duration: {h}h {m}m {s}s\n\n"
        )

    await context.bot.send_message(chat_id=ADMIN_ID, text=message)


# ===== MAIN =====
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("join", join))
app.add_handler(CommandHandler("pray", pray))
app.add_handler(CommandHandler("stop", stop))
app.add_handler(CommandHandler("status", status))

app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))

job_queue = app.job_queue
if job_queue:
    job_queue.run_daily(send_daily_report, time=time(23, 0))

print("🚀 Bot is running...")
app.run_polling()
