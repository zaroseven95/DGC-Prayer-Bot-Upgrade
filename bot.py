import sqlite3
from datetime import datetime, timedelta

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from apscheduler.schedulers.background import BackgroundScheduler

# ================= CONFIG =================
TOKEN = "8370065008:AAGMFPrXnOR2MmiXb0edtFIqrAOea_tX3SA"
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
awaiting_name = set()

# ================= HELPERS =================

def now():
    return datetime.utcnow() + timedelta(hours=1)

def is_registered(user_id):
    cursor.execute("SELECT name FROM users WHERE user_id=?", (user_id,))
    return cursor.fetchone()

def format_duration(seconds):
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h}h {m}m {s}s"

# ================= MENU =================

def main_menu(registered=True):
    if not registered:
        return ReplyKeyboardMarkup([
            ["📝 Register"],
            ["📘 Guide", "🏆 Leaderboard"],
            ["👥 Live Room"]
        ], resize_keyboard=True)

    return ReplyKeyboardMarkup([
        ["🔥 Pray", "⛔ Stop"],
        ["▶️ Continue", "🛑 End Prayer"],
        ["📊 My Time", "🏆 Leaderboard"],
        ["📍 Status", "📘 Guide"],
        ["👥 Live Room"]
    ], resize_keyboard=True)

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

# ================= PRAY =================

async def pray(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id in paused_sessions:
        paused_time = paused_sessions.pop(user_id)
        active_sessions[user_id] = now() - timedelta(seconds=paused_time)
        await update.message.reply_text("▶️ Resumed prayer 🔥", reply_markup=main_menu())
        return

    if user_id in active_sessions:
        await update.message.reply_text("⚠️ Already praying 🔥")
        return

    active_sessions[user_id] = now()
    await update.message.reply_text("🔥 Prayer started", reply_markup=main_menu())

# ================= STOP =================

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in active_sessions:
        await update.message.reply_text("❌ You are not praying.")
        return

    start = active_sessions.pop(user_id)
    elapsed = int((now() - start).total_seconds())

    paused_sessions[user_id] = elapsed

    keyboard = [["▶️ Continue", "🛑 End Prayer"]]

    await update.message.reply_text(
        f"⏸ Paused at {format_duration(elapsed)}",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

# ================= CONTINUE =================

async def continue_prayer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in paused_sessions:
        await update.message.reply_text("❌ No paused session.")
        return

    paused_time = paused_sessions.pop(user_id)
    active_sessions[user_id] = now() - timedelta(seconds=paused_time)

    await update.message.reply_text("▶️ Continued 🔥", reply_markup=main_menu())

# ================= END =================

async def end_prayer(update, user_id, duration):
    if duration < 7200:
        await update.message.reply_text(
            f"⚠️ You prayed {format_duration(duration)}\n❌ Minimum is 2 hours."
        )
        return

    end_time = now()
    start_time = end_time - timedelta(seconds=duration)

    cursor.execute("""
        INSERT INTO sessions (user_id, start_time, end_time, duration_seconds)
        VALUES (?, ?, ?, ?)
    """, (user_id, str(start_time), str(end_time), duration))

    conn.commit()

    await update.message.reply_text(
        f"✅ Completed {format_duration(duration)}",
        reply_markup=main_menu()
    )

# ================= LIVE ROOM =================

async def live_room(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not active_sessions:
        await update.message.reply_text("😴 No one is currently praying.")
        return

    text = "🔥 LIVE PRAYER ROOM\n\n"

    for user_id, start_time in active_sessions.items():
        cursor.execute("SELECT name FROM users WHERE user_id=?", (user_id,))
        name = cursor.fetchone()[0]

        duration = int((now() - start_time).total_seconds())
        text += f"👤 {name}\n⏱ {format_duration(duration)}\n\n"

    await update.message.reply_text(text)

# ================= REGISTER FLOW =================

async def register_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    awaiting_name.add(user_id)

    await update.message.reply_text("📝 Enter your name to register:")

async def handle_name_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id in awaiting_name:
        name = update.message.text

        cursor.execute("REPLACE INTO users (user_id, name) VALUES (?, ?)", (user_id, name))
        conn.commit()

        awaiting_name.remove(user_id)

        await update.message.reply_text(
            f"✅ Registered as {name}",
            reply_markup=main_menu(True)
        )

# ================= BUTTON HANDLER =================

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    registered = is_registered(user_id)

    # handle name input first
    if user_id in awaiting_name:
        await handle_name_input(update, context)
        return

    # REGISTER BUTTON
    if text == "📝 Register":
        await register_prompt(update, context)
        return

    # ALLOWED WITHOUT REGISTRATION
    if text in ["📘 Guide", "🏆 Leaderboard", "👥 Live Room"]:
        pass
    else:
        if not registered:
            await update.message.reply_text(
                "❌ Please register first",
                reply_markup=main_menu(False)
            )
            return

    # REGISTERED FEATURES
    if text == "🔥 Pray":
        await pray(update, context)
    elif text == "⛔ Stop":
        await stop(update, context)
    elif text == "▶️ Continue":
        await continue_prayer(update, context)
    elif text == "🛑 End Prayer":
        if user_id in paused_sessions:
            await end_prayer(update, user_id, paused_sessions[user_id])
            paused_sessions.pop(user_id)
    elif text == "📊 My Time":
        await mytime(update, context)
    elif text == "🏆 Leaderboard":
        await leaderboard(update, context)
    elif text == "📍 Status":
        await status(update, context)
    elif text == "📘 Guide":
        await guide(update, context)
    elif text == "👥 Live Room":
        await live_room(update, context)

# ================= OTHER =================

async def mytime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cursor.execute("SELECT SUM(duration_seconds) FROM sessions WHERE user_id=?", (user_id,))
    total = cursor.fetchone()[0] or 0

    await update.message.reply_text(f"📊 Total: {format_duration(total)}")

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

async def guide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📘 HOW TO USE\n\n🔥 Pray → Start\n⛔ Stop → Pause\n▶️ Continue → Resume\n🛑 End → Finish\n\n⏱ 2hrs minimum"
    )

# ================= START =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    registered = is_registered(user_id)

    await update.message.reply_text(
        "🔥 Welcome to Prayer WatchLog",
        reply_markup=main_menu(bool(registered))
    )

# ================= APP =================

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))

# ================= SCHEDULER =================

scheduler = BackgroundScheduler()
scheduler.start()

print("🔥 BOT RUNNING...")
app.run_polling()
