import sqlite3
import os
from datetime import datetime, timedelta, timezone
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# ================= CONFIG =================
TOKEN = "YOUR_NEW_TOKEN_HERE" 
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

# ================= CALLBACK LOGIC (INLINE BUTTONS) =================

async def handle_exit_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the user clicking 'Exit & Discard' or 'Keep Praying'"""
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    if query.data == "exit_discard":
        active_sessions.pop(user_id, None)
        paused_sessions.pop(user_id, None)
        await query.edit_message_text("❌ Session discarded. You have exited the battlefield.")
    
    elif query.data == "keep_praying":
        # Check if they have a saved duration in paused_sessions
        if user_id in paused_sessions:
            elapsed_seconds = paused_sessions.pop(user_id)
            # Re-calculate the start time as (now - previously elapsed time)
            active_sessions[user_id] = now() - timedelta(seconds=elapsed_seconds)
            await query.edit_message_text("🔥 Standard maintained! Prayer is continuing automatically. Keep mounting pressure!")
        else:
            await query.edit_message_text("⚠️ No session found to resume.")

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
        await update.message.reply_text("Tap below to open the drive:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif text == "📘 Guide":
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

    elif text in ["🔥 Mount Pressure", "▶️ Continue"]:
        if not registered:
            await update.message.reply_text("❌ Register first")
        else:
            # Reusing the prayer logic
            if user_id in paused_sessions:
                p_time = paused_sessions.pop(user_id)
                active_sessions[user_id] = now() - timedelta(seconds=p_time)
                await update.message.reply_text("▶️ Resuming... back to the battlefield!")
            elif user_id in active_sessions:
                await update.message.reply_text("⚠️ Already mounting pressure 🔥")
            else:
                active_sessions[user_id] = now()
                await update.message.reply_text("🔥 You are mounting pressure")

    elif text == "🛑 End Prayer":
        duration = 0
        if user_id in active_sessions:
            # If they hit end while active, we calculate current duration and move to paused temp
            start_t = active_sessions.pop(user_id)
            duration = int((now() - start_t).total_seconds())
            paused_sessions[user_id] = duration 
        elif user_id in paused_sessions:
            duration = paused_sessions[user_id]

        if duration >= 7200: # 2 Hours
            end_time = now()
            start_time_val = end_time - timedelta(seconds=duration)
            cursor.execute("INSERT INTO sessions (user_id, start_time, end_time, duration_seconds) VALUES (?, ?, ?, ?)", 
                           (user_id, start_time_val.strftime('%Y-%m-%d %H:%M:%S'), end_time.strftime('%Y-%m-%d %H:%M:%S'), duration))
            conn.commit()
            paused_sessions.pop(user_id, None)
            await update.message.reply_text(f"✅ Completed: {format_duration(duration)}\n🔥 High Conversion Rate! Welldone!")
        elif duration > 0:
            keyboard = [
                [InlineKeyboardButton("✅ Keep Praying", callback_data="keep_praying")],
                [InlineKeyboardButton("❌ Exit & Discard", callback_data="exit_discard")]
            ]
            await update.message.reply_text(
                f"⏱ Session: {format_duration(duration)}\n\n"
                "⚠️ Soldier, you haven't hit the 2-hour mark! If you exit now, this time will be lost. What do you want to do?",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await update.message.reply_text("❌ No active session.")

    elif text == "⚙️ Admin Report" and user_id == ADMIN_ID:
        cursor.execute("SELECT users.name, sessions.duration_seconds FROM sessions JOIN users ON users.user_id = sessions.user_id ORDER BY sessions.id DESC LIMIT 10")
        rows = cursor.fetchall()
        report = "📋 RECENT RECORDS\n\n" + "\n".join([f"👤 {r[0]} - {format_duration(r[1])}" for r in rows])
        await update.message.reply_text(report if rows else "No records.")

# ================= START =================

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔥 Blessed be the Lord that teacheth my hands to war.Psalm 144:1", reply_markup=main_menu(update.effective_user.id))

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start_cmd))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))
app.add_handler(CallbackQueryHandler(handle_exit_choice))

print("🔥 BOT RUNNING (Auto-Continue Enabled)...")
app.run_polling()
