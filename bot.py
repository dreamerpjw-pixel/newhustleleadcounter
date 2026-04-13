import os
import re
from datetime import date
from collections import defaultdict

from fastapi import FastAPI, Request
from telegram import Bot

# ---------------- TOKEN ----------------
TOKEN = os.environ.get("BOT_TOKEN")

if not TOKEN:
    raise ValueError("BOT_TOKEN not set in environment variables")

bot = Bot(token=TOKEN)
app = FastAPI()

# ---------------- CONFIG ----------------
ADMIN_USER_ID = int(os.environ.get("ADMIN_USER_ID", "0"))  # optional safety

# ---------------- STATE ----------------
data = defaultdict(dict)
current_day = date.today()

# ---------------- HELPERS ----------------
def normalize_name(name: str):
    return name.strip().lower()


def reset_data():
    global data
    data.clear()


def check_reset():
    global current_day

    today = date.today()

    if today != current_day:
        reset_data()
        current_day = today


def reset_data_manual():
    global data
    data.clear()


# ---------------- PARSER ----------------
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

    return normalize_name(name), dict(result)


# ---------------- STORAGE ----------------
def update_store(name, parsed):
    name = normalize_name(name)

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
    return data.get(normalize_name(name), {})


# ---------------- DASHBOARD ----------------
def classify_workshops(totals: dict):
    zero, low, healthy = [], [], []

    for workshop, count in totals.items():
        if count == 0:
            zero.append(workshop)
        elif count <= 2:
            low.append((workshop, count))
        else:
            healthy.append((workshop, count))

    return zero, low, healthy


def build_dashboard():
    totals = get_totals()

    if not totals:
        return "📊 No data yet for today."

    zero, low, healthy = classify_workshops(totals)

    lines = ["📊 WORKSHOP DASHBOARD (TODAY)\n"]

    # 🔴 ZERO
    lines.append("🔴 NO LEADS")
    lines.extend([f"- {w}" for w in zero] or ["All workshops active ✨"])
    lines.append("")

    # 🟠 LOW
    lines.append("🟠 LOW LEADS (1–2)")
    if low:
        for w, v in sorted(low, key=lambda x: x[1]):
            lines.append(f"- {w} ({v})")
    else:
        lines.append("None 🎯")
    lines.append("")

    # 🟢 HEALTHY
    lines.append("🟢 HEALTHY (3+)")
    if healthy:
        for w, v in sorted(healthy, key=lambda x: -x[1]):
            lines.append(f"- {w} ({v})")
    else:
        lines.append("None yet 📉")

    return "\n".join(lines)


# ---------------- PERSON CARD ----------------
def build_person_card(name: str, stats: dict):
    if not stats:
        return f"👤 {name}\n\nNo data found for today."

    total = sum(stats.values())

    lines = [f"👤 {name}\n"]

    for k, v in sorted(stats.items(), key=lambda x: -x[1]):
        lines.append(f"{k}: {v}")

    lines.append(f"\n📊 Total: {total} leads today")

    return "\n".join(lines)


# ---------------- WEBHOOK ----------------
@app.post("/webhook")
async def webhook(req: Request):
    check_reset()

    update = await req.json()

    if "message" in update:
        msg = update["message"]
        chat_id = msg["chat"]["id"]
        text = msg.get("text", "")
        user_id = msg["from"]["id"]

        if not text:
            return {"ok": True}

        # ---------------- COMMANDS ----------------
        if text.startswith("/dashboard"):
            response = build_dashboard()

        elif text.startswith("/totals"):
            response = str(get_totals())

        elif text.startswith("/person"):
            parts = text.split()

            if len(parts) < 2:
                response = "Usage: /person Ryan"
            else:
                name = " ".join(parts[1:])
                stats = get_person(name)
                response = build_person_card(name, stats)

        # ---------------- MANUAL RESET ----------------
        elif text.startswith("/reset"):
            if ADMIN_USER_ID and user_id != ADMIN_USER_ID:
                response = "⛔ You are not allowed to reset data."
            else:
                reset_data_manual()
                response = "🧹 Data has been reset manually."

        else:
            # ---------------- DATA INPUT ----------------
            name, parsed = parse_message(text)
            update_store(name, parsed)
            response = f"Stored for {name}: {parsed}"

        await bot.send_message(chat_id=chat_id, text=response)

    return {"ok": True}


# ---------------- HEALTH CHECK ----------------
@app.get("/")
def home():
    return {"status": "bot alive"}
