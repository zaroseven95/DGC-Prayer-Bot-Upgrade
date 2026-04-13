import sqlite3
import os
from datetime import datetime, timedelta, timezone
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ================= CONFIG =================
TOKEN = "8370065008:AAHJh1uD5fipfEidv5G1cho8WWbrHr8tVQY"
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

# ================= MEMORY =================
active_sessions = {}
awaiting_name = set()

# ================= HELPERS =================

def now():
    # Adjusted to UTC+1 (Nigeria/London Standard)
    return datetime.now(timezone.utc) + timedelta(hours=1)

def is_within_time_window():
    """Checks if current time is between 20:40 (8:40 PM) and 23:20 (11:20 PM)"""
    current_time = now().time()
    start = datetime.strptime("20:40", "%H:%M").time()
    end = datetime.strptime("23:20", "%H:%M").time()
    return start <= current_time <= end

def format_duration(seconds):
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h}h {m}m {s}s"

# ================= AUTOMATION (DAILY REPORT) =================

async def send_daily_report_and_reset(bot):
    """Sends the daily report to admin and clears records for the next day"""
    today_str = now().strftime('%Y-%m-%d')
    
    cursor.execute("""
        SELECT u.name, s.start_time, s.end_time, s.duration_seconds 
        FROM sessions s 
        JOIN users u ON s.user_id = u.user_id
    """)
    records = cursor.fetchall()

    report = f"📋 *DAILY BATTLE REPORT* ({today_str})\n\n"
    if not records:
        report += "No sessions were successfully saved today."
    else:
        for r in records:
            report += (f"👤 *Soldier:* {r[0]}\n"
                       f"🛫 *Started:* {r[1]}\n"
                       f"🛬 *Ended:* {r[2]}\n"
                       f"⏳ *Duration:* {format_duration(r[3])}\n\n")

    try:
        await bot.send_message(chat_id=ADMIN_ID, text=report, parse_mode="Markdown")
        # RESET logic: Clear sessions for the new day
        cursor.execute("DELETE FROM sessions")
        conn.commit()
        print(f"✅ Daily report sent and reset at {now()}")
    except Exception as e:
        print(f"❌ Error in daily report task: {e}")

# ================= HANDLERS =================

def main_menu():
    kb = [
        ["🔥 Mount Pressure", "🛑 End Prayer"],
        ["📝 Register", "📂 Prayer Drive"]
    ]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    
    # Registration Flow
    if user_id in awaiting_name:
        cursor.execute("INSERT INTO users (user_id, name) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET name=excluded.name", (user_id, text))
        conn.commit()
        awaiting_name.remove(user_id)
        await update.message.reply_text(f"✅ Soldier {text}, your profile is consecrated for battle!", reply_markup=main_menu())
        return

    # Check registration status
    cursor.execute("SELECT name FROM users WHERE user_id=?", (user_id,))
    user_data = cursor.fetchone()

    if text == "📝 Register":
        awaiting_name.add(user_id)
        await update.message.reply_text(
            "📝 Enter your name:\n\n"
            "_\"For the weapons of our warfare are not carnal, but mighty through God to the pulling down of strong holds.\"\n2 Corinthians 10:4_",
            parse_mode="Markdown"
        )
        return

    if not user_data:
        await update.message.reply_text("❌ Soldier, you must register before you can engage in the battlefield.")
        return

    # Main Command Logic
    if text == "🔥 Mount Pressure":
        if not is_within_time_window():
            await update.message.reply_text(
                "🚫 *Battlefield Closed.*\n\nThe bot is only active for prayer records between *8:40 PM and 11:20 PM* daily.", 
                parse_mode="Markdown"
            )
            return
        
        active_sessions[user_id] = now()
        charge = (
            "🔥 *Dear Soldier of Christ,*\n\n"
            "Kindly unmute your mic and engage. This is a moment of spiritual alignment—your voice is not ordinary; it carries fire.\n\n"
            "The battlefield is active, and your sound is needed. Do not be a spectator—release your prayers, release your fire.\n\n"
            "🔥 *Engage now!*"
        )
        await update.message.reply_text(charge, parse_mode="Markdown")

    elif text == "🛑 End Prayer":
        if user_id in active_sessions:
            start_dt = active_sessions.pop(user_id)
            end_dt = now()
            duration = int((end_dt - start_dt).total_seconds())

            # 2 Hour Standard (7200 seconds)
            if duration >= 7200:
                cursor.execute("INSERT INTO sessions (user_id, start_time, end_time, duration_seconds) VALUES (?, ?, ?, ?)", 
                               (user_id, start_dt.strftime('%H:%M:%S'), end_dt.strftime('%H:%M:%S'), duration))
                conn.commit()
                await update.message.reply_text(
                    f"✅ *Session Successfully Logged!*\n"
                    f"🛫 Start: {start_dt.strftime('%H:%M:%S')}\n"
                    f"🛬 End: {end_dt.strftime('%H:%M:%S')}\n"
                    f"⏳ Duration: {format_duration(duration)}", 
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text(
                    "⚠️ *Soldier, the standard is 2 hours minimum.*\n"
                    "Because you have stopped early, this session will not be recorded in the daily report. Keep pushing!", 
                    parse_mode="Markdown"
                )
        else:
            await update.message.reply_text("❌ No active session found. Click 'Mount Pressure' to start.")

    elif text == "📂 Prayer Drive":
        kb = [[InlineKeyboardButton("Open Prayer Drive 📂", url=PRAYER_DRIVE_LINK)]]
        await update.message.reply_text("Tap below to access battlefield manuals:", reply_markup=InlineKeyboardMarkup(kb))

# ================= START COMMAND =================

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    scripture = (
        "🔥 *Jeremiah 51:20-23*\n\n"
        "“You are My battle-ax and weapons of war:\n"
        "For with you I will break the nation in pieces;\n"
        "With you I will destroy kingdoms;\""
    )
    await update.message.reply_text(scripture, reply_markup=main_menu(), parse_mode="Markdown")

# ================= EXECUTION =================

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    
    # Setup Automation: Reports at 11:30 PM
    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_daily_report_and_reset, 'cron', hour=23, minute=30, args=(app.bot,))
    scheduler.start()

    # Handlers
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))
    
    print("🔥 WATCHLOG BOT IS ONLINE...")
    # drop_pending_updates ignores messages sent while bot was offline
    app.run_polling(drop_pending_updates=True)
