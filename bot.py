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
        "You can upload files in any order:\n"
        "• **Upload CSV**: Saves as baseline.\n"
        "• **Paste Text**: Shows lead alerts & prompts for CSV.\n"
        "• **Both**: Generates full leakage & leakage-only reports.\n\n"
        "Use /help for more details or /reset to start over.",
        parse_mode="Markdown",
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Explains how the logic works and lists commands"""
    help_text = (
        "🆘 *How to use this Bot*\n\n"
        "**1. Baseline Only (CSV)**\n"
        "Upload a `.csv` file. The bot will store these counts as your 'source of truth'.\n\n"
        "**2. Alerts Only (Text)**\n"
        "Paste your leads text. The bot will immediately show **Zero Leads** and **Low Leads** alerts, then ask for a CSV.\n\n"
        "**3. Full Analysis (Both)**\n"
        "Once the bot has both, it automatically generates the comparison reports.\n\n"
        "**Commands:**\n"
        "/start - Restart the bot\n"
        "/status - Check what files are currently uploaded\n"
        "/sample - See CSV and Text formatting examples\n"
        "/reset - Wipe current data and start fresh\n"
        "/leakage - Manually trigger comparison (requires both files)"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = user_state.get(user_id) or {"baseline": None, "reported": None}
    
    baseline_status = "✅ Loaded" if state.get("baseline") else "❌ Missing"
    reported_status = "✅ Loaded" if state.get("reported") else "❌ Missing"

    await update.message.reply_text(
        f"📊 *Current Session Status*\n\n"
        f"**Baseline CSV:** {baseline_status}\n"
        f"**Reported Text:** {reported_status}\n\n"
        "Ready to generate reports? Just upload the missing piece!",
        parse_mode="Markdown",
    )

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    reset_state(user_id)
    await update.message.reply_text("🔄 *Session Reset.* All uploaded data has been cleared.", parse_mode="Markdown")

async def sample(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📄 *Sample Formats*\n\n"
        "*CSV Format:*\n"
        "Campaign name, Leads\n"
        "Photography - 6 Apr, 10\n"
        "Videography - 23 Mar, 5\n\n"
        "*Text Format:*\n"
        "PPE - 8\n"
        "VVE - 3",
        parse_mode="Markdown",
    )

async def leakage_report_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = user_state.get(user_id)

    if not state or not state.get("baseline") or not state.get("reported"):
        await update.message.reply_text("⚠️ *Error:* You need both CSV and Text data for this.")
        return

    comparison = compare(state["baseline"], state["reported"])
    await update.message.reply_text(build_report(comparison), parse_mode="Markdown")
    await update.message.reply_text(build_leakage_only_report(comparison), parse_mode="Markdown")

async def leads_report_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = user_state.get(user_id)

    if not state or not state.get("reported"):
        await update.message.reply_text("❌ No reported leads found.")
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
    if user_id not in user_state:
        reset_state(user_id)
    
    state = user_state[user_id]
    msg = update.message
    if not msg:
        return

    # 1. IDENTIFY AND PARSE INPUT
    data_received = False

    # Check for CSV Document
    if msg.document and msg.document.file_name.lower().endswith(".csv"):
        try:
            file = await msg.document.get_file()
            file_bytes = await file.download_as_bytearray()
            parsed_data = parse_csv(file_bytes)
            
            if parsed_data:
                state["baseline"] = parsed_data
                data_received = True
                await msg.reply_text(f"✅ *CSV Baseline Received!* ({len(parsed_data)} campaigns loaded)", parse_mode="Markdown")
            else:
                await msg.reply_text("❌ CSV was empty or format was unrecognized. Check /sample.")
                return
        except Exception as e:
            await msg.reply_text(f"❌ Error processing CSV: {str(e)}")
            return

    # Check for Text Input (if no document was processed)
    elif msg.text and not msg.text.startswith('/'):
        reported = parse_text(msg.text)
        if reported:
            state["reported"] = reported
            data_received = True
            await msg.reply_text("✅ *Text Lead Data Received!*", parse_mode="Markdown")
        else:
            await msg.reply_text("❌ No valid lead data found in your text. Please check /sample.")
            return

    # 2. DECISION ENGINE (Only trigger if we just received data)
    if data_received:
        baseline = state.get("baseline")
        reported = state.get("reported")

        if baseline and not reported:
            await msg.reply_text("👉 Now, please paste your **reported leads text**.")

        elif reported and not baseline:
            # Show the immediate alert report
            alert_report = build_lead_count_alert_report(reported)
            await msg.reply_text(alert_report, parse_mode="Markdown")
            await msg.reply_text("👉 Now, please upload your **baseline CSV**.")

        elif baseline and reported:
            comparison = compare(baseline, reported)
            await msg.reply_text("📊 *Generating Full Analysis...*", parse_mode="Markdown")
            await msg.reply_text(build_report(comparison), parse_mode="Markdown")
            await msg.reply_text(build_leakage_only_report(comparison), parse_mode="Markdown")
    
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
