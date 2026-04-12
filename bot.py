import sqlite3
from datetime import datetime, timedelta, timezone, time as dtime
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

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
    return datetime.now(timezone.utc) + timedelta(hours=1)

def is_registered(user_id):
    cursor.execute("SELECT name FROM users WHERE user_id=?", (user_id,))
    return cursor.fetchone()

def format_duration(seconds):
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h}h {m}m {s}s"

def is_active_time():
    current = now().time()
    return dtime(20, 50) <= current <= dtime(23, 10)

# ================= DAILY RESET =================

async def reset_daily_sessions(context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("DELETE FROM sessions")
    conn.commit()
    print("🔄 Daily session reset completed")

# ================= MENU =================

def main_menu(user_id):
    registered = is_registered(user_id)
    if not registered:
        return ReplyKeyboardMarkup([["📝 Register"]], resize_keyboard=True)
    
    keyboard = [
        ["🔥 Mount Pressure"],
        ["▶️ Continue", "🛑 End Prayer"],
        ["📊 My Time", "🏆 Leaderboard"],
        ["📍 Status", "📘 Guide"],
        ["👥 Live Room", "📂 Prayer Drive"]
    ]
    if user_id == ADMIN_ID:
        keyboard.append(["⚙️ Admin Report"])

    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ================= CALLBACK =================

async def handle_exit_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    if query.data == "exit_discard":
        active_sessions.pop(user_id, None)
        paused_sessions.pop(user_id, None)
        await query.edit_message_text("❌ Session discarded.")

    elif query.data == "keep_praying":
        if user_id in paused_sessions:
            elapsed = paused_sessions.pop(user_id)
            active_sessions[user_id] = now() - timedelta(seconds=elapsed)
            await query.edit_message_text("🔥 Prayer continues!")
        else:
            await query.edit_message_text("⚠️ No session found.")

# ================= HANDLERS =================

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id

    if not is_active_time():
        await update.message.reply_text("⏰ Active only 8:50PM – 11:10PM.")
        return

    registered = is_registered(user_id)

    if user_id in awaiting_name:
        cursor.execute("INSERT INTO users (user_id, name) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET name=excluded.name", (user_id, text))
        conn.commit()
        awaiting_name.remove(user_id)
        await update.message.reply_text(f"✅ Registered as {text}", reply_markup=main_menu(user_id))
        return

    if text == "📝 Register":
        awaiting_name.add(user_id)
        await update.message.reply_text(
            "📝 Enter your name:\n\n"
            "_\"For the weapons of our warfare are not carnal...\"_\n2 Corinthians 10:4",
            parse_mode="Markdown"
        )

    elif text == "📂 Prayer Drive":
        keyboard = [[InlineKeyboardButton("Open Prayer Drive 📂", url=PRAYER_DRIVE_LINK)]]
        await update.message.reply_text("Tap below:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif text == "🔥 Mount Pressure":
        if not registered:
            await update.message.reply_text("❌ Register first")
        else:
            active_sessions[user_id] = now()
            context.user_data["start_time"] = now()
            await update.message.reply_text("🔥 You are mounting pressure")

    elif text == "🛑 End Prayer":
        duration = 0
        start_time_val = context.user_data.get("start_time", now())

        if user_id in active_sessions:
            start_t = active_sessions.pop(user_id)
            duration = int((now() - start_t).total_seconds())

        if duration > 0:
            end_time = now()
            cursor.execute("INSERT INTO sessions VALUES (NULL, ?, ?, ?, ?)",
                           (user_id,
                            start_time_val.strftime('%Y-%m-%d %H:%M:%S'),
                            end_time.strftime('%Y-%m-%d %H:%M:%S'),
                            duration))
            conn.commit()

            status = "✅ PASS" if duration >= 7200 else "❌ FAIL"
            await update.message.reply_text(f"{status}\n⏱ {format_duration(duration)}")

        else:
            await update.message.reply_text("❌ No active session.")

    elif text == "📊 My Time":
        cursor.execute("SELECT SUM(duration_seconds) FROM sessions WHERE user_id=?", (user_id,))
        total = cursor.fetchone()[0] or 0
        await update.message.reply_text(f"📊 Today: {format_duration(total)}")

# ================= REPORT =================

async def send_daily_report(context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("""
    SELECT u.name, s.start_time, s.end_time, s.duration_seconds
    FROM sessions s
    JOIN users u ON u.user_id = s.user_id
    """)
    rows = cursor.fetchall()

    if not rows:
        report = "📋 No activity today."
    else:
        report = "📋 DAILY REPORT\n\n"
        for r in rows:
            name, start, end, duration = r
            status = "✅ PASS" if duration >= 7200 else "❌ FAIL"
            report += f"{name}\n{start} → {end}\n{format_duration(duration)}\n{status}\n\n"

    await context.bot.send_message(chat_id=ADMIN_ID, text=report)

# ================= START =================

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔥 Blessed be the Lord that teacheth my hands to war. Psalm 144:1",
        reply_markup=main_menu(update.effective_user.id)
    )

app = ApplicationBuilder().token(TOKEN).build()

# ⏰ Schedule
app.job_queue.run_daily(send_daily_report, time=dtime(23, 15))
app.job_queue.run_daily(reset_daily_sessions, time=dtime(0, 0))  # midnight reset

app.add_handler(CommandHandler("start", start_cmd))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))
app.add_handler(CallbackQueryHandler(handle_exit_choice))

print("🔥 BOT RUNNING...")
app.run_polling()
