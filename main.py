import os
import time
import random
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)

TOKEN = os.getenv("TOKEN")
PORT = int(os.environ.get("PORT", 5000))

# Admin IDs
ADMIN_IDS = {5083713667, 7020245048}

# Public usernames for membership check
REQUIRED_CHANNELS = ["proaid", "QuickAid", "ArcComic", "ExpertAid"]

# Invite links for buttons
CHANNEL_LINKS = {
    "Waifus": "https://t.me/+8jDIgoFZY98yNDE1",
    "QuickAid Comics": "https://t.me/+MjgFpHIjrZgxZTg9",
    "Arc Comics": "https://t.me/+VG9pG6hW78E2NWU1",
    "ExpertAid": "https://t.me/+CgMQndxJB1hlYmNl"
}

# Track users
USERS = set()
PENDING_CODES = {}  # {user_id: {"code": "349536", "time": 1739300000}}

# --------------------------
# Check if user is subscribed
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
    USERS.add(user_id)

    if not await is_subscribed(context.bot, user_id):
        if context.args:
            PENDING_CODES[user_id] = {"code": context.args[0].strip(), "time": time.time()}

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

    if context.args:
        code = context.args[0].strip()
        if code.isdigit():
            url = f"https://nhentai.net/g/{code}/"
            keyboard = [[InlineKeyboardButton("📖 Open Comic", url=url)]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                "🔎 Your comic link is ready:",
                reply_markup=reply_markup,
                protect_content=True
            )
            return

    await send_instructions(update)

# --------------------------
# Instructions
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

        if user_id in PENDING_CODES:
            data = PENDING_CODES.pop(user_id)
            if time.time() - data["time"] <= 86400:
                code = data["code"]
                if code.isdigit():
                    url = f"https://nhentai.net/g/{code}/"
                    keyboard = [[InlineKeyboardButton("📖 Open Comic", url=url)]]
                    reply_markup = InlineKeyboardMarkup(keyboard)

                    await query.message.reply_text(
                        "🔎 Your comic link is ready:",
                        reply_markup=reply_markup,
                        protect_content=True
                    )
                    return
            else:
                await query.message.reply_text("⚠️ Your deep-link code expired (24h limit). Please restart with a new link.")

        await send_instructions(update)
    else:
        await query.answer("❌ You must join all channels first.", show_alert=True)

# --------------------------
# Comic code handler
# --------------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    USERS.add(user_id)

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
# Admin-only broadcast
# --------------------------
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    message = " ".join(context.args)
    removed = 0
    for user in list(USERS):
        try:
            await context.bot.send_message(chat_id=user, text=message)
        except:
            USERS.remove(user)
            removed += 1
    await update.message.reply_text(
        f"📢 Broadcast sent!\nRemoved {removed} blocked users.\nCurrent users: {len(USERS)}"
    )

# --------------------------
# Admin-only stats
# --------------------------
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    await update.message.reply_text(
        f"📊 Stats:\nTotal active users: {len(USERS)}"
    )

# --------------------------
# Auto random post forward every 24h
# --------------------------
async def send_random_post(app):
    channels = ["proaid", "ArcComic", "QuickAid"]
    channel = random.choice(channels)

    messages = []
    async for msg in app.bot.get_chat_history(f"@{channel}", limit=30):
        messages.append(msg)

    if not messages:
        return

    chosen = random.choice(messages)

    for user in list(USERS):
        try:
            await app.bot.send_message(
                chat_id=user,
                text="✨ *Here’s a highlight from our channels — don’t miss it!* ✨",
                parse_mode="Markdown"
            )
            await app.bot.forward_message(
                chat_id=user,
                from_chat_id=chosen.chat.id,
                message_id=chosen.message_id
            )
        except:
            USERS.remove(user)

async def auto_loop(app):
    while True:
        await send_random_post(app)
        await asyncio.sleep(86400)  # 24 hours

# --------------------------
# Build app
# --------------------------
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(joined_callback, pattern="joined"))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
app.add_handler(CommandHandler("broadcast", broadcast))
app.add_handler(CommandHandler("stats", stats))

# --------------------------
# Run webhook
# --------------------------
if __name__ == "__main__":
    webhook_url = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/webhook"
    loop = asyncio.get_event_loop()
    loop.create_task(auto_loop(app))  # start the 24h auto job
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path="webhook",
        webhook_url=webhook_url
    )
