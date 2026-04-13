import os
import re
from collections import defaultdict

from fastapi import FastAPI, Request
from telegram import Bot

# ---------------- TOKEN ----------------
TOKEN = os.environ.get("BOT_TOKEN")

if not TOKEN:
    raise ValueError("BOT_TOKEN not set in environment variables")

bot = Bot(token=TOKEN)

app = FastAPI()

# ---------------- DATA STORE ----------------
data = defaultdict(dict)

# ---------------- PARSER ----------------
def parse_message(text: str):
    lines = text.splitlines()

    name = "Unknown"

    # detect name (first non-numeric line)
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


# ---------------- STORAGE ----------------
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


# ---------------- WEBHOOK ENDPOINT ----------------
@app.post("/webhook")
async def webhook(req: Request):
    update = await req.json()

    if "message" in update:
        msg = update["message"]
        chat_id = msg["chat"]["id"]
        text = msg.get("text", "")

        # ignore non-text
        if not text:
            return {"ok": True}

        # commands handling
        if text.startswith("/totals"):
            response = str(get_totals())

        elif text.startswith("/person"):
            parts = text.split()
            if len(parts) < 2:
                response = "Usage: /person Ryan"
            else:
                name = " ".join(parts[1:])
                response = str(get_person(name))

        else:
            # normal message = data input
            name, parsed = parse_message(text)
            update_store(name, parsed)
            response = f"Stored for {name}: {parsed}"

        await bot.send_message(chat_id=chat_id, text=response)

    return {"ok": True}


# ---------------- HEALTH CHECK ----------------
@app.get("/")
def home():
    return {"status": "bot alive"}
