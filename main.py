import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes

TOKEN = os.getenv("TOKEN")
PORT = int(os.environ.get("PORT", 5000))  # Render gives you a port automatically

# --------------------------
# /start handler
# --------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        code = context.args[0]
        if code.isdigit():
            url = f"https://nhentai.net/g/{code}/"
            keyboard = [[InlineKeyboardButton("📖 Open Comic", url=url)]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                "🔎 Click the button to open your comic!",
                reply_markup=reply_markup,
                protect_content=True
            )
            return

    keyboard = [
        [InlineKeyboardButton("📌 Waifus", url="https://t.me/+8jDIgoFZY98yNDE1"),
         InlineKeyboardButton("📌 QuickAid Comics", url="https://t.me/+MjgFpHIjrZgxZTg9")],
        [InlineKeyboardButton("📌 Arc Comics", url="https://t.me/+VG9pG6hW78E2NWU1"),
         InlineKeyboardButton("💡 ExpertAid Community", url="https://t.me/+CgMQndxJB1hlYmNl")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    message = (
        "👋 *Welcome to Arc Comics BotYour gateway to the hottest comics & community_\n\n"
        "📌 *How to use me:* \n"
        "1️⃣ Send any comic code (numbers only)\n"
        "2️⃣ I’ll reply with a clickable button linking your comic\n"
        "3️⃣ Tap the button to read instantly!\n\n"
        "✨ *Enjoy your comics safely & responsibly!*"
    )

    await update.message.reply_text(
        message,
        reply_markup=reply_markup,
        parse_mode="Markdown",
        protect_content=True
    )

# --------------------------
# Message handler
# --------------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()

    if code.isdigit():
        url = f"https://nhentai.net/g/{code}/"
        keyboard = [[InlineKeyboardButton("📖 Open Comic", url=url)]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "🔎 Click the button to open your comic!",
            reply_markup=reply_markup,
            protect_content=True
        )
    else:
        await update.message.reply_text(
            "❌ Send only the comic code (numbers).",
            protect_content=True
        )

# --------------------------
# Build app
# --------------------------
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# --------------------------
# Run webhook directly
# --------------------------
if __name__ == "__main__":
    webhook_url = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/webhook"
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path="webhook",
        webhook_url=webhook_url
    )
