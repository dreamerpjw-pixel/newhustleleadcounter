import os
import csv
import re
import json
from io import StringIO
from collections import defaultdict
from datetime import date

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

if not TOKEN:
    raise ValueError("BOT_TOKEN is not set")

# =========================
# STATE STORAGE 🧠
# =========================
user_state = {}

def reset_state(user_id):
    user_state[user_id] = {
        "step": 1,
        "baseline": {},
        "reported": {}
    }

# =========================
# COMMANDS 🎮
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    reset_state(user_id)

    await update.message.reply_text(
        "👋 *Welcome to the Leakage Bot (Polling Mode)*\n\n"
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

    step_text = "Waiting for CSV upload 📎" if step == 1 else "Waiting for text input 💬"

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
MERGE = {"CAM": "DSLR", "PPECAM": "DSLR"}

def normalize(w):
    return w.strip().upper()

def apply_rules(w):
    if w in IGNORE: return None
    return MERGE.get(w, w)

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
# PARSERS 📎 💬
# =========================
def parse_csv(file_bytes):
    data = defaultdict(int)
    content = file_bytes.decode("utf-8", errors="ignore")
    reader = csv.reader(StringIO(content))

    for row in reader:
        if len(row) < 5: continue
        raw_name = normalize(row[0]).split("-")[0].split("(")[0].strip()
        workshop = apply_rules(WORKSHOP_MAP.get(raw_name, raw_name))
        
        if not workshop: continue
        
        try:
            count = int(row[4].replace(",", "").strip())
            data[workshop] += count
        except: continue
    return dict(data)

def parse_text(text):
    data = defaultdict(int)
    for line in text.split("\n"):
        line = line.strip()
        if not line or line.startswith("["): continue
        match = re.match(r"(.+?)\s*[-:]?\s*([\d,]+)", line)
        if not match: continue
        w = apply_rules(normalize(match.group(1)))
        if w: data[w] += int(match.group(2).replace(",", ""))
    return dict(data)

# =========================
# ENGINE 🔍
# =========================
def compare(baseline, reported):
    all_keys = set(baseline) | set(reported)
    result = []
    for k in sorted(all_keys):
        base, rep = baseline.get(k, 0), reported.get(k, 0)
        diff = base - rep
        status = f"🔻 Leakage: {diff}" if diff > 0 else (f"⚠️ Over-reporting: {abs(diff)}" if diff < 0 else "✅ Matched")
        result.append((k, base, rep, status))
    return result

def build_report(comparison):
    lines = ["📊 *LEAKAGE REPORT*\n"]
    for k, base, rep, status in comparison:
        lines.append(f"*{k}*\nBase: {base} | Rep: {rep} | {status}\n")
    return "\n".join(lines)

# =========================
# HANDLER ⚙️
# =========================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_state: reset_state(user_id)
    
    state = user_state[user_id]
    msg = update.message
    if not msg: return

    if state["step"] == 1:
        if msg.document and msg.document.file_name.endswith('.csv'):
            file = await msg.document.get_file()
            file_bytes = await file.download_as_bytearray()
            state["baseline"] = parse_csv(file_bytes)
            state["step"] = 2
            await msg.reply_text("✅ CSV parsed. Now paste the reported leads text.")
        else:
            await msg.reply_text("📎 Please upload the baseline CSV file.")
    
    elif state["step"] == 2:
        if msg.text:
            reported = parse_text(msg.text)
            if not reported:
                await msg.reply_text("❌ No valid lead data found in your text. Try again.")
                return
            
            comparison = compare(state["baseline"], reported)
            await msg.reply_text(build_report(comparison), parse_mode="Markdown")
            reset_state(user_id)
        else:
            await msg.reply_text("💬 Please send the reported leads as text.")

# =========================
# MAIN 🚀
# =========================
if __name__ == "__main__":
    print("🤖 Bot is starting via Polling...")
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("sample", sample))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(MessageHandler((filters.TEXT | filters.Document.ALL) & ~filters.COMMAND, handle_message))

    # This replaces all the webhook/aiohttp code
    app.run_polling()
