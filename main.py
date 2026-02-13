import os
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)

TOKEN = os.getenv("TOKEN")
PORT = int(os.environ.get("PORT", 5000))

ADMIN_IDS = {5083713667, 7020245048}
SPECIAL_COMMAND = "742467"

REQUIRED_CHANNELS = ["Ai39k", "ArcComic", "QuickAid", "ExpertAid"]

CHANNEL_LINKS = {
    "Emma": "https://t.me/+aLdg5hhj0j8zMWU1",
    "Arc Comics": "https://t.me/+VG9pG6hW78E2NWU1",
    "QuickAid Comics": "https://t.me/+MjgFpHIjrZgxZTg9",
    "ExpertAid": "https://t.me/+CgMQndxJB1hlYmNl"
}

PENDING_CODES = {}
BOT_USERS = set()
BROADCAST_CONTEXT = {}

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
        "ExpertAid": "ExpertAid"
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
        elif "ExpertAid" in name:
            label = f"💡 {name} Community{tick}"
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

async def send_instructions(update: Update):
    message = (
        "✨ *Arc Comics Bot Activated!* ✨\n\n"
        "Send any comic code (numbers only) and I’ll reply with a secure button linking your comic."
    )
    if update.message:
        await update.message.reply_text(message, parse_mode="Markdown", protect_content=True)
    else:
        await update.callback_query.message.reply_text(message, parse_mode="Markdown", protect_content=True)

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
                await query.message.reply_text("⚠️ Your deep-link code expired.")
        await send_instructions(update)
    else:
        await query.answer("❌ You must join all channels first.", show_alert=True)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    BOT_USERS.add(user_id)
    text = update.message.text.strip()
    if text == SPECIAL_COMMAND and user_id in ADMIN_IDS:
        keyboard = [
            [InlineKeyboardButton("📊 Stats", callback_data="admin_stats")],
            [InlineKeyboardButton("📢 Bot Broadcast", callback_data="admin_broadcast_bot")],
            [InlineKeyboardButton("📢 All Channels + Bot Broadcast", callback_data="admin_broadcast_all")]
        ]
        await update.message.reply_text("🔐 Admin Panel", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    if not await is_subscribed(context.bot, user_id):
        await update.message.reply_text("❌ Access denied. Use /start to verify again.")
        return
    if text.isdigit():
        url = f"https://nhentai.net/g/{text}/"
        keyboard = [[InlineKeyboardButton("📖 Open Comic", url=url)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("🔎 Your comic link is ready:", reply_markup=reply_markup, protect_content=True)
    else:
        await update.message.reply_text("⚠️ Please send only the comic code (numbers).", protect_content=True)
async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if user_id not in ADMIN_IDS:
        return
    if query.data == "admin_stats":
        await query.message.reply_text(f"📊 Bot Users: {len(BOT_USERS)}")
    elif query.data == "admin_broadcast_bot":
        BROADCAST_CONTEXT[user_id] = "bot"
        await query.message.reply_text("📢 Send the post you want to broadcast to bot users.")
    elif query.data == "admin_broadcast_all":
        BROADCAST_CONTEXT[user_id] = "all"
        await query.message.reply_text("📢 Send the post you want to broadcast to bot users + channels.")

async def handle_broadcast_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS or user_id not in BROADCAST_CONTEXT:
        return
    BROADCAST_CONTEXT["message"] = update.message
    keyboard = [
        [InlineKeyboardButton("✅ Send", callback_data="broadcast_send")],
        [InlineKeyboardButton("🔙 Back", callback_data="broadcast_back")]
    ]
    await update.message.reply_text("Confirm broadcast:", reply_markup=InlineKeyboardMarkup(keyboard))

async def broadcast_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if user_id not in ADMIN_IDS or user_id not in BROADCAST_CONTEXT:
        return
    if query.data == "broadcast_send":
        mode = BROADCAST_CONTEXT[user_id]
        msg = BROADCAST_CONTEXT["message"]
        if mode == "bot":
            for uid in BOT_USERS:
                try:
                    await msg.copy(uid)
                except:
                    pass
        elif mode == "all":
            for uid in BOT_USERS:
                try:
                    await msg.copy(uid)
                except:
                    pass
            for channel in REQUIRED_CHANNELS:
                try:
                    await msg.copy(f"@{channel}")
                except:
                    pass
        BROADCAST_CONTEXT.pop(user_id, None)
        BROADCAST_CONTEXT.pop("message", None)
        await query.message.reply_text("📢 Broadcast sent.")
    elif query.data == "broadcast_back":
        BROADCAST_CONTEXT.pop(user_id, None)
        BROADCAST_CONTEXT.pop("message", None)
        await query.message.reply_text("🔙 Broadcast cancelled.")

# --------------------------
# Build app
# --------------------------
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(joined_callback, pattern="joined"))
app.add_handler(CallbackQueryHandler(admin_callback, pattern="admin_.*"))
app.add_handler(CallbackQueryHandler(broadcast_confirm, pattern="broadcast_.*"))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_broadcast_content))

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
