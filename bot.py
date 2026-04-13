import os
import asyncio

from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters

TOKEN = os.environ.get("BOT_TOKEN")

# ---- handlers ----

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    name, parsed = parse_message(text)
    update_store(name, parsed)

    await update.message.reply_text(
        f"Stored for {name}: {parsed}"
    )

async def totals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(str(get_totals()))

async def person(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /person Ryan")
        return

    name = " ".join(context.args)
    await update.message.reply_text(str(get_person(name)))


# ---- app ----

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
app.add_handler(CommandHandler("totals", totals))
app.add_handler(CommandHandler("person", person))

app.run_polling()
    await app.updater.idle()

if __name__ == "__main__":
    asyncio.run(main())
