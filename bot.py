import sqlite3
from datetime import datetime, timedelta, timezone
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# ================= CONFIG =================
# ⚠️ REPLACE WITH A NEW TOKEN FROM BOTFATHER
TOKEN = "8370065008:AAG_8-fXJ3Giiivm9ZSJZHQ6ISncBuPCokg" 
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
    # Adjusting to UTC+1 (e.g., West Africa Time)
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

def main_menu(user_id):
    registered = is_registered(user_id)
    
    if not registered:
        keyboard = [
            ["📝 Register"],
            ["📘 Guide", "🏆 Leaderboard"],
            ["👥 Live Room"]
        ]
    else:
        keyboard = [
            ["🔥 Mount Pressure"],
            ["▶️ Continue", "🛑 End Prayer"],
            ["📊 My Time", "🏆 Leaderboard"],
            ["📍 Status", "📘 Guide"],
            ["👥 Live Room"]
        ]
    
    if user_id == ADMIN_ID:
        keyboard.append(["⚙️ Admin Report"])

    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ================= LOGIC =================

async def pray(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in paused_sessions:
        paused_time = paused_sessions.pop(user_id)
        active_sessions[user_id] = now() - timedelta(seconds=paused_time)
        await update.message.reply_text("▶️ Back to battlefield 🔥", reply_markup=main_menu(user_id))
        return
    if user_id in active_sessions:
        await update.message.reply_text("⚠️ Already mounting pressure 🔥")
        return
    active_sessions[user_id] = now()
    await update.message.reply_text("🔥 You are mounting pressure", reply_markup=main_menu(user_id))

async def end_prayer_logic(update: Update, user_id: int, duration: int):
    # Rule: 7200 seconds = 2 hours
    if duration < 7200:
        await update.message.reply_text(
            f"⏱ Session: {format_duration(duration)}\n\n"
            "⚠️ Ah! You are not under attack, soldier. Why do you want to abscond? Get back to the battlefield!\n\n"
            "Minimum 2 hours required to save. Your time is preserved in 'Continue'."
        )
        return False

    end_time = now()
    start_time_val = end_time - timedelta(seconds=duration)
    cursor.execute("""
        INSERT INTO sessions (user_id, start_time, end_time, duration_seconds)
        VALUES (?, ?, ?, ?)
    """, (user_id, start_time_val.strftime('%Y-%m-%d %H:%M:%S'), end_time.strftime('%Y-%m-%d %H:%M:%S'), duration))
    conn.commit()

    await update.message.reply_text(
        f"✅ Completed: {format_duration(duration)}\n\n"
        "🔥 Chai! Your Conversion Rate is High. Welldone!",
        reply_markup=main_menu(user_id)
    )
    return True

# ================= ADMIN FEATURE =================

async def admin_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("🚫 Unauthorized.")
        return

    cursor.execute("""
        SELECT users.name, sessions.start_time, sessions.end_time, sessions.duration_seconds
        FROM sessions
        JOIN users ON users.user_id = sessions.user_id
        ORDER BY sessions.id DESC
        LIMIT 20
    """)
    rows = cursor.fetchall()

    if not rows:
        await update.message.reply_text("📂 No prayer records found.")
        return

    report = "📋 **RECENT PRAYER RECORDS**\n\n"
    for name, start, end, duration in rows:
        date_str = start.split(" ")[0]
        report += (
            f"👤 **{name}**\n"
            f"📅 Date: {date_str}\n"
            f"🕒 Start: {start.split(' ')[1]}\n"
            f"🕓 End: {end.split(' ')[1]}\n"
            f"⏱ Total: {format_duration(duration)}\n"
            f"--- --- --- ---\n"
        )
    
    if len(report) > 4000: report = report[:3900] + "\n... (Truncated)"
    await update.message.reply_text(report, parse_mode="Markdown")

# ================= HANDLERS =================

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE
