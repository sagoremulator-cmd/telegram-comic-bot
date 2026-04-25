import os
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)

# Import Ads system
from Ads import maybe_show_ads

TOKEN = os.getenv("TOKEN")
PORT = int(os.environ.get("PORT", 5000))

ADMIN_IDS = {5083713667, 7020245048}
REQUIRED_CHANNELS = ["Ai39k", "ArcComic", "QuickAid", "BrainRage"]

CHANNEL_LINKS = {
    "Emma": "https://t.me/+aLdg5hhj0j8zMWU1",
    "Arc Comics": "https://t.me/+VG9pG6hW78E2NWU1",
    "QuickAid Comics": "https://t.me/+MjgFpHIjrZgxZTg9",
    "BrainRage ✨": "https://t.me/+UYWqbGQc9kdiNjk1"
}

PENDING_CODES = {}
BOT_USERS = set()

async def is_subscribed(bot, user_id):
    for channel in REQUIRED_CHANNELS:
        try:
            member = await bot.get_chat_member(f"@{channel}", user_id)
            if member.status not in ["member", "administrator", "creator"]:
                return False
        except:
            return False
    return True

async def build_join_keyboard(bot, user_id):
    keyboard = []
    mapping = {
        "Emma": "Ai39k",
        "Arc Comics": "ArcComic",
        "QuickAid Comics": "QuickAid",
        "BrainRage ✨": "BrainRage"
    }
    for name, link in CHANNEL_LINKS.items():
        username = mapping.get(name)
        tick = ""
        if username:
            try:
                member = await bot.get_chat_member(f"@{username}", user_id)
                if member.status in ["member", "administrator", "creator"]:
                    tick = " ✅"
            except:
                pass
        if "QuickAid" in name:
            label = f"📌 {name}{tick}"
        elif "Arc" in name:
            label = f"📌 {name}{tick}"
        elif "BrainRage" in name:
            label = f"✨ {name}{tick}"
        elif "Emma" in name:
            label = f"📌 {name}{tick}"
        else:
            label = name + tick
        keyboard.append([InlineKeyboardButton(label, url=link)])
    keyboard.append([InlineKeyboardButton("✅ I Joined", callback_data="joined")])
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    BOT_USERS.add(user_id)
    if not await is_subscribed(context.bot, user_id):
        if context.args:
            PENDING_CODES[user_id] = {"code": context.args[0].strip(), "time": time.time()}
        reply_markup = await build_join_keyboard(context.bot, user_id)
        await update.message.reply_text(
            "👋 *Welcome to Arc Comics Bot!*\n\n"
            "To unlock features, you must join all required channels below.\n\n"
            "After joining, click *✅ I Joined* to verify.",
            reply_markup=reply_markup,
            parse_mode="Markdown",
            protect_content=False
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
                parse_mode="Markdown",
                protect_content=False
            )
            await maybe_show_ads(update)
            return
    await send_instructions(update)

async def send_instructions(update: Update):
    message = (
        "✨ *Arc Comics Bot Activated!* ✨\n\n"
        "I instantly turn your comic codes into clickable links.\n\n"
        "📌 *How to use me:* \n"
        "1️⃣ Send any comic code (numbers only)\n"
        "2️⃣ I'll reply with a secure button linking your comic\n"
        "3️⃣ Tap the button to read instantly!\n\n"
        "⚡ Professional. Fast. Reliable.\n"
        "💫 Doesn't have Codes? Get Codes ➜ @ArcComic"
    )
    if update.message:
        await update.message.reply_text(message, parse_mode="Markdown", protect_content=False)
    else:
        await update.callback_query.message.reply_text(message, parse_mode="Markdown", protect_content=False)

async def joined_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if await is_subscribed(context.bot, user_id):
        await query.message.delete()
        await query.message.reply_text("✅ Subscription verified successfully!", protect_content=False)
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
                        parse_mode="Markdown",
                        protect_content=False
                    )
                    await maybe_show_ads(update)
                    return
            else:
                await query.message.reply_text("⚠️ Your deep-link code expired (24h limit). Please restart with a new link.", protect_content=False)
        await send_instructions(update)
    else:
        await query.answer("❌ You must join all channels first.", show_alert=True)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    BOT_USERS.add(user_id)
    if not await is_subscribed(context.bot, user_id):
        await update.message.reply_text(
            "❌ Access denied.\n\nYou must remain subscribed to all channels.\nUse /start to verify again.",
            protect_content=False
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
            parse_mode="Markdown",
            protect_content=False
        )
        await maybe_show_ads(update)
    else:
        await update.message.reply_text(
            "⚠️ Please send only the comic code (numbers).",
            protect_content=False
        )

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(joined_callback, pattern="joined"))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

if __name__ == "__main__":
    webhook_url = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/webhook"
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path="webhook",
        webhook_url=webhook_url
    )
