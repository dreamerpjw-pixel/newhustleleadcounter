import os
import re
import json
from datetime import datetime, timedelta
from collections import defaultdict

from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters


# =========================
# CONFIG
# =========================
TOKEN = os.getenv("BOT_TOKEN")
DATA_FILE = "history.json"

if not TOKEN:
    raise ValueError("BOT_TOKEN not set")


# =========================
# PARSER
# =========================
def parse_leads(text):
    data = {}
    current_person = None

    for line in text.split("\n"):
        line = line.strip()

        if line.startswith("["):
            continue

        if line.startswith("*") and line.endswith("*"):
            current_person = line.strip("*")
            data[current_person] = {}
            continue

        if line and not any(c.isdigit() for c in line) and ":" not in line:
            current_person = line
            data[current_person] = {}
            continue

        match = re.match(r"([A-Za-z ]+)\s*[-:]?\s*(\d+)", line)
        if match and current_person:
            workshop = match.group(1).strip()
            count = int(match.group(2))
            data[current_person][workshop] = count

    return data


# =========================
# STORAGE
# =========================
def save_today_totals(totals):
    today = datetime.now().strftime("%Y-%m-%d")

    try:
        with open(DATA_FILE, "r") as f:
            history = json.load(f)
    except:
        history = {}

    history[today] = dict(totals)

    with open(DATA_FILE, "w") as f:
        json.dump(history, f)


def get_yesterday_totals():
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    try:
        with open(DATA_FILE, "r") as f:
            history = json.load(f)
        return history.get(yesterday, {})
    except:
        return {}


def build_trend(today, yesterday):
    lines = ["📈 TREND TRACKER"]

    keys = set(today) | set(yesterday)

    for k in sorted(keys):
        diff = today.get(k, 0) - yesterday.get(k, 0)

        if diff > 0:
            lines.append(f"{k} ↑ +{diff}")
        elif diff < 0:
            lines.append(f"{k} ↓ {diff}")
        else:
            lines.append(f"{k} → {today.get(k, 0)}")

    return "\n".join(lines)


# =========================
# HANDLER
# =========================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    data = parse_leads(update.message.text)

    if not data:
        await update.message.reply_text("No valid data found.")
        return

    totals = defaultdict(int)

    for person, workshops in data.items():
        for w, c in workshops.items():
            totals[w] += c

    totals = dict(totals)

    save_today_totals(totals)
    yesterday = get_yesterday_totals()

    trend = build_trend(totals, yesterday)

    sorted_ws = sorted(totals.items(), key=lambda x: x[1], reverse=True)

    top = sorted_ws[:3]
    zero = [w for w, v in totals.items() if v == 0]
    low = [w for w, v in totals.items() if 1 <= v <= 2]

    today = datetime.now().strftime("%d %b %Y")

    lines = [f"📊 WORKSHOP DASHBOARD — {today}\n"]

    lines.append("🏆 Top Workshops")
    for i, (w, v) in enumerate(top, 1):
        lines.append(f"{i}. {w} — {v}")
    lines.append("")

    if zero:
        lines.append("🚨 Zero Leads")
        for w in zero:
            lines.append(f"{w} — 0")

    if low:
        lines.append("\n⚠️ Low Leads")
        for w in low:
            lines.append(f"{w} — {totals[w]}")

    lines.append("")
    lines.append(trend)

    await update.message.reply_text("\n".join(lines))


# =========================
# BOOT
# =========================
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

app.run_polling()
