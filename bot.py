import os
import sqlite3
import logging
from datetime import datetime, timedelta, timezone

from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ================= CONFIG =================
TOKEN = os.getenv("8370065008:AAF_-AW-GJbCUM14JMEsV6FzGIH3yLlgpVI")  # <-- KEEP THIS FOR HOSTING
# TOKEN = "8370065008:AAF_-AW-GJbCUM14JMEsV6FzGIH3yLlgpVI"  # <-- USE THIS ONLY FOR LOCAL TESTING

ADMIN_ID = 6021933432
PRAYER_DRIVE_LINK = "https://t.me/c/3754852727/885"

# ================= LOGGING =================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
    duration_seconds INTEGER,
    created_date TEXT
)
""")

conn.commit()

# ================= MEMORY =================
active_sessions = {}
awaiting_name = set()

# ================= HELPERS =================
def now():
    return datetime.now(timezone.utc) + timedelta(hours=1)

def today():
    return now().strftime('%Y-%m-%d')

def is_within_time_window():
    current_time = now().time()
    start = datetime.strptime("20:40", "%H:%M").time()
    end = datetime.strptime("23:20", "%H:%M").time()
    return start <= current_time <= end

def format_duration(seconds):
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h}h {m}m {s}s"

def main_menu():
    return ReplyKeyboardMarkup(
        [["🔥 Mount Pressure", "🛑 End Prayer"], ["📝 Register", "📂 Prayer Drive"]],
        resize_keyboard=True
    )

# ================= START =================
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("START COMMAND RECEIVED")

    await update.message.reply_text(
        "🔥 Welcome to WatchLog Bot\n\nClick Register to begin.",
        reply_markup=main_menu()
    )

# ================= BUTTON HANDLER =================
async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id

    # Register flow
    if user_id in awaiting_name:
        cursor.execute("INSERT OR REPLACE INTO users (user_id, name) VALUES (?, ?)", (user_id, text))
        conn.commit()
        awaiting_name.remove(user_id)

        await update.message.reply_text(f"✅ Registered as {text}", reply_markup=main_menu())
        return

    if text == "📝 Register":
        awaiting_name.add(user_id)
        await update.message.reply_text("Enter your name:")
        return

    # Check registration
    cursor.execute("SELECT name FROM users WHERE user_id=?", (user_id,))
    if not cursor.fetchone():
        await update.message.reply_text("Please register first.")
        return

    # Start prayer
    if text == "🔥 Mount Pressure":
        if not is_within_time_window():
            await update.message.reply_text("Bot only works 8:40PM - 11:20PM")
            return

        active_sessions[user_id] = now()
        await update.message.reply_text("🔥 Prayer Started")
        return

    # End prayer
    if text == "🛑 End Prayer":
        if user_id not in active_sessions:
            await update.message.reply_text("No active session.")
            return

        start = active_sessions.pop(user_id)
        duration = int((now() - start).total_seconds())

        if duration >= 7200:
            cursor.execute(
                "INSERT INTO sessions VALUES (NULL, ?, ?, ?, ?, ?)",
                (user_id, start.strftime('%H:%M:%S'), now().strftime('%H:%M:%S'), duration, today())
            )
            conn.commit()

            await update.message.reply_text(f"Saved: {format_duration(duration)}")
        else:
            await update.message.reply_text("Must be 2 hours minimum.")

    # Prayer drive
    if text == "📂 Prayer Drive":
        kb = [[InlineKeyboardButton("Open Drive", url=PRAYER_DRIVE_LINK)]]
        await update.message.reply_text("Open resources:", reply_markup=InlineKeyboardMarkup(kb))

# ================= MAIN =================
def main():
    if not TOKEN:
        raise ValueError("BOT_TOKEN not set")

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))

    print("BOT RUNNING...")
    app.run_polling()

if __name__ == "__main__":
    main()
