import sqlite3
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

TOKEN = "8370065008:AAFEoJpf6F5e78x9fZtOW5YNbJBvO8o2rRQ"

# 👑 ADMIN ID (CHANGE THIS)
ADMIN_ID = 6021933432

# ================= DATABASE =================
conn = sqlite3.connect("prayer.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    name TEXT
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

# ================= MEMORY =================
active_sessions = {}

# ================= HELPERS =================
def is_registered(user_id):
    cursor.execute("SELECT name FROM users WHERE user_id=?", (user_id,))
    return cursor.fetchone()

def is_admin(user_id):
    return user_id == ADMIN_ID

def format_duration(seconds):
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours}h {minutes}m {secs}s"


# ================= COMMANDS =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["🔥 Pray", "⛔ Stop"], ["📊 My Time", "📍 Status"], ["🏆 Leaderboard"]]

    await update.message.reply_text(
        "🔥 Welcome Soldier\n\nRegister first:\n/join YourName",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )


async def join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if len(context.args) == 0:
        await update.message.reply_text("❌ Use: /join YourName")
        return

    name = " ".join(context.args)

    cursor.execute("REPLACE INTO users (user_id, name) VALUES (?, ?)", (user_id, name))
    conn.commit()

    await update.message.reply_text(f"✅ Registered as {name}")


async def pray(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_registered(user_id):
        await update.message.reply_text("❌ You must register first.\nUse: /join YourName")
        return

    if user_id in active_sessions:
        await update.message.reply_text("⚠️ Already praying")
        return

    active_sessions[user_id] = datetime.utcnow()

    await update.message.reply_text("🔥 Prayer started")


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_registered(user_id):
        await update.message.reply_text("❌ Register first.")
        return

    if user_id not in active_sessions:
        await update.message.reply_text("❌ You are not praying.")
        return

    start_time = active_sessions.pop(user_id)
    end_time = datetime.utcnow()

    duration = int((end_time - start_time).total_seconds())

    cursor.execute("""
        INSERT INTO sessions (user_id, start_time, end_time, duration_seconds)
        VALUES (?, ?, ?, ?)
    """, (user_id, str(start_time), str(end_time), duration))

    conn.commit()

    if duration < 7200:
        await update.message.reply_text(
            f"⚠️ You prayed for {format_duration(duration)}\n"
            "🔥 Continue until 2 hours!"
        )
    else:
        await update.message.reply_text(
            f"🔥 Completed {format_duration(duration)}\nWell done Soldier!"
        )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in active_sessions:
        await update.message.reply_text("❌ You are not currently praying")
        return

    start_time = active_sessions[user_id]
    duration = int((datetime.utcnow() - start_time).total_seconds())

    await update.message.reply_text(
        f"🔥 You are praying\n\n⏱ {format_duration(duration)}"
    )


async def mytime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    cursor.execute("SELECT SUM(duration_seconds) FROM sessions WHERE user_id=?", (user_id,))
    total = cursor.fetchone()[0] or 0

    await update.message.reply_text(f"📊 Total Time:\n⏱ {format_duration(total)}")


async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("""
        SELECT users.name, SUM(sessions.duration_seconds) as total
        FROM sessions
        JOIN users ON sessions.user_id = users.user_id
        GROUP BY users.user_id
        ORDER BY total DESC
    """)

    rows = cursor.fetchall()

    text = "🏆 Leaderboard\n\n"
    for i, row in enumerate(rows, start=1):
        text += f"{i}. {row[0]} — {format_duration(row[1])}\n"

    await update.message.reply_text(text)


# ================= ADMIN REPORT =================

async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_admin(user_id):
        await update.message.reply_text("❌ Not authorized.")
        return

    cursor.execute("""
        SELECT users.name, sessions.start_time, sessions.end_time, sessions.duration_seconds
        FROM sessions
        JOIN users ON sessions.user_id = users.user_id
        WHERE DATE(sessions.start_time) = DATE('now')
    """)

    rows = cursor.fetchall()

    if not rows:
        await update.message.reply_text("📊 No activity today.")
        return

    text = "📊 DAILY REPORT\n\n"

    for row in rows:
        name, start, end, duration = row
        text += f"""👤 {name}
🕘 Start: {start}
🕚 End: {end}
⏱ Duration: {format_duration(duration)}

"""

    await update.message.reply_text(text)


# ================= BUTTONS =================

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


# ================= APP =================

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("join", join))
app.add_handler(CommandHandler("report", report))

app.add_handler(CommandHandler("pray", pray))
app.add_handler(CommandHandler("stop", stop))
app.add_handler(CommandHandler("status", status))
app.add_handler(CommandHandler("mytime", mytime))
app.add_handler(CommandHandler("leaderboard", leaderboard))

app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))

print("🔥 DGC Abuja Prayer WatchLog is running...")
app.run_polling()
