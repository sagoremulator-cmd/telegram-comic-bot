import os
from flask import Flask, request, abort
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Your bot token from environment (same as before)
TOKEN = os.getenv("TOKEN")

# Render gives us the hostname automatically
BASE_URL = os.getenv("RENDER_EXTERNAL_HOSTNAME")
if BASE_URL is None:
    BASE_URL = "localhost:10000"  # For local testing

# Secret webhook path (uses token for security)
WEBHOOK_PATH = f"/{TOKEN}"
WEBHOOK_URL = f"https://{BASE_URL}{WEBHOOK_PATH}"

# Create Flask app (mini web server)
flask_app = Flask(__name__)

# Create Telegram application (no polling!)
application = Application.builder().token(TOKEN).build()

# ---------------- ----------
# /start handler (unchanged from your code)
# --------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ✅ Check if user clicked a deep link with a code
    if context.args:
        code = context.args[0]
        if code.isdigit():
            url = f"https://nhentai.net/g/{code}/"
            keyboard = [[InlineKeyboardButton("📖 Open Comic", url=url)]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            # Message with protection
            await update.message.reply_text(
                "🔎 Click the button to open your comic!",
                reply_markup=reply_markup,
                protect_content=True  # Protect from forwarding/copying
            )
            return  # Exit the function so welcome message is skipped

    # 👇 Normal welcome message if no deep link
    keyboard = [
        [InlineKeyboardButton("📌 Waifus", url="https://t.me/+8jDIgoFZY98yNDE1"),
         InlineKeyboardButton("📌 QuickAid Comics", url="https://t.me/+MjgFpHIjrZgxZTg9")],
        [InlineKeyboardButton("📌 Arc Comics", url="https://t.me/+VG9pG6hW78E2NWU1"),
         InlineKeyboardButton("💡 ExpertAid Community", url="https://t.me/+CgMQndxJB1hlYmNl")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    message = (
        "👋 *Welcome to Arc Comics Bot!*\n\n"
        "_Your gateway to the hottest comics & community_\n\n"
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
        protect_content=True  # Protect welcome message
    )

# --------------------------
# Message handler (unchanged from your code)
# --------------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()

    if code.isdigit():
        url = f"https://nhentai.net/g/{code}/"

        keyboard = [[InlineKeyboardButton("📖 Open Comic", url=url)]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Message with protection
        await update.message.reply_text(
            "🔎 Click the button to open your comic!",
            reply_markup=reply_markup,
            protect_content=True  # Protect comic link message
        )
    else:
        await update.message.reply_text(
            "❌ Send only the comic code (numbers).",
            protect_content=True  # Protect error messages
        )

# Add your handlers to the application
application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# Flask route for Telegram webhook (this receives updates from Telegram)
@flask_app.route(WEBHOOK_PATH, methods=["POST"])
async def webhook():
    if request.headers.get("content-type") == "application/json":
        json_data = request.get_json()
        update = Update.de_json(json_data, application.bot)
        await application.process_update(update)
        return "", 200
    abort(403)  # Block unauthorized access

# A simple health check route (good for Render to know it's alive)
@flask_app.route("/", methods=["GET"])
def health():
    return "Bot is running! 🚀"

# For running locally (testing)
if __name__ == "__main__":
    flask_app.run(host="0.0.0.0", port=10000)
