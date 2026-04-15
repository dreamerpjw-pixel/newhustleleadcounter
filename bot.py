import os
import csv
import re
import json
import threading
from io import StringIO
from collections import defaultdict
from datetime import date
from http.server import HTTPServer, BaseHTTPRequestHandler

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

async def leakage_report_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = user_state.get(user_id)

    if not state or not state.get("baseline"):
        await update.message.reply_text("❌ No baseline data found. Please upload a CSV first.")
        return

    # If they've already pasted text, we can compare. 
    # If not, we show leakage against an empty 'reported' set (showing all as leaked).
    comparison = compare(state["baseline"], state.get("reported", {}))
    report = build_leakage_only_report(comparison)
    await update.message.reply_text(report, parse_mode="Markdown")

async def leads_report_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = user_state.get(user_id)

    if not state or not state.get("reported"):
        await update.message.reply_text("❌ No reported leads found. Please paste your leads text first.")
        return

    report = build_lead_count_alert_report(state["reported"])
    await update.message.reply_text(report, parse_mode="Markdown")

# =========================
# RULE ENGINE ⚙️
# =========================
IGNORE = {"PCA","NARRATIVE WRITING","RICE SMC"}
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
# NEW REPORT BUILDERS 📊
# =========================

def build_leakage_only_report(comparison):
    """Only reports cases where Baseline > Reported"""
    lines = ["🔻 *LEAKAGE ONLY REPORT*\n"]
    found = False
    for k, base, rep, status in comparison:
        diff = base - rep
        if diff > 0:
            lines.append(f"*{k}*\nMissing: {diff} leads (Base: {base} | Rep: {rep})\n")
            found = True
    
    return "\n".join(lines) if found else "✅ No leakages found! All leads accounted for."

def build_lead_count_alert_report(reported_data):
    """Highlights zero and low (1-2) reported leads"""
    lines = ["⚠️ *LEAD COUNT ALERTS*\n"]
    
    zero_leads = []
    low_leads = []

    # Check against our known WORKSHOP_MAP to find zeros
    all_workshops = set(WORKSHOP_MAP.values())
    
    for w in all_workshops:
        count = reported_data.get(w, 0)
        if count == 0:
            zero_leads.append(w)
        elif 1 <= count <= 2:
            low_leads.append(f"{w} ({count})")

    lines.append("🔴 *ZERO LEADS REPORTED:*")
    lines.extend([f"- {w}" for w in sorted(zero_leads)] or ["None"])
    
    lines.append("\n🟠 *LOW LEADS (1-2):*")
    lines.extend([f"- {w}" for w in sorted(low_leads)] or ["None"])

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
                await msg.reply_text("❌ No valid lead data found. Try again.")
                return
            
            state["reported"] = reported
            comparison = compare(state["baseline"], reported)
            
            await msg.reply_text(build_report(comparison), parse_mode="Markdown")
            await msg.reply_text(build_leakage_only_report(comparison), parse_mode="Markdown")
            await msg.reply_text(build_lead_count_alert_report(reported), parse_mode="Markdown")

            # REMOVED reset_state(user_id) here so commands keep working!
            await msg.reply_text("✅ Analysis complete. You can use /leakage or /leadsreport to see these again, or /reset to start fresh.")

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is active")
    
    # Silence the logs so they don't clutter your terminal
    def log_message(self, format, *args):
        return

def run_health_check():
    # Retrieve the PORT from the environment (default 10000)
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    print(f"📡 Heartbeat server started on port {port}")
    server.serve_forever()


# =========================
# MAIN 🚀
# =========================
if __name__ == "__main__":
    # 1. Start the Heartbeat for the hosting provider
    threading.Thread(target=run_health_check, daemon=True).start()
    
    print("🤖 Bot is starting via Polling...")
    
    # 2. Build the Application
    app = ApplicationBuilder().token(TOKEN).build()

    # 3. Add all your Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("sample", sample))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("leakage", leakage_report_cmd))
    app.add_handler(CommandHandler("leadsreport", leads_report_cmd))

    # General Messages (CSV and Text input)
    app.add_handler(MessageHandler((filters.TEXT | filters.Document.ALL) & ~filters.COMMAND, handle_message))

    # 4. Start Polling
    app.run_polling()
