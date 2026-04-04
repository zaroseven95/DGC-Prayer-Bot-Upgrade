import logging
import sqlite3
from datetime import datetime, time

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ===== CONFIG =====
ADMIN_ID = 6021933432
TOKEN = "8370065008:AAFwJzuq9amFdP3VBdZWUDElOH5p9wV10sA"  # 🔴 REPLACE THIS

logging.basicConfig(level=logging.INFO)

# ===== DATABASE =====
conn = sqlite3.connect("attendance.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    name TEXT,
    streak INTEGER DEFAULT 0
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

# ===== GLOBALS =====
active_sessions = {}

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

# ===== COMMANDS =====

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔥 Dear Soldier, Welcome to Your Duty Post\n\n"
        "Use /join YourName\n"
        "Use /pray\n"
        "Use /stop\n"
        "Use /mytime\n"
        "Use /leaderboard\n"
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
    await update.message.reply_text("🔥 Prayer started (24/7 allowed)")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in active_sessions:
        await update.message.reply_text("❌ You have not started")
        return

    start_time = active_sessions.pop(user_id)
    end_time = datetime.utcnow()

    duration = (end_time - start_time).total_seconds()

    if duration < 60:
        await update.message.reply_text("⚠️ Prayer session too short.")
        return

    cursor.execute(
        "INSERT INTO sessions (user_id, start_time, end_time, duration_seconds) VALUES (?, ?, ?, ?)",
        (user_id, start_time.isoformat(), end_time.isoformat(), int(duration))
    )
    conn.commit()

    total_today = get_today_total(user_id)

    if total_today >= 7200:
        msg = "✅ You have completed your 2 hours today. Well done 🫡"
    else:
        remaining = 7200 - total_today
        msg = f"🔥 You still need {int(remaining // 60)} minutes today."

    h = duration // 3600
    m = (duration % 3600) // 60
    s = duration % 60

    await update.message.reply_text(
        f"⛔ Stopped\n⏱️ {int(h)}h {int(m)}m {int(s)}s\n\n{msg}"
    )

async def mytime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    cursor.execute("SELECT SUM(duration_seconds) FROM sessions WHERE user_id=?", (user_id,))
    total = cursor.fetchone()[0] or 0

    h = total // 3600
    m = (total % 3600) // 60

    await update.message.reply_text(f"📊 Total: {int(h)}h {int(m)}m")

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("""
        SELECT users.name, SUM(sessions.duration_seconds) as total
        FROM sessions
        JOIN users ON sessions.user_id = users.user_id
        GROUP BY sessions.user_id
        ORDER BY total DESC
        LIMIT 10
    """)

    rows = cursor.fetchall()

    if not rows:
        await update.message.reply_text("No data yet.")
        return

    message = "🏆 Leaderboard:\n\n"

    for i, (name, total) in enumerate(rows, start=1):
        hours = total // 3600
        minutes = (total % 3600) // 60
        message += f"{i}. {name} — {int(hours)}h {int(minutes)}m\n"

    await update.message.reply_text(message)

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Not authorized")
        return

    if not context.args:
        await update.message.reply_text("❌ Use: /broadcast message")
        return

    message = " ".join(context.args)

    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()

    for (user_id,) in users:
        try:
            await context.bot.send_message(chat_id=user_id, text=message)
        except:
            pass

    await update.message.reply_text("✅ Broadcast sent!")

# ===== BACKGROUND TASKS =====

async def check_two_hours(context: ContextTypes.DEFAULT_TYPE):
    for user_id, start_time in list(active_sessions.items()):
        elapsed = (datetime.utcnow() - start_time).total_seconds()

        if elapsed >= 7200:
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text="⏱️ 2 hours reached — I Salute you, Soldier 🫡"
                )
            except:
                pass

            active_sessions.pop(user_id, None)

# 🔥 DAILY REMINDER (if user hasn't reached 2 hours)
async def remind_users(context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()

    for (user_id,) in users:
        total_today = get_today_total(user_id)

        if total_today < 7200:
            remaining = 7200 - total_today
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"🔥 Reminder: You still need {int(remaining//60)} minutes of prayer today."
                )
            except:
                pass

# 📊 DAILY REPORT TO ADMIN
async def send_daily_report(context: ContextTypes.DEFAULT_TYPE):
    today = datetime.utcnow().date()

    cursor.execute("""
        SELECT users.name, SUM(sessions.duration_seconds)
        FROM sessions
        JOIN users ON sessions.user_id = users.user_id
        WHERE DATE(sessions.start_time) = ?
        GROUP BY sessions.user_id
    """, (str(today),))

    rows = cursor.fetchall()

    if not rows:
        return

    message = f"📅 Daily Report ({today})\n\n"

    for name, total in rows:
        minutes = total // 60
        message += f"{name} — {int(minutes)} minutes\n"

    await context.bot.send_message(chat_id=ADMIN_ID, text=message)

# ===== MAIN =====

app = ApplicationBuilder().token(TOKEN).build()

# Handlers
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("join", join))
app.add_handler(CommandHandler("pray", pray))
app.add_handler(CommandHandler("stop", stop))
app.add_handler(CommandHandler("mytime", mytime))
app.add_handler(CommandHandler("leaderboard", leaderboard))
app.add_handler(CommandHandler("broadcast", broadcast))

# Job Queue
job_queue = app.job_queue

if job_queue:
    job_queue.run_repeating(check_two_hours, interval=60, first=10)

    job_queue.run_daily(remind_users, time=time(18, 0))  # 6 PM reminder
    job_queue.run_daily(send_daily_report, time=time(23, 0))  # 11 PM report

print("🚀 Bot is running...")
app.run_polling()