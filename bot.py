import os

from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters

# ---------------- TOKEN ----------------
TOKEN = os.environ.get("BOT_TOKEN")

if not TOKEN:
    raise ValueError("BOT_TOKEN not set in environment variables")

# ---------------- DATA LAYER ----------------
from collections import defaultdict
import re

data = defaultdict(dict)

def parse_message(text: str):
    lines = text.splitlines()

    name = "Unknown"

    for line in lines:
        clean = line.strip()
        if clean and not re.search(r"\d", clean):
            name = clean.replace("*", "").strip()
            break

    pattern = re.compile(r"([A-Za-z]+)\s*[- ]\s*(\d+)")

    result = defaultdict(int)

    for line in lines:
        for code, value in pattern.findall(line):
            result[code.upper()] += int(value)

    return name, dict(result)


def update_store(name, parsed):
    if name not in data:
        data[name] = {}

    for k, v in parsed.items():
        data[name][k] = data[name].get(k, 0) + v


def get_totals():
    totals = defaultdict(int)

    for person in data.values():
        for k, v in person.items():
            totals[k] += v

    return dict(totals)


def get_person(name):
    return data.get(name, {})

# ---------------- HANDLERS ----------------

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    name, parsed = parse_message(text)
    update_store(name, parsed)

    await update.message.reply_text(f"Stored for {name}: {parsed}")


async def totals_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(str(get_totals()))


async def person_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /person Ryan")
        return

    name = " ".join(context.args)
    await update.message.reply_text(str(get_person(name)))

# ---------------- APP ----------------

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
app.add_handler(CommandHandler("totals", totals_cmd))
app.add_handler(CommandHandler("person", person_cmd))

if __name__ == "__main__":
    app.run_polling()
