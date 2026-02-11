import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

TOKEN = os.getenv("TOKEN")
PORT = int(os.environ.get("PORT", 5000))

# Public usernames for membership check (bot must be admin here)
REQUIRED_CHANNELS = ["WaifusChannel", "QuickAidComics", "ArcComics", "ExpertAidCommunity"]

# Invite links for buttons (your tracking links)
CHANNEL_LINKS = {
    "Waifus": "https://t.me/+8jDIgoFZY98yNDE1",
    "QuickAid Comics": "https://t.me/+MjgFpHIjrZgxZTg9",
    "Arc Comics": "https://t.me/+VG9pG6hW78E2NWU1",
    "ExpertAid": "https://t.me/+CgMQndxJB1hlYmNl"
}

# --------------------------
# Check if user is subscribed to all channels
# --------------------------
async def is_subscribed(bot, user_id):
    for channel in REQUIRED_CHANNELS:
        try:
            member = await bot.get_chat_member(f"@{channel}", user_id)
            if member.status not in ["member", "administrator", "creator"]:
                return False
        except:
            return False
    return True

# --------------------------
# /start handler
# --------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not await is_subscribed(context.bot, user_id):
        keyboard = [
            [InlineKeyboardButton("📌 Waifus", url=CHANNEL_LINKS["Waifus"])],
            [InlineKeyboardButton("📌 QuickAid Comics", url=CHANNEL_LINKS["QuickAid Comics"])],
            [InlineKeyboardButton("📌 Arc Comics", url=CHANNEL_LINKS["Arc Comics"])],
            [InlineKeyboardButton("💡 ExpertAid Community", url=CHANNEL_LINKS["ExpertAid"])],
            [InlineKeyboardButton("✅ I Joined", callback_data="joined")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "👋 *Welcome to Arc Comics Bot!*\n\n"
            "To unlock features, you must join all required channels below.\n\n"
            "After joining, click *✅ I Joined* to verify.",
            reply_markup=reply_markup,
            parse_mode="Markdown",
            protect_content=True
        )
        return

    # Already subscribed → show instructions
    await send_instructions(update)

# --------------------------
# Instructions message
# --------------------------
async def send_instructions(update: Update):
    message = (
        "✨ *Arc Comics Bot Activated!* ✨\n\n"
        "I instantly turn your comic codes into clickable links.\n\n"
        "📌 *How to use me:* \n"
        "1️⃣ Send any comic code (numbers only)\n"
        "2️⃣ I’ll reply with a secure button linking your comic\n"
        "3️⃣ Tap the button to read instantly!\n\n"
        "⚡ Professional. Fast. Reliable."
    )
    if update.message:
        await update.message.reply_text(message, parse_mode="Markdown", protect_content=True)
    else:
        await update.callback_query.message.reply_text(message, parse_mode="Markdown", protect_content=True)

# --------------------------
# Handle 'Joined' button
# --------------------------
async def joined_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    if await is_subscribed(context.bot, user_id):
        await query.message.delete()
        await query.message.reply_text("✅ Subscription verified successfully!")
        await send_instructions(update)
    else:
        await query.answer("❌ You must join all channels first.", show_alert=True)

# --------------------------
# Comic code handler
# --------------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Block usage if unsubscribed
    if not await is_subscribed(context.bot, user_id):
        await update.message.reply_text(
            "❌ Access denied.\n\nYou must remain subscribed to all channels.\nUse /start to verify again."
        )
        return

    code = update.message.text.strip()
    if code.isdigit():
        url = f"https://nhentai.net/g/{code}/"
        keyboard = [[InlineKeyboardButton("📖 Open Comic", url=url)]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "🔎 Your comic link is ready:",
            reply_markup=reply_markup,
            protect_content=True
        )
    else:
        await update.message.reply_text(
            "⚠️ Please send only the comic code (numbers).",
            protect_content=True
        )

# --------------------------
# Build app
# --------------------------
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(joined_callback, pattern="joined"))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# --------------------------
# Run webhook
# --------------------------
if __name__ == "__main__":
    webhook_url = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/webhook"
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path="webhook",
        webhook_url=webhook_url
    )
