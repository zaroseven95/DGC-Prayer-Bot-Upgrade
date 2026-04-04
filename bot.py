import sqlite3
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from apscheduler.schedulers.background import BackgroundScheduler

TOKEN = "8370065008:AAG-uXIs808EQ9sw96s7l_X3D89_TFpdreY"
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

# ================= RANK SYSTEM =================

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

# ================= STREAK SYSTEM =================

def update_streak(user_id):
    today = datetime.utcnow().date()

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

# ================= PRAYER =================

async def pray(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_registered(user_id):
        await update.message.reply_text("❌ Register first: /join YourName")
        return

    if user_id in paused_sessions:
        active_sessions[user_id] = datetime.utcnow()
        paused_sessions.pop(user_id)
        await update.message.reply_text("▶️ Resumed prayer 🔥")
        return

    if user_id in active_sessions:
        await update.message.reply_text("⚠️ You are already mounting preasure🔥")
        return

    active_sessions[user_id] = datetime.utcnow()
    await update.message.reply_text("🔥 Prayer started")

# ================= STOP =================

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in active_sessions:
        await update.message.reply_text("❌ Not praying. Soldier, wake-up your strenght lets make Jesus proud")
        return

    start = active_sessions.pop(user_id)
    elapsed = int((datetime.utcnow() - start).total_seconds())

    paused_sessions[user_id] = elapsed

    if elapsed < 7200:
        keyboard = [["▶️ Continue", "🛑 End Prayer"]]

        await update.message.reply_text(
            f"⚠️ {format_duration(elapsed)}\n"
            "🔥 Ahhhh... You are not under atack!🙌 Continue Praying💪🔥",
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

    active_sessions[user_id] = datetime.utcnow()
    await update.message.reply_text("▶️ Continued 🔥")

# ================= END =================

async def end_prayer(update, user_id, duration):
    cursor.execute("""
        INSERT INTO sessions (user_id, start_time, end_time, duration_seconds)
        VALUES (?, ?, ?, ?)
    """, (user_id, str(datetime.utcnow()), str(datetime.utcnow()), duration))

    conn.commit()

    update_streak(user_id)

    await update.message.reply_text(
        f"🔥 Chai! Your Conversion Rate is High. Completed {format_duration(duration)}\n"
        f"🏆 Rank: {get_rank(duration)}"
    )

# ================= STATUS =================

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id in active_sessions:
        duration = int((datetime.utcnow() - active_sessions[user_id]).total_seconds())
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

    rank = get_rank(total)

    await update.message.reply_text(
        f"📊 Total: {format_duration(total)}\n🏆 Rank: {rank}"
    )

# ================= REPORT =================

async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Not authorized.")
        return

    cursor.execute("""
        SELECT users.name, sessions.duration_seconds
        FROM sessions
        JOIN users ON users.user_id = sessions.user_id
        WHERE DATE(start_time) = DATE('now')
    """)

    rows = cursor.fetchall()

    text = "📊 DAILY REPORT\n\n"

    for row in rows:
        text += f"{row[0]} — {format_duration(row[1])}\n"

    await update.message.reply_text(text)

# ================= AUTO REPORT =================

def send_daily_report():
    cursor.execute("""
        SELECT users.name, sessions.duration_seconds
        FROM sessions
        JOIN users ON users.user_id = sessions.user_id
        WHERE DATE(start_time) = DATE('now')
    """)

    rows = cursor.fetchall()

    if not rows:
        return

    text = "📊 AUTO DAILY REPORT\n\n"

    for row in rows:
        text += f"{row[0]} — {format_duration(row[1])}\n"

    # Send to admin
    app.bot.send_message(chat_id=ADMIN_ID, text=text)

# ================= NOTIFICATION =================

async def notify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id in active_sessions:
        await update.message.reply_text("🔥 Stay on the altar! Keep praying!")


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
        await update.message.reply_text("Coming soon...")

    elif text == "📍 Status":
        await status(update, context)


# ================= START =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["🔥 Pray", "⛔ Stop"], ["▶️ Continue", "🛑 End Prayer"], ["📊 My Time", "📍 Status"]]

    await update.message.reply_text(
        "🔥 Soldier, Pick up your sword there is warfare in front. It's time to make Jesus proud.🫡\n/join YourName",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

# ================= JOIN =================

async def join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if len(context.args) == 0:
        await update.message.reply_text("❌ /join YourName")
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
scheduler.add_job(send_daily_report, "cron", hour=23, minute=59)
scheduler.start()

print("🔥 Bot Running 24/7...")
app.run_polling()
