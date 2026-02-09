import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes

TOKEN = os.getenv("TOKEN")  # Stored safely in Railway variables

# --------------------------
# /start handler (polished professional welcome)
# --------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Grid-style buttons with hidden links
    keyboard = [
        [InlineKeyboardButton("📌 Waifus", url="https://t.me/+8jDIgoFZY98yNDE1"),
         InlineKeyboardButton("📌 QuickAid Comics", url="https://t.me/+MjgFpHIjrZgxZTg9")],
        [InlineKeyboardButton("📌 Arc Comics", url="https://t.me/+VG9pG6hW78E2NWU1"),
         InlineKeyboardButton("💡 ExpertAid Community", url="https://t.me/+CgMQndxJB1hlYmNl")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Clean and professional welcome message
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
        parse_mode="Markdown"
    )

# --------------------------
# Message handler (code → link)
# --------------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()

    if code.isdigit():
        url = f"https://nhentai.net/g/{code}/"

        keyboard = [
            [InlineKeyboardButton("📖 Open Comic", url=url)]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "🔎 Your comic is ready! Make sure to join our channels @QuickAid @ArcComic @proaid",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text("❌ Send only the comic code (numbers).")

# --------------------------
# Build app and add handlers
# --------------------------
app = ApplicationBuilder().token(TOKEN).build()

# Add /start handler
app.add_handler(CommandHandler("start", start))

# Keep code → link handler
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# Run bot
app.run_polling()
