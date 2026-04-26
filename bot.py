import sqlite3
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from datetime import datetime
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_FILE = "meal_votes.db"

NAMES = ["hx", "chole", "mel"]
VOTES = {
    "good": "👍",
    "ok": "👌",
    "bad": "👎",
}


def run_web_server():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Bot is running!")

    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), Handler)
    server.serve_forever()


def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS rounds (
            chat_id INTEGER PRIMARY KEY,
            round_started_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            round_started_at TEXT,
            voter_id INTEGER,
            voter_name TEXT,
            target_name TEXT,
            vote TEXT,
            created_at TEXT
        )
    """)

    conn.commit()
    conn.close()


def save_vote(chat_id, user, target_name, vote):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    cur.execute("SELECT round_started_at FROM rounds WHERE chat_id = ?", (chat_id,))
    row = cur.fetchone()

    if not row:
        conn.close()
        return False

    round_started_at = row[0]

    cur.execute("""
        INSERT INTO votes (
            chat_id, round_started_at, voter_id, voter_name,
            target_name, vote, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        chat_id,
        round_started_at,
        user.id,
        user.full_name,
        target_name,
        vote,
        datetime.now().isoformat(timespec="seconds")
    ))

    conn.commit()
    conn.close()
    return True


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Meal Rating Bot 🍱\n\n"
        "/initiate - start a new weekly round\n"
        "/rate - rate hx / chole / mel\n"
        "/tally - show results"
    )


async def initiate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    now = datetime.now().isoformat(timespec="seconds")

    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO rounds (chat_id, round_started_at)
        VALUES (?, ?)
        ON CONFLICT(chat_id)
        DO UPDATE SET round_started_at = excluded.round_started_at
    """, (chat_id, now))

    conn.commit()
    conn.close()

    await update.message.reply_text("New weekly round started! 🍱")


async def rate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton(name, callback_data=f"name_{name}")]
        for name in NAMES
    ]

    await update.message.reply_text(
        "Who are you rating?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    selected_name = query.data.replace("name_", "")
    context.user_data["target_name"] = selected_name

    keyboard = [
        [InlineKeyboardButton(f"{emoji} {vote}", callback_data=f"vote_{vote}")]
        for vote, emoji in VOTES.items()
    ]

    await query.edit_message_text(
        text=f"Selected: {selected_name}\nChoose rating:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_vote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    vote = query.data.replace("vote_", "")
    target_name = context.user_data.get("target_name")

    chat_id = query.message.chat_id
    user = query.from_user

    if not target_name:
        await query.edit_message_text("Please use /rate again.")
        return

    success = save_vote(chat_id, user, target_name, vote)

    if not success:
        await query.edit_message_text("No active round. Use /initiate first.")
        return

    emoji = VOTES[vote]

    await query.edit_message_text(
        text=f"{target_name}: {emoji}"
    )


async def tally(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    cur.execute("SELECT round_started_at FROM rounds WHERE chat_id = ?", (chat_id,))
    row = cur.fetchone()

    if not row:
        conn.close()
        await update.message.reply_text("No active round. Use /initiate first.")
        return

    round_started_at = row[0]

    cur.execute("""
        SELECT target_name, vote, COUNT(*)
        FROM votes
        WHERE chat_id = ? AND round_started_at = ?
        GROUP BY target_name, vote
        ORDER BY target_name
    """, (chat_id, round_started_at))

    rows = cur.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("No votes yet.")
        return

    results = {}

    for name, vote, count in rows:
        if name not in results:
            results[name] = {"good": 0, "ok": 0, "bad": 0}
        results[name][vote] = count

    message = "🍱 Weekly Tally\n\n"

    for name, counts in results.items():
        message += (
            f"{name}\n"
            f"👍 {counts['good']}  👌 {counts['ok']}  👎 {counts['bad']}\n\n"
        )

    await update.message.reply_text(message)


def main():
    init_db()
    threading.Thread(target=run_web_server, daemon=True).start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("initiate", initiate))
    app.add_handler(CommandHandler("rate", rate))
    app.add_handler(CommandHandler("tally", tally))

    app.add_handler(CallbackQueryHandler(handle_name, pattern="^name_"))
    app.add_handler(CallbackQueryHandler(handle_vote, pattern="^vote_"))

    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
