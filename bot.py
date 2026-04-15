import os
import csv
import re
from io import StringIO
from collections import defaultdict

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    ContextTypes,
    filters,
    CommandHandler,
)

# =========================
# CONFIG 🔧
# =========================
TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PORT = int(os.environ.get("PORT", 10000))

if not TOKEN:
    raise ValueError("BOT_TOKEN is not set")

if not WEBHOOK_URL:
    raise ValueError("WEBHOOK_URL is not set")

# =========================
# STATE STORAGE 🧠
# =========================
user_state = {}

def reset_state(user_id):
    user_state[user_id] = {
        "step": 1,
        "baseline": {},
        "reported": {},
    }

# =========================
# COMMANDS 🎮
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    reset_state(user_id)

    await update.message.reply_text(
        "👋 *Welcome to the Leakage Bot*\n\n"
        "Step 1️⃣: Upload your baseline CSV 📎\n"
        "Step 2️⃣: Paste reported leads text 💬\n\n"
        "Use /sample to see format examples.\n"
        "Use /reset anytime to restart.",
        parse_mode="Markdown",
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🆘 *How to use*\n\n"
        "1. Upload CSV with workshop + count\n"
        "2. Paste reported text\n\n"
        "Commands:\n"
        "/start - Restart flow\n"
        "/reset - Clear session\n"
        "/sample - Show examples\n"
        "/status - Check progress",
        parse_mode="Markdown",
    )

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    reset_state(user_id)
    await update.message.reply_text("🔄 Reset complete. Upload a new CSV to start.")

async def sample(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📄 *Sample Formats*\n\n"
        "*CSV:*\n"
        "Photography - 6 Apr, 10\n"
        "Videography - 23 Mar, 5\n\n"
        "*Text:*\n"
        "PPE - 8\n"
        "VVE - 3",
        parse_mode="Markdown",
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = user_state.get(user_id, {"step": 1})

    step = state["step"]
    baseline = "✅" if state.get("baseline") else "❌"
    reported = "✅" if state.get("reported") else "❌"

    if step == 1:
        step_text = "Waiting for CSV upload 📎"
    elif step == 2:
        step_text = "Waiting for text input 💬"
    else:
        step_text = "Processing / Done"

    await update.message.reply_text(
        f"📊 *Current Status*\n\n"
        f"Step: {step_text}\n"
        f"Baseline: {baseline}\n"
        f"Reported: {reported}",
        parse_mode="Markdown",
    )

# =========================
# RULE ENGINE ⚙️
# =========================
IGNORE = {"PCA"}

MERGE = {
    "CAM": "DSLR",
    "PPECAM": "DSLR",
}

def normalize(w):
    return w.strip().upper()

def apply_rules(w):
    if w in IGNORE:
        return None
    if w in MERGE:
        return MERGE[w]
    return w

WORKSHOP_MAP = {
    "PHOTOGRAPHY": "PPE",
    "VIDEOGRAPHY": "VVE",
    "ACRYLIC PAINTING": "CCA",
    "DIGITAL ART": "DAR",
    "WATERCOLOUR": "WAR",
    "DSLR": "DSLR",
    "CANVA SOCIAL MEDIA": "CSM",
    "CANVA PRO": "GDC",
    "DJ SOUND MIXING": "PSM",
    "GENERAL AI": "PHG",
    "MUSIC PRODUCTION": "DMP",
    "GUITAR": "GMP",
    "PUBLIC SPEAKING": "PPS",
    "AI VIDEO": "AVC",
    "MONEY MANAGEMENT": "MMW",
    "LEICA": "LVS",
    "NEGOTIATION": "BNG",
    "FLORAL ARRANGEMENT": "FPS",
    "PERFUME": "SPD",
    "VIBE CODING": "AIC",
}

# =========================
# CSV PARSER 📎
# =========================
def clean_csv_workshop(raw):
    return raw.split("-")[0].split("(")[0].strip()

def parse_csv(file_bytes):
    data = defaultdict(int)
    content = file_bytes.decode("utf-8", errors="ignore")

    reader = csv.reader(StringIO(content))

    for row in reader:
        # need at least 5 columns
        if len(row) < 5:
            continue

        # =========================
        # 1. WORKSHOP NAME (COL 1)
        # =========================
        raw_name = normalize(row[0])
        clean_name = clean_csv_workshop(raw_name)

        workshop = WORKSHOP_MAP.get(clean_name, clean_name)
        workshop = apply_rules(workshop)

        if not workshop:
            continue

        # =========================
        # 2. LEAD COUNT (COL 5)
        # =========================
        try:
            count = int(row[4].replace(",", "").strip())
        except:
            continue

        data[workshop] += count

    return dict(data)

# =========================
# TEXT PARSER 💬
# =========================
def parse_text(text):
    data = defaultdict(int)

    for line in text.split("\n"):
        line = line.strip()

        if not line or line.startswith("["):
            continue

        match = re.match(r"(.+?)\s*[-:]?\s*([\d,]+)", line)
        if not match:
            continue

        w = apply_rules(normalize(match.group(1)))
        if not w:
            continue

        count = int(match.group(2).replace(",", ""))
        data[w] += count

    return dict(data)

# =========================
# LEAKAGE ENGINE 🔍
# =========================
def compare(baseline, reported):
    all_keys = set(baseline) | set(reported)
    result = []

    for k in sorted(all_keys):
        base = baseline.get(k, 0)
        rep = reported.get(k, 0)
        diff = base - rep

        if diff > 0:
            status = f"🔻 Leakage: {diff}"
        elif diff < 0:
            status = f"⚠️ Over-reporting: {abs(diff)}"
        else:
            status = "✅ Matched"

        result.append((k, base, rep, status))

    return result

# =========================
# REPORT BUILDER 📊
# =========================
def build_report(comparison):
    lines = ["📊 *LEAKAGE REPORT*\n"]

    for k, base, rep, status in comparison:
        lines.append(f"{k}")
        lines.append(f"Baseline: {base} | Reported: {rep} | {status}")
        lines.append("")

    return "\n".join(lines)

# =========================
# MAIN HANDLER ⚙️
# =========================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in user_state:
        reset_state(user_id)

    state = user_state[user_id]
    msg = update.message

    # 🧯 SAFETY CHECK (important for webhooks)
    if msg is None:
        return

    # =========================
    # STEP 1: CSV 📎
    # =========================
    if state["step"] == 1:
        if msg.document:
            file = await msg.document.get_file()
            file_bytes = await file.download_as_bytearray()

            state["baseline"] = parse_csv(file_bytes)
            state["step"] = 2

            await msg.reply_text("✅ CSV uploaded. Now send reported text.")
        else:
            await msg.reply_text("📎 Please upload CSV first.")
        return

    # =========================
    # STEP 2: TEXT 💬
    # =========================
    if state["step"] == 2:
        if not msg.text:
            await msg.reply_text("💬 Please send text input (not file or sticker).")
            return

        reported = parse_text(msg.text)

        if not reported:
            await msg.reply_text("❌ No valid leads found.")
            return

        state["reported"] = reported
        state["step"] = 3

        comparison = compare(state["baseline"], reported)
        report = build_report(comparison)

        await msg.reply_text(report, parse_mode="Markdown")

        reset_state(user_id)
        return

# =========================
# BOOT 🚀
# =========================
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_cmd))
app.add_handler(CommandHandler("reset", reset))
app.add_handler(CommandHandler("sample", sample))
app.add_handler(CommandHandler("status", status))

app.add_handler(
    MessageHandler(
        (filters.TEXT | filters.Document.ALL) & ~filters.COMMAND,
        handle_message,
    )
)

# =========================
# WEBHOOK 🌐
# =========================
from aiohttp import web

WEBHOOK_PATH = "/webhook"

async def handle(request):
    data = await request.json()
    update = Update.de_json(data, app.bot)
    await app.process_update(update)
    return web.Response(text="ok")

async def start_bot():
    await app.initialize()
    await app.start()
    await app.bot.set_webhook(WEBHOOK_URL)

async def stop_bot():
    await app.bot.delete_webhook()
    await app.stop()
    await app.shutdown()

def main():
    web_app = web.Application()
    web_app.router.add_post(WEBHOOK_PATH, handle)
    web_app.on_startup.append(lambda app_web: start_bot())
    web_app.on_cleanup.append(lambda app_web: stop_bot())

    web.run_app(web_app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    main()
