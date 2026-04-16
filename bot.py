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

if not TOKEN:
    raise ValueError("BOT_TOKEN is not set")

WEBHOOK_URL = os.getenv("WEBHOOK_URL")

if not WEBHOOK_URL:
    raise ValueError("WEBHOOK_URL is not set")

# =========================
# STATE STORAGE 🧠
# =========================
user_state = {}

def reset_state(user_id):
    user_state[user_id] = {
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

    state = user_state.get(user_id) or {"step": 1, "baseline": {}, "reported": {}}
    baseline = "✅ Loaded" if state.get("baseline") else "❌ Not set"
    reported = "✅ Loaded" if state.get("reported") else "❌ Not set"

    await update.message.reply_text(
    f"📊 *Current Status*\n\n"
    f"Baseline: {baseline}\n"
    f"Reported: {reported}",
    parse_mode="Markdown",
)

async def leakage_report_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = user_state.get(user_id)

    if not state or not state.get("baseline"):
        await update.message.reply_text("❌ Baseline required for leakage report. Upload a CSV first.")
        return

    if not state.get("reported"):
        await update.message.reply_text("❌ No reported data found. Send leads text first.")
        return

    comparison = compare(state["baseline"], state["reported"])
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

    rows = list(reader)
    if not rows:
        return {}

    # Normalize headers
    headers = [h.strip().lower() for h in rows[0]]

    campaign_idx = None
    leads_idx = None

    # 🎯 Try to detect columns by name
    for i, h in enumerate(headers):
        if "campaign" in h:
            campaign_idx = i
        elif "lead" in h:
            leads_idx = i

    # 🚨 If headers not found → fallback to positional logic
    start_row = 1
    if campaign_idx is None or leads_idx is None:
        campaign_idx = 0
        leads_idx = -1
        start_row = 0  # no header

    valid_codes = set(WORKSHOP_MAP.values())

    for row in rows[start_row:]:
        if len(row) <= max(campaign_idx, leads_idx):
            continue

        raw_val = normalize(row[campaign_idx]).split("-")[0].split("(")[0].strip()

        # Map workshop
        if raw_val in valid_codes:
            workshop = raw_val
        else:
            workshop = WORKSHOP_MAP.get(raw_val, raw_val)

        workshop = apply_rules(workshop)
        if not workshop:
            continue

        try:
            count = int(row[leads_idx].replace(",", "").strip())
            data[workshop] += count
        except:
            continue

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
# HANDLERS
# =========================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = user_state.setdefault(user_id, {"baseline": {}, "reported": {}})
    msg = update.message
    if not msg:
        return


    # 📎 CASE 1: CSV UPLOAD
    if msg.document and msg.document.file_name.endswith(".csv"):
        file = await msg.document.get_file()
        file_bytes = await file.download_as_bytearray()

        state["baseline"] = parse_csv(file_bytes)

        await msg.reply_text("✅ Baseline saved. Now send reported leads text.")
    
    # 💬 CASE 2: TEXT INPUT
    if msg.text:
        reported = parse_text(msg.text)

        if not reported:
            await msg.reply_text("❌ No valid lead data found. Try again.")
            return

        state["reported"] = reported

    baseline = state.get("baseline")
    reported = state.get("reported")

    # =========================
    # DECISION ENGINE 🧠
    # =========================

    # CASE B: TEXT ONLY (no baseline yet)
    if reported and not baseline:
        await msg.reply_text(
            build_lead_count_alert_report(reported),
            parse_mode="Markdown"
        )

        await msg.reply_text(
            "📎 Upload a CSV to generate leakage report.",
        )
        return

    # CASE A: CSV ONLY (no text yet)
    if baseline and not reported:
        await msg.reply_text(
            "📊 Baseline saved. Now paste reported leads text.",
        )
        return

    # CASE C: BOTH PRESENT → FULL ENGINE
    if baseline and reported:
        comparison = compare(baseline, reported)

        await msg.reply_text(
            build_lead_count_alert_report(reported),
            parse_mode="Markdown"
        )

        await msg.reply_text(
            build_report(comparison),
            parse_mode="Markdown"
        )

        await msg.reply_text(
            build_leakage_only_report(comparison),
            parse_mode="Markdown"
        )

        return
# =========================
# MAIN 🚀
# =========================
if __name__ == "__main__":
    print("🤖 Bot is starting via Webhook...")

    app = ApplicationBuilder().token(TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("sample", sample))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("leakage", leakage_report_cmd))
    app.add_handler(CommandHandler("leadsreport", leads_report_cmd))

    app.add_handler(
        MessageHandler(
            (filters.TEXT | filters.Document.ALL) & ~filters.COMMAND,
            handle_message
        )
    )

    # Webhook start
    app.run_webhook(
    listen="0.0.0.0",
    port=int(os.environ.get("PORT", 10000)),
    webhook_url=f"{WEBHOOK_URL}/webhook",
    url_path="webhook",
)
