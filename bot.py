import sqlite3
import os
from datetime import datetime, timedelta, timezone
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ================= CONFIG =================
TOKEN = "8370065008:AAEPZ7_FO2sDvpz99p3pH1XjVv-cd54H7zc"
ADMIN_ID = 6021933432
PRAYER_DRIVE_LINK = "https://t.me/c/3754852727/885"

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

active_sessions = {}
paused_sessions = {}
awaiting_name = set()

# ================= HELPERS =================

def now():
    # Adjusted to your local time (UTC+1)
    return datetime.now(timezone.utc) + timedelta(hours=1)

def is_within_time_window():
    """Checks if current time is between 20:40 and 23:20"""
    current_time = now().time()
    start = datetime.strptime("20:40", "%H:%M").time()
    end = datetime.strptime("23:20", "%H:%M").time()
    return start <= current_time <= end

def format_duration(seconds):
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h}h {m}m {s}s"

# ================= AUTOMATION (SCHEDULER) =================

async def send_daily_report_and_reset(context: ContextTypes.DEFAULT_TYPE):
    """Sends report to admin and clears sessions table for the new day"""
    today_str = now().strftime('%Y-%m-%d')
    
    cursor.execute("""
        SELECT u.name, s.start_time, s.end_time, s.duration_seconds 
        FROM sessions s 
        JOIN users u ON s.user_id = u.user_id
    """)
    records = cursor.fetchall()

    report = f"📋 *DAILY BATTLE REPORT* ({today_str})\n\n"
    if not records:
        report += "No sessions recorded today."
    else:
        for r in records:
            report += (f"👤 *{r[0]}*\n"
                       f"🛫 Start: {r[1]}\n"
                       f"🛬 End: {r[2]}\n"
                       f"⏳ Duration: {format_duration(r[3])}\n\n")

    # Send to Admin
    await context.bot.send_message(chat_id=ADMIN_ID, text=report, parse_mode="Markdown")

    # RESET: Clear sessions for the next day
    cursor.execute("DELETE FROM sessions")
    conn.commit()
    print(f"✅ Daily report sent and records reset at {now()}")

# ================= HANDLERS =================

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    
    # Check for Time Restriction first for prayer actions
    if text in ["🔥 Mount Pressure", "▶️ Continue"]:
        if not is_within_time_window():
            await update.message.reply_text("🚫 *Battlefield Closed.*\n\nThe bot is only active for prayer between *8:40 PM and 11:20 PM* daily.", parse_mode="Markdown")
            return

    # Standard Button Logic
    if user_id in awaiting_name:
        cursor.execute("INSERT INTO users (user_id, name) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET name=excluded.name", (user_id, text))
        conn.commit()
        awaiting_name.remove(user_id)
        await update.message.reply_text(f"✅ Registered as {text}")
        return

    if text == "📝 Register":
        awaiting_name.add(user_id)
        await update.message.reply_text("📝 Enter your name:")

    elif text == "🔥 Mount Pressure":
        active_sessions[user_id] = now()
        await update.message.reply_text("🔥 *Engage now! Your voice carries fire.*", parse_mode="Markdown")

    elif text == "🛑 End Prayer":
        if user_id in active_sessions:
            start_dt = active_sessions.pop(user_id)
            end_dt = now()
            duration = int((end_dt - start_dt).total_seconds())

            if duration >= 7200: # 2 Hour standard
                cursor.execute("INSERT INTO sessions (user_id, start_time, end_time, duration_seconds) VALUES (?, ?, ?, ?)", 
                               (user_id, start_dt.strftime('%H:%M:%S'), end_dt.strftime('%H:%M:%S'), duration))
                conn.commit()
                await update.message.reply_text(f"✅ Session Saved: {format_duration(duration)}")
            else:
                await update.message.reply_text("⚠️ Soldier, 2 hours not reached. Time discarded.")
        else:
            await update.message.reply_text("❌ No active session.")

# ================= START =================

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔥 WatchLog Active. Use buttons to navigate.", 
                                   reply_markup=ReplyKeyboardMarkup([["🔥 Mount Pressure", "🛑 End Prayer"], ["📝 Register"]], resize_keyboard=True))

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    
    # Scheduler Setup
    scheduler = AsyncIOScheduler()
    # Schedule the report and reset for 11:30 PM (just after the session ends)
    scheduler.add_job(send_daily_report_and_reset, 'cron', hour=23, minute=30, args=[app])
    scheduler.start()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))
    
    print("🔥 BOT RUNNING & SCHEDULER ACTIVE...")
    app.run_polling()
