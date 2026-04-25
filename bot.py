import sqlite3
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_FILE = "meal_votes.db"


# Initialize database
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


# /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Meal Rating Bot 🍱\n\n"
        "/initiate - start a new weekly round\n"
        "/rate <name> <good|ok|bad>\n"
        "/tally - show results"
    )


# /initiate command
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


# /rate command
async def rate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user

    if len(context.args) < 2:
        await update.message.reply_text(
            "Usage:\n/rate <name> <good|ok|bad>\n\nExample:\n/rate HuiXian good"
        )
        return

    vote_input = context.args[-1].lower()
    target_name = " ".join(context.args[:-1]).strip()

    valid_votes = {
        "good": "good",
        "ok": "ok",
        "bad": "bad",
        "👍": "good",
        "👌": "ok",
        "👎": "bad"
    }

    if vote_input not in valid_votes:
        await update.message.reply_text("Vote must be: good, ok, or bad")
        return

    vote = valid_votes[vote_input]

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

    emoji = {"good": "👍", "ok": "👌", "bad": "👎"}[vote]
    await update.message.reply_text(f"{target_name}: {emoji}")


# /tally command
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


# main
def main():
    init_db()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("initiate", initiate))
    app.add_handler(CommandHandler("rate", rate))
    app.add_handler(CommandHandler("tally", tally))

    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
