import sqlite3
from datetime import datetime, timedelta, timezone

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# ================= CONFIG =================
# Replace 'YOUR_NEW_TOKEN_HERE' with your new token from BotFather
TOKEN = "8370065008:AAGsEWWzR3jv3T3deUIHK_928UPjJFF5MKM" 
ADMIN_ID = 6021933432

# ================= DATABASE =================
conn = sqlite3.connect("prayer.db", check_same_thread=False)
cursor = conn.cursor()

# Updated table creation to ensure streaks aren't lost
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
    # Adjusted to UTC+1 as per your original logic
    return datetime.now(timezone.utc) + timedelta(hours=1)

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

# ================= LOGIC =================

async def pray(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id in paused_sessions:
        # Resume from pause
        paused_time = paused_sessions.pop(user_id)
        active_sessions[user_id] = now() - timedelta(seconds=paused_time)
        await update.message.reply_text("▶️ Resumed prayer 🔥", reply_markup=main_menu())
        return

    if user_id in active_sessions:
        await update.message.reply_text("⚠️ Already praying 🔥")
        return

    active_sessions[user_id] = now()
    await update.message.reply_text("🔥 Prayer started", reply_markup=main_menu())

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in active_sessions:
        await update.message.reply_text("❌ You are not currently praying.")
        return

    start_time = active_sessions.pop(user_id)
    elapsed = int((now() - start_time).total_seconds())
    paused_sessions[user_id] = elapsed

    await update.message.reply_text(
        f"⏸ Paused at {format_duration(elapsed)}",
        reply_markup=main_menu()
    )

async def end_prayer(update: Update, user_id: int, duration: int):
    # Minimum 2 hours check
    if duration < 7200:
        await update.message.reply_text(
            f"⚠️ You only prayed {format_duration(duration)}.\n❌ A minimum of 2 hours is required to save the session."
        )
        return

    end_time = now()
    start_time_val = end_time - timedelta(seconds=duration)

    cursor.execute("""
        INSERT INTO sessions (user_id, start_time, end_time, duration_seconds)
        VALUES (?, ?, ?, ?)
    """, (user_id, str(start_time_val), str(end_time), duration))
    conn.commit()

    await update.message.reply_text(
        f"✅ Session Saved!\n⏱ Total: {format_duration(duration)}",
        reply_markup=main_menu()
    )

# ================= HANDLERS =================

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    registered = is_registered(user_id)

    # 1. Handle registration input
    if user_id in awaiting_name:
        cursor.execute("""
            INSERT INTO users (user_id, name) VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET name=excluded.name
        """, (user_id, text))
        conn.commit()
        awaiting_name.remove(user_id)
        await update.message.reply_text(f"✅ Registered as {text}", reply_markup=main_menu(True))
        return

    # 2. Public buttons
    if text == "📝 Register":
        awaiting_name.add(user_id)
        await update.message.reply_text("📝 Enter your name to register:")
        return
    elif text == "📘 Guide":
        await guide(update, context)
        return
    elif text == "🏆 Leaderboard":
        await leaderboard(update, context)
        return
    elif text == "👥 Live Room":
        await live_room(update, context)
        return

    # 3. Check registration for private actions
    if not registered:
        await update.message.reply_text("❌ Please register first", reply_markup=main_menu(False))
        return

    # 4. Registered actions
    if text == "🔥 Pray":
        await pray(update, context)
    elif text == "⛔ Stop":
        await stop(update, context)
    elif text == "▶️ Continue":
        await pray(update, context) # Same logic as starting/resuming
    elif text == "🛑 End Prayer":
        if user_id in paused_sessions:
            duration = paused_sessions.pop(user_id)
            await end_prayer(update, user_id, duration)
        elif user_id in active_sessions:
            start_time = active_sessions.pop(user_id)
            duration = int((now() - start_time).total_seconds())
            await end_prayer(update, user_id, duration)
        else:
            await update.message.reply_text("❌ You don't have an active session.")
    elif text == "📊 My Time":
        await mytime(update, context)
    elif text == "📍 Status":
        await status(update, context)

# ================= VIEWS =================

async def live_room(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not active_sessions:
        await update.message.reply_text("😴 No one is currently praying.")
        return

    text = "🔥 LIVE PRAYER ROOM\n\n"
    for uid, start_t in active_sessions.items():
        cursor.execute("SELECT name FROM users WHERE user_id=?", (uid,))
        res = cursor.fetchone()
        name = res[0] if res else "Unknown User"
        duration = int((now() - start_t).total_seconds())
        text += f"👤 {name}\n⏱ {format_duration(duration)}\n\n"
    await update.message.reply_text(text)

async def mytime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cursor.execute("SELECT SUM(duration_seconds) FROM sessions WHERE user_id=?", (user_id,))
    total = cursor.fetchone()[0] or 0
    await update.message.reply_text(f"📊 Your Total Prayer Time: {format_duration(total)}")

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("""
        SELECT users.name, SUM(sessions.duration_seconds) as total
        FROM sessions
        JOIN users ON users.user_id = sessions.user_id
        GROUP BY users.user_id
        ORDER BY total DESC LIMIT 10
    """)
    rows = cursor.fetchall()
    text = "🏆 LEADERBOARD\n\n"
    for i, (name, total) in enumerate(rows, start=1):
        text += f"{i}. {name} — {format_duration(total)}\n"
    await update.message.reply_text(text or "No data yet!")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in active_sessions:
        duration = int((now() - active_sessions[user_id]).total_seconds())
        state = "Praying 🔥"
    elif user_id in paused_sessions:
        duration = paused_sessions[user_id]
        state = "Paused ⏸"
    else:
        await update.message.reply_text("❌ You are not praying.")
        return
    await update.message.reply_text(f"Status: {state}\n⏱ {format_duration(duration)}")

async def guide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📘 HOW TO USE\n\n"
        "🔥 Pray -> Start or Resume\n"
        "⛔ Stop -> Pause session\n"
        "🛑 End Prayer -> Save session\n\n"
        "⚠️ Sessions under 2 hours will not be saved."
    )

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    registered = is_registered(user_id)
    await update.message.reply_text(
        "🔥 Welcome to Prayer WatchLog",
        reply_markup=main_menu(bool(registered))
    )

# ================= APP =================

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start_cmd))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))

print("🔥 BOT RUNNING...")
app.run_polling()
