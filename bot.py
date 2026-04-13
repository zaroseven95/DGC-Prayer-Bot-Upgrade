import sqlite3
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ================= CONFIG =================
TOKEN = "8370065008:AAHJh1uD5fipfEidv5G1cho8WWbrHr8tVQY"
ADMIN_ID = 6021933432 
PRAYER_DRIVE_LINK = "https://t.me/c/3754852727/885"

# Logging for easier debugging on Railway
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# ================= DATABASE & PERSISTENCE =================
conn = sqlite3.connect("prayer.db", check_same_thread=False)
cursor = conn.cursor()

def db_setup():
    cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, name TEXT)")
    # New: active_sessions table so restarts don't wipe current prayers
    cursor.execute("CREATE TABLE IF NOT EXISTS active_sessions (user_id INTEGER PRIMARY KEY, start_time TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, start_time TEXT, end_time TEXT, duration_seconds INTEGER)")
    conn.commit()

db_setup()
awaiting_name = set()

# ================= CORE HELPERS =================

def now():
    return datetime.now(timezone.utc) + timedelta(hours=1)

def is_within_time_window():
    current_time = now().time()
    start = datetime.strptime("20:40", "%H:%M").time()
    end = datetime.strptime("23:20", "%H:%M").time()
    return start <= current_time <= end

def format_duration(seconds):
    h, m, s = seconds // 3600, (seconds % 3600) // 60, seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"

def get_progress_bar(seconds):
    target = 7200 # 2 hours
    percent = min(int((seconds / target) * 10), 10)
    bar = "🔥" * percent + "🌑" * (10 - percent)
    return f"[{bar}] {int((seconds/target)*100)}%"

# ================= AUTOMATION =================

async def send_daily_report_and_reset(bot):
    cursor.execute("SELECT u.name, s.start_time, s.end_time, s.duration_seconds FROM sessions s JOIN users u ON s.user_id = u.user_id")
    records = cursor.fetchall()
    
    report = f"📋 *FINAL BATTLE REPORT* — {now().strftime('%d %b %Y')}\n"
    report += "━━━━━━━━━━━━━━━━━━\n\n"
    
    if not records:
        report += "No records found for this period."
    else:
        for r in records:
            report += f"👤 *{r[0]}*\n🛫 {r[1]} → 🛬 {r[2]}\n⏳ Total: `{format_duration(r[3])}`\n\n"
    
    try:
        await bot.send_message(chat_id=ADMIN_ID, text=report, parse_mode="Markdown")
        cursor.execute("DELETE FROM sessions")
        cursor.execute("DELETE FROM active_sessions") # Clear any hanging timers
        conn.commit()
    except Exception as e:
        logging.error(f"Report Error: {e}")

# ================= HANDLERS =================

def main_menu(user_id):
    kb = [
        ["🔥 Mount Pressure", "🛑 End Prayer"],
        ["📍 Status", "🏆 Leaderboard"],
        ["📊 My Time", "📘 Guide"],
        ["📝 Register", "📂 Prayer Drive"]
    ]
    if user_id == ADMIN_ID: kb.append(["⚙️ Admin Report"])
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    if query.data == "confirm_exit":
        cursor.execute("DELETE FROM active_sessions WHERE user_id=?", (user_id,))
        conn.commit()
        await query.edit_message_text("❌ *Session Aborted.* The time has been discarded.", parse_mode="Markdown")
    elif query.data == "cancel_exit":
        await query.edit_message_text("🔥 *Standard Maintained.* Push through, soldier!", parse_mode="Markdown")

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text, user_id = update.message.text, update.effective_user.id
    
    if user_id in awaiting_name:
        cursor.execute("INSERT INTO users (user_id, name) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET name=excluded.name", (user_id, text))
        conn.commit()
        awaiting_name.remove(user_id)
        return await update.message.reply_text(f"✅ *Welcome, {text}!*\nYou are now authorized for WatchLog operations.", reply_markup=main_menu(user_id), parse_mode="Markdown")

    cursor.execute("SELECT name FROM users WHERE user_id=?", (user_id,))
    user_data = cursor.fetchone()
    if not user_data and text != "📝 Register":
        return await update.message.reply_text("👋 *Welcome!* Please use the **📝 Register** button to begin.", parse_mode="Markdown")

    # --- ACTIONS ---
    if text == "📝 Register":
        awaiting_name.add(user_id)
        return await update.message.reply_text("📝 *Kingdom Registration*\n\nPlease enter your full name below:\n\n_\"You are My battle-ax...\"_", parse_mode="Markdown")

    elif text == "🔥 Mount Pressure":
        if not is_within_time_window():
            return await update.message.reply_text("🚫 *Battlefield Closed.*\nAccess remains restricted until *20:40 (8:40 PM)*.", parse_mode="Markdown")
        
        cursor.execute("SELECT start_time FROM active_sessions WHERE user_id=?", (user_id,))
        if cursor.fetchone():
            return await update.message.reply_text("🔥 You are already in active prayer!")
            
        start_val = now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute("INSERT INTO active_sessions (user_id, start_time) VALUES (?, ?)", (user_id, start_val))
        conn.commit()
        return await update.message.reply_text("🔥 *BATTLE ENGAGED.*\nUnmute your mic and release the sound of heaven.", parse_mode="Markdown")

    elif text == "🛑 End Prayer":
        cursor.execute("SELECT start_time FROM active_sessions WHERE user_id=?", (user_id,))
        session = cursor.fetchone()
        if not session:
            return await update.message.reply_text("❌ You do not have an active session.")
        
        start_dt = datetime.strptime(session[0], '%Y-%m-%d %H:%M:%S')
        duration = int((now().replace(tzinfo=None) - start_dt).total_seconds())

        if duration >= 7200:
            cursor.execute("DELETE FROM active_sessions WHERE user_id=?", (user_id,))
            cursor.execute("INSERT INTO sessions (user_id, start_time, end_time, duration_seconds) VALUES (?, ?, ?, ?)", 
                           (user_id, start_dt.strftime('%H:%M:%S'), now().strftime('%H:%M:%S'), duration))
            conn.commit()
            return await update.message.reply_text(f"✅ *VICTORY.*\nYour 2-hour standard has been met and recorded.\n⏳ Total: `{format_duration(duration)}`", parse_mode="Markdown")
        else:
            kb = [[InlineKeyboardButton("✅ Continue", callback_data="cancel_exit")], [InlineKeyboardButton("❌ Discard Session", callback_data="confirm_exit")]]
            return await update.message.reply_text(
                f"⚠️ *STANDARD NOT MET*\n\nYou have only reached `{format_duration(duration)}`.\nDo you wish to continue or discard the time?",
                reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown"
            )

    elif text == "📍 Status":
        cursor.execute("SELECT start_time FROM active_sessions WHERE user_id=?", (user_id,))
        session = cursor.fetchone()
        if session:
            start_dt = datetime.strptime(session[0], '%Y-%m-%d %H:%M:%S')
            elapsed = int((now().replace(tzinfo=None) - start_dt).total_seconds())
            return await update.message.reply_text(f"📍 *LIVE STATUS: PRAYING*\n━━━━━━━━━━━━━━\n⏳ Elapsed: `{format_duration(elapsed)}`\n📊 {get_progress_bar(elapsed)}\n\n_Don't stop until the rain falls!_", parse_mode="Markdown")
        return await update.message.reply_text("📍 *STATUS: IDLE*\nWaiting for the next watch...", parse_mode="Markdown")

    elif text == "🏆 Leaderboard":
        cursor.execute("SELECT u.name, SUM(s.duration_seconds) as t FROM sessions s JOIN users u ON u.user_id = s.user_id GROUP BY u.user_id ORDER BY t DESC LIMIT 5")
        rows = cursor.fetchall()
        lb = "🏆 *TOP INTERCESSORS (TODAY)*\n━━━━━━━━━━━━━━\n"
        if not rows: lb += "No fire recorded yet today."
        for i, r in enumerate(rows): lb += f"{i+1}. *{r[0]}* — `{format_duration(r[1])}`\n"
        return await update.message.reply_text(lb, parse_mode="Markdown")

    elif text == "📊 My Time":
        cursor.execute("SELECT SUM(duration_seconds) FROM sessions WHERE user_id=?", (user_id,))
        total = cursor.fetchone()[0] or 0
        return await update.message.reply_text(f"📊 *YOUR PROGRESS*\nTotal Record for Today: `{format_duration(total)}`", parse_mode="Markdown")

    elif text == "📘 Guide":
        guide = (
            "📘 *WATCHLOG OPERATIONS GUIDE*\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "🔥 *Mount Pressure*\nStart your watch. Active only from *20:40 to 23:20* daily.\n\n"
            "🛑 *End Prayer*\nStop your watch. Requires *2 Hours* minimum to record.\n\n"
            "📍 *Status*\nView live progress bar and current prayer duration.\n\n"
            "🏆 *Leaderboard*\nSee the top 5 ranking intercessors for the current day.\n\n"
            "📂 *Prayer Drive*\nDirect access to spiritual weapons and manuals.\n\n"
            "📝 *Register*\nUpdate your identity for the Kingdom logs.\n"
            "━━━━━━━━━━━━━━━━━━"
        )
        return await update.message.reply_text(guide, parse_mode="Markdown")

    elif text == "📂 Prayer Drive":
        return await update.message.reply_text("📂 *Accessing Resources...*", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Open Drive", url=PRAYER_DRIVE_LINK)]]), parse_mode="Markdown")

    elif text == "⚙️ Admin Report" and user_id == ADMIN_ID:
        report = f"⚙️ *REAL-TIME DATABASE LOG*\n━━━━━━━━━━━━━━\n"
        cursor.execute("SELECT u.name, SUM(s.duration_seconds) FROM sessions s JOIN users u ON u.user_id = s.user_id GROUP BY u.user_id")
        for r in cursor.fetchall(): report += f"• {r[0]}: `{format_duration(r[1])}`\n"
        return await update.message.reply_text(report if report != "" else "No records.", parse_mode="Markdown")

async def main():
    app = ApplicationBuilder().token(TOKEN).build()
    
    # Simple start command
    app.add_handler(CommandHandler("start", lambda u, c: u.message.reply_text("🔥 *WATCHLOG COMMAND*\n\n_“You are My battle-ax and weapons of war...”_", reply_markup=main_menu(u.effective_user.id), parse_mode="Markdown")))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    # Scheduler
    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_daily_report_and_reset, 'cron', hour=23, minute=30, args=(app.bot,))
    scheduler.start()

    print("💎 WATCHLOG ULTRA IS ONLINE...")
    async with app:
        await app.initialize()
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        while True: await asyncio.sleep(1)

if __name__ == "__main__":
    try: asyncio.run(main())
    except: pass
