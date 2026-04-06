import sqlite3
import os
from datetime import datetime, timedelta, timezone
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# ================= CONFIG =================
# ⚠️ REPLACE WITH A NEW TOKEN FROM BOTFATHER
TOKEN = "8370065008:AAEB6zCbHLOakKb16bt-NKqc5P9FSaQOtgc" 
ADMIN_ID = 6021933432

# The link to the specific PDF message in your group
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
            ["👥 Live Room", "📂 Prayer Drive"]
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
    if duration < 7200:
        await update.message.reply_text(
            f"⏱ Session: {format_duration(duration)}\n\n"
            "⚠️ Soldier, you haven't hit the 2-hour mark! Get back to the battlefield!\n\n"
            "Your time is preserved. Use ▶️ Continue or 🔥 Mount Pressure to keep going."
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

    report = "📋 RECENT PRAYER RECORDS\n\n"
    for name, start, end, duration in rows:
        date_str = start.split(" ")[0]
        report += (
            f"👤 {name}\n"
            f"📅 Date: {date_str}\n"
            f"🕒 Start: {start.split(' ')[1]}\n"
            f"🕓 End: {end.split(' ')[1]}\n"
            f"⏱ Total: {format_duration(duration)}\n"
            f"--- --- --- ---\n"
        )
    
    if len(report) > 4000: report = report[:3900] + "\n... (Truncated)"
    await update.message.reply_text(report)

# ================= HANDLERS =================

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    registered = is_registered(user_id)

    if user_id in awaiting_name:
        cursor.execute("INSERT INTO users (user_id, name) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET name=excluded.name", (user_id, text))
        conn.commit()
        awaiting_name.remove(user_id)
        await update.message.reply_text(f"✅ Registered as {text}", reply_markup=main_menu(user_id))
        return

    if text == "📝 Register":
        awaiting_name.add(user_id)
        await update.message.reply_text("📝 Enter your name:")
    
    elif text == "📂 Prayer Drive":
        keyboard = [[InlineKeyboardButton("Open Prayer Drive 📂", url=PRAYER_DRIVE_LINK)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        # Direct response with just the button link
        await update.message.reply_text(
            "Tap below to open the drive:",
            reply_markup=reply_markup
        )

    elif text == "📘 Guide":
        # Removed ** markers, using Markdown bold
        await update.message.reply_text(
            "📘 *HOW TO USE*\n\n"
            "*🔥 Mount Pressure* -> Start your prayer session.\n"
            "*🛑 End Prayer* -> Save your record.\n"
            "*📂 Prayer Drive* -> Access the manual.\n\n"
            "⚠️ *Note:* 2 hours minimum required to save a session.",
            parse_mode="Markdown"
        )

    elif text == "🏆 Leaderboard":
        cursor.execute("SELECT u.name, SUM(s.duration_seconds) as t FROM sessions s JOIN users u ON u.user_id = s.user_id GROUP BY u.user_id ORDER BY t DESC LIMIT 10")
        rows = cursor.fetchall()
        leader_text = "🏆 LEADERBOARD\n\n" + "\n".join([f"{i}. {r[0]} — {format_duration(r[1])}" for i, r in enumerate(rows, 1)])
        await update.message.reply_text(leader_text if rows else "No data.")

    elif text == "👥 Live Room":
        if not active_sessions:
            await update.message.reply_text("😴 No one is currently praying.")
            return
        live_text = "🔥 LIVE PRAYER ROOM\n\n"
        for uid, start_t in active_sessions.items():
            cursor.execute("SELECT name FROM users WHERE user_id=?", (uid,))
            res = cursor.fetchone()
            name = res[0] if res else "Unknown"
            live_text += f"👤 {name}\n⏱ {format_duration(int((now()-start_t).total_seconds()))}\n\n"
        await update.message.reply_text(live_text)

    elif text == "📊 My Time":
        cursor.execute("SELECT SUM(duration_seconds) FROM sessions WHERE user_id=?", (user_id,))
        total = cursor.fetchone()[0] or 0
        await update.message.reply_text(f"📊 Total Time: {format_duration(total)}")

    elif text == "📍 Status":
        if user_id in active_sessions:
            d, s = int((now() - active_sessions[user_id]).total_seconds()), "Praying 🔥"
        elif user_id in paused_sessions:
            d, s = paused_sessions[user_id], "Preserved Time ⏳"
        else:
            await update.message.reply_text("❌ Not praying.")
            return
        await update.message.reply_text(f"Status: {s}\n⏱ {format_duration(d)}")

    elif text == "⚙️ Admin Report":
        await admin_report(update, context)

    elif not registered:
        await update.message.reply_text("❌ Register first", reply_markup=main_menu(user_id))

    elif text in ["🔥 Mount Pressure", "▶️ Continue"]:
        await pray(update, context)

    elif text == "🛑 End Prayer":
        duration = 0
        current_source = None
        if user_id in paused_sessions:
            duration = paused_sessions[user_id]
            current_source = "paused"
        elif user_id in active_sessions:
            start_t = active_sessions[user_id]
            duration = int((now() - start_t).total_seconds())
            current_source = "active"

        if duration > 0:
            success = await end_prayer_logic(update, user_id, duration)
            if success:
                active_sessions.pop(user_id, None)
                paused_sessions.pop(user_id, None)
            else:
                if current_source == "active":
                    start_t = active_sessions.pop(user_id)
                    paused_sessions[user_id] = int((now() - start_t).total_seconds())
        else:
            await update.message.reply_text("❌ No active session.")

# ================= START =================

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text("🔥 Welcome to Prayer WatchLog", reply_markup=main_menu(user_id))

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start_cmd))
app.add_handler(CommandHandler("admin_report", admin_report)) 
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))

print("🔥 BOT RUNNING...")
app.run_polling()
