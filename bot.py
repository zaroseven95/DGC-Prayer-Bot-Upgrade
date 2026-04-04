import sqlite3
from datetime import datetime, timedelta

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from apscheduler.schedulers.background import BackgroundScheduler

# ================= CONFIG =================
TOKEN = "8370065008:AAF8IT7h23ywaEfXRy_MToo_TQOu4xMHLBk"
ADMIN_ID = 6021933432

# ================= DATABASE =================
conn = sqlite3.connect("prayer.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    name TEXT,
    streak INTEGER DEFAULT 0,
    last_prayer_date TEXT
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
paused_sessions = {}

# ================= HELPERS =================

def now():
    return datetime.utcnow() + timedelta(hours=1)

def is_registered(user_id):
    cursor.execute("SELECT name FROM users WHERE user_id=?", (user_id,))
    return cursor.fetchone()

def is_admin(user_id):
    return user_id == ADMIN_ID

def format_duration(seconds):
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h}h {m}m {s}s"

# ================= RANK =================

def get_rank(total_seconds):
    hours = total_seconds // 3600
    if hours < 10:
        return "🪖 Soldier"
    elif hours < 50:
        return "🛡 Captain"
    elif hours < 150:
        return "🔥 General"
    else:
        return "👑 Apostle"

# ================= STREAK =================

def update_streak(user_id):
    today = now().date()

    cursor.execute("SELECT last_prayer_date, streak FROM users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()

    if not row:
        return

    last_date, streak = row

    if last_date:
        last_date = datetime.strptime(last_date, "%Y-%m-%d").date()

        if last_date == today - timedelta(days=1):
            streak += 1
        elif last_date < today - timedelta(days=1):
            streak = 1
    else:
        streak = 1

    cursor.execute("""
        UPDATE users SET streak=?, last_prayer_date=?
        WHERE user_id=?
    """, (streak, str(today), user_id))

    conn.commit()

# ================= PRAY =================

async def pray(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_registered(user_id):
        await update.message.reply_text("❌ Register first: /join YourName")
        return

    if user_id in paused_sessions:
        active_sessions[user_id] = now()
        paused_sessions.pop(user_id)
        await update.message.reply_text("▶️ Resumed prayer 🔥")
        return

    if user_id in active_sessions:
        await update.message.reply_text("⚠️ Already praying 🔥")
        return

    active_sessions[user_id] = now()
    await update.message.reply_text("🔥 Prayer started")

# ================= STOP =================

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in active_sessions:
        await update.message.reply_text("❌ You are not praying.")
        return

    start = active_sessions.pop(user_id)
    elapsed = int((now() - start).total_seconds())

    paused_sessions[user_id] = elapsed

    if elapsed < 7200:
        keyboard = [["▶️ Continue", "🛑 End Prayer"]]

        await update.message.reply_text(
            f"⚠️ {format_duration(elapsed)}\n🔥 Continue pressing!",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
    else:
        await end_prayer(update, user_id, elapsed)

# ================= CONTINUE =================

async def continue_prayer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in paused_sessions:
        await update.message.reply_text("❌ No paused session.")
        return

    active_sessions[user_id] = now()
    await update.message.reply_text("▶️ Continued 🔥")

# ================= END =================

async def end_prayer(update, user_id, duration):
    end_time = now()
    start_time = end_time - timedelta(seconds=duration)

    cursor.execute("""
        INSERT INTO sessions (user_id, start_time, end_time, duration_seconds)
        VALUES (?, ?, ?, ?)
    """, (user_id, str(start_time), str(end_time), duration))

    conn.commit()

    update_streak(user_id)

    await update.message.reply_text(
        f"✅ Completed {format_duration(duration)}\n🏆 Rank: {get_rank(duration)}"
    )

# ================= STATUS =================

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id in active_sessions:
        duration = int((now() - active_sessions[user_id]).total_seconds())
    elif user_id in paused_sessions:
        duration = paused_sessions[user_id]
    else:
        await update.message.reply_text("❌ Not praying.")
        return

    await update.message.reply_text(f"⏱ {format_duration(duration)}")

# ================= MY TIME =================

async def mytime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    cursor.execute("SELECT SUM(duration_seconds) FROM sessions WHERE user_id=?", (user_id,))
    total = cursor.fetchone()[0] or 0

    await update.message.reply_text(
        f"📊 Total: {format_duration(total)}\n🏆 Rank: {get_rank(total)}"
    )

# ================= LEADERBOARD =================

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("""
        SELECT users.name, SUM(sessions.duration_seconds)
        FROM sessions
        JOIN users ON users.user_id = sessions.user_id
        GROUP BY users.user_id
        ORDER BY SUM(sessions.duration_seconds) DESC
        LIMIT 10
    """)

    rows = cursor.fetchall()

    text = "🏆 LEADERBOARD\n\n"

    for i, (name, total) in enumerate(rows, start=1):
        text += f"{i}. {name} — {format_duration(total)}\n"

    await update.message.reply_text(text)

# ================= REPORT =================

async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    cursor.execute("""
        SELECT users.name, sessions.start_time, sessions.end_time, sessions.duration_seconds
        FROM sessions
        JOIN users ON users.user_id = sessions.user_id
        WHERE DATE(start_time) = DATE('now')
        ORDER BY start_time
    """)

    rows = cursor.fetchall()

    text = "📊 DAILY REPORT\n\n"

    for name, start, end, duration in rows:
        text += (
            f"👤 {name}\n"
            f"⏱ Start: {start}\n"
            f"⏹ End: {end}\n"
            f"⏳ {format_duration(duration)}\n\n"
        )

    await update.message.reply_text(text)

# ================= AUTO NOTIFICATION =================

async def notify(context: ContextTypes.DEFAULT_TYPE):
    for user_id, start_time in list(active_sessions.items()):
        elapsed = int((now() - start_time).total_seconds())

        if elapsed >= 7200:
            await context.bot.send_message(
                chat_id=user_id,
                text="🔥 2 HOURS DONE! WELL DONE SOLDIER 🫡"
            )

            await end_prayer_dummy(user_id, elapsed)
            active_sessions.pop(user_id, None)

        elif elapsed % 1800 == 0:  # every 30 mins
            await context.bot.send_message(
                chat_id=user_id,
                text="🔥 Stay on the altar! Keep pushing!"
            )

async def end_prayer_dummy(user_id, duration):
    end_time = now()
    start_time = end_time - timedelta(seconds=duration)

    cursor.execute("""
        INSERT INTO sessions (user_id, start_time, end_time, duration_seconds)
        VALUES (?, ?, ?, ?)
    """, (user_id, str(start_time), str(end_time), duration))

    conn.commit()
    update_streak(user_id)

# ================= BUTTON HANDLER =================

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "🔥 Pray":
        await pray(update, context)
    elif text == "⛔ Stop":
        await stop(update, context)
    elif text == "▶️ Continue":
        await continue_prayer(update, context)
    elif text == "🛑 End Prayer":
        user_id = update.effective_user.id
        if user_id in paused_sessions:
            await end_prayer(update, user_id, paused_sessions[user_id])
            paused_sessions.pop(user_id)
    elif text == "📊 My Time":
        await mytime(update, context)
    elif text == "🏆 Leaderboard":
        await leaderboard(update, context)
    elif text == "📍 Status":
        await status(update, context)

# ================= START =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        ["🔥 Pray", "⛔ Stop"],
        ["▶️ Continue", "🛑 End Prayer"],
        ["📊 My Time", "🏆 Leaderboard"],
        ["📍 Status"]
    ]

    await update.message.reply_text(
        "🔥 Welcome to DGC Abuja Prayer WatchLog\n\nRegister with /join YourName",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

# ================= JOIN =================

async def join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not context.args:
        await update.message.reply_text("❌ Use /join YourName")
        return

    name = " ".join(context.args)

    cursor.execute("REPLACE INTO users (user_id, name) VALUES (?, ?)", (user_id, name))
    conn.commit()

    await update.message.reply_text(f"✅ Registered as {name}")

# ================= APP =================

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("join", join))
app.add_handler(CommandHandler("report", report))

app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))

# ================= SCHEDULER =================

scheduler = BackgroundScheduler()
scheduler.add_job(lambda: app.create_task(notify(None)), "interval", minutes=1)
scheduler.start()

print("🔥 BOT RUNNING...")
app.run_polling()
