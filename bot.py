import sqlite3
from datetime import datetime, timedelta, timezone
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ================= CONFIG =================
TOKEN = "8370065008:AAGCFCC8IwG7UFhRLXNEHVzGg4ewd4DxUM0"
ADMIN_ID = 6021933432
PRAYER_DRIVE_LINK = "https://t.me/c/3754852727/885"

# ================= DATABASE =================
conn = sqlite3.connect("prayer.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, name TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, start_time TEXT, end_time TEXT, duration_seconds INTEGER)")
conn.commit()

active_sessions = {}
awaiting_name = set()

# ================= HELPERS =================

def now():
    return datetime.now(timezone.utc) + timedelta(hours=1)

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

# ================= AUTOMATION =================

async def send_daily_report_and_reset(bot):
    today_str = now().strftime('%Y-%m-%d')
    cursor.execute("SELECT u.name, s.start_time, s.end_time, s.duration_seconds FROM sessions s JOIN users u ON s.user_id = u.user_id")
    records = cursor.fetchall()

    report = f"📋 *DAILY BATTLE REPORT* ({today_str})\n\n"
    if not records:
        report += "No sessions recorded today."
    else:
        for r in records:
            report += f"👤 *{r[0]}*\n🛫 {r[1]} 🛬 {r[2]}\n⏳ {format_duration(r[3])}\n\n"

    await bot.send_message(chat_id=ADMIN_ID, text=report, parse_mode="Markdown")
    cursor.execute("DELETE FROM sessions")
    conn.commit()
    print("✅ Daily report sent and records reset.")

# ================= HANDLERS =================

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    
    cursor.execute("SELECT name FROM users WHERE user_id=?", (user_id,))
    user_data = cursor.fetchone()

    if user_id in awaiting_name:
        cursor.execute("INSERT INTO users (user_id, name) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET name=excluded.name", (user_id, text))
        conn.commit()
        awaiting_name.remove(user_id)
        await update.message.reply_text(f"✅ Registered as {text}")
        return

    if text == "📝 Register":
        awaiting_name.add(user_id)
        await update.message.reply_text("📝 Enter your name:")
        return

    if not user_data:
        await update.message.reply_text("❌ Please register first!")
        return

    if text == "🔥 Mount Pressure":
        if not is_within_time_window():
            await update.message.reply_text("🚫 Battlefield Closed. Active: 8:40PM - 11:20PM.")
            return
        active_sessions[user_id] = now()
        await update.message.reply_text("🔥 *Engage now! Your voice carries fire.*", parse_mode="Markdown")

    elif text == "🛑 End Prayer":
        if user_id in active_sessions:
            start_dt = active_sessions.pop(user_id)
            end_dt = now()
            duration = int((end_dt - start_dt).total_seconds())

            if duration >= 7200: # 2 Hour check
                cursor.execute("INSERT INTO sessions (user_id, start_time, end_time, duration_seconds) VALUES (?, ?, ?, ?)", 
                               (user_id, start_dt.strftime('%H:%M:%S'), end_dt.strftime('%H:%M:%S'), duration))
                conn.commit()
                await update.message.reply_text(f"✅ Session Saved: {format_duration(duration)}")
            else:
                await update.message.reply_text("⚠️ Soldier, 2 hours not reached. Session discarded.")
        else:
            await update.message.reply_text("❌ No active session.")

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [["🔥 Mount Pressure", "🛑 End Prayer"], ["📝 Register"]]
    await update.message.reply_text("🔥 WatchLog Active.", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    
    # Corrected Scheduler Setup
    scheduler = AsyncIOScheduler()
    # Note: args expects a tuple, so we use (app.bot,)
    scheduler.add_job(send_daily_report_and_reset, 'cron', hour=23, minute=30, args=(app.bot,))
    scheduler.start()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))
    
    print("🔥 BOT RUNNING...")
    app.run_polling()
