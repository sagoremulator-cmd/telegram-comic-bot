import os
import time
import asyncio
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes,
    ConversationHandler
)

from Ads import maybe_show_ads
import storage

TOKEN = os.getenv("TOKEN")
PORT = int(os.environ.get("PORT", 5000))

ADMIN_IDS = {5083713667}
REQUIRED_CHANNELS = ["Ai39k", "ArcComic", "QuickAid", "BrainRage"]

CHANNEL_LINKS = {
    "Emma": "https://t.me/+aLdg5hhj0j8zMWU1",
    "Arc Comics": "https://t.me/+VG9pG6hW78E2NWU1",
    "QuickAid Comics": "https://t.me/+MjgFpHIjrZgxZTg9",
    "BrainRage ✨": "https://t.me/+UYWqbGQc9kdiNjk1"
}

# Landing pages
GITHUB_PAGE  = "https://jizzybx.github.io/linkgateway/comic.html"  # Mondiad ads
BLOG_BASE    = "https://dogyabhi.blogspot.com/p/read.html"          # Adsterra (backup, not used)

PENDING_CODES = {}

# ── Per-user convert counter (session-only, resets on restart — fine, it's cosmetic) ──
USER_CONVERT_COUNT = {}


def get_comic_url(user_id: int, code: str) -> str:
    """
    Every 5th conversion per user goes through GitHub landing page.
    All other conversions go direct to nhentai.
    Returns (url, is_gateway) so callers can log gateway views.
    """
    count = USER_CONVERT_COUNT.get(user_id, 0) + 1
    USER_CONVERT_COUNT[user_id] = count

    if count % 5 == 0:
        # 5th, 10th, 15th... → landing page with Mondiad ads
        return f"{GITHUB_PAGE}?c={code}", True
    else:
        # All others → direct
        return f"https://nhentai.net/g/{code}/", False


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


async def deliver_comic(update: Update, context, user_id, code):
    """Shared logic: build the comic URL, send it, log a gateway view if applicable, maybe show a text ad."""
    url, is_gateway = get_comic_url(user_id, code)
    if is_gateway:
        await storage.log_gateway_view(user_id)

    keyboard = [[InlineKeyboardButton("📖 Read Comic", url=url)]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Works whether this came from a normal message or a callback query,
    # since update.effective_message resolves correctly either way.
    target_message = update.effective_message
    await target_message.reply_text(
        "🔎 Your comic link is ready:",
        reply_markup=reply_markup,
        parse_mode="Markdown",
        protect_content=False
    )

    shown = await maybe_show_ads(update)
    if shown:
        await storage.log_text_ad_view(user_id)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await storage.register_user(update.effective_user)

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
            await deliver_comic(update, context, user_id, code)
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
                    await deliver_comic(update, context, user_id, code)
                    return
            else:
                await query.message.reply_text(
                    "⚠️ Your deep-link code expired (24h limit). Please restart with a new link.",
                    protect_content=False
                )
        await send_instructions(update)
    else:
        await query.answer("❌ You must join all channels first.", show_alert=True)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await storage.register_user(update.effective_user)

    if not await is_subscribed(context.bot, user_id):
        await update.message.reply_text(
            "❌ Access denied.\n\nYou must remain subscribed to all channels.\nUse /start to verify again.",
            protect_content=False
        )
        return

    code = update.message.text.strip()
    if code.isdigit():
        await deliver_comic(update, context, user_id, code)
    else:
        await update.message.reply_text(
            "⚠️ Please send only the comic code (numbers).",
            protect_content=False
        )


# ═══════════════════════════════════════════════════════════════════
# ADMIN PANEL — inline-button menu system, only visible/usable to ADMIN_IDS
# ═══════════════════════════════════════════════════════════════════

# Conversation states for the broadcast flow
BC_AWAITING_MESSAGE, BC_AWAITING_TARGET_IDS = range(2)


def is_admin(user_id):
    return user_id in ADMIN_IDS


def admin_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Stats", callback_data="adm_stats")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="adm_broadcast")],
        [InlineKeyboardButton("❌ Close", callback_data="adm_close")],
    ])


def stats_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Total Users", callback_data="adm_stats_users")],
        [InlineKeyboardButton("🌐 Gateway Ads Views", callback_data="adm_stats_gateway")],
        [InlineKeyboardButton("📝 Text Ads Views", callback_data="adm_stats_textads")],
        [InlineKeyboardButton("🔙 Back", callback_data="adm_root")],
    ])


def view_period_keyboard(kind):
    """kind: 'gateway' or 'textads' — used to route which stat to show, and to Back to Stats menu."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 Today", callback_data=f"adm_{kind}_today")],
        [InlineKeyboardButton("🗓️ Monthly", callback_data=f"adm_{kind}_month")],
        [InlineKeyboardButton("📈 Total", callback_data=f"adm_{kind}_total")],
        [InlineKeyboardButton("🔙 Back", callback_data="adm_stats")],
    ])


def broadcast_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Send to Everyone", callback_data="adm_bc_all")],
        [InlineKeyboardButton("🎯 Send to Specific Users", callback_data="adm_bc_specific")],
        [InlineKeyboardButton("🔙 Back", callback_data="adm_root")],
    ])


def cancel_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="adm_root")]])


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/admin — entry point. Silently ignored for non-admins."""
    if not is_admin(update.effective_user.id):
        return
    await update.message.reply_text("🛠️ *Admin Panel*", parse_mode="Markdown", reply_markup=admin_menu_keyboard())


async def admin_menu_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles all adm_* callback buttons that are NOT part of the broadcast conversation."""
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("Not authorized.", show_alert=True)
        return
    await query.answer()

    data = query.data

    if data == "adm_root":
        await query.message.edit_text("🛠️ *Admin Panel*", parse_mode="Markdown", reply_markup=admin_menu_keyboard())

    elif data == "adm_close":
        await query.message.delete()

    elif data == "adm_stats":
        await query.message.edit_text("📊 *Stats Menu*", parse_mode="Markdown", reply_markup=stats_menu_keyboard())

    elif data == "adm_stats_users":
        count = storage.get_user_count()
        await query.message.edit_text(
            f"👥 *Total Users:* {count}",
            parse_mode="Markdown",
            reply_markup=stats_menu_keyboard()
        )

    elif data == "adm_stats_gateway":
        await query.message.edit_text(
            "🌐 *Gateway Ads Views*\nChoose a period:",
            parse_mode="Markdown",
            reply_markup=view_period_keyboard("gateway")
        )

    elif data == "adm_stats_textads":
        await query.message.edit_text(
            "📝 *Text Ads Views*\nChoose a period:",
            parse_mode="Markdown",
            reply_markup=view_period_keyboard("textads")
        )

    elif data.startswith("adm_gateway_"):
        period = data.replace("adm_gateway_", "")
        stats = storage.get_gateway_stats()
        label = {"today": "Today", "month": "This Month", "total": "All-Time"}[period]
        await query.message.edit_text(
            f"🌐 *Gateway Ads Views — {label}*\n\n{stats[period]} views",
            parse_mode="Markdown",
            reply_markup=view_period_keyboard("gateway")
        )

    elif data.startswith("adm_textads_"):
        period = data.replace("adm_textads_", "")
        stats = storage.get_text_ad_stats()
        label = {"today": "Today", "month": "This Month", "total": "All-Time"}[period]
        await query.message.edit_text(
            f"📝 *Text Ads Views — {label}*\n\n{stats[period]} views",
            parse_mode="Markdown",
            reply_markup=view_period_keyboard("textads")
        )

    elif data == "adm_broadcast":
        await query.message.edit_text(
            "📢 *Broadcast Menu*", parse_mode="Markdown", reply_markup=broadcast_menu_keyboard()
        )


# ── Broadcast conversation (multi-step: pick target → send message → confirm) ──

async def bc_start_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("Not authorized.", show_alert=True)
        return ConversationHandler.END
    await query.answer()
    context.user_data["bc_target"] = "all"
    await query.message.edit_text(
        "📤 *Broadcasting to Everyone*\n\n"
        "Send me the message now.\n"
        "• Plain text, OR a photo with a caption.\n"
        "• Use `{name}` anywhere to auto-insert each user's first name.\n\n"
        "Example: `Hey {name}, good morning! ☀️`",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard()
    )
    return BC_AWAITING_MESSAGE


async def bc_start_specific(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("Not authorized.", show_alert=True)
        return ConversationHandler.END
    await query.answer()
    context.user_data["bc_target"] = "specific"
    await query.message.edit_text(
        "🎯 *Broadcast to Specific Users*\n\n"
        "Send me the user IDs, comma-separated.\n"
        "Example: `123456789,987654321`",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard()
    )
    return BC_AWAITING_TARGET_IDS


async def bc_receive_target_ids(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    raw = update.message.text.strip()
    try:
        ids = [int(x.strip()) for x in raw.split(",") if x.strip()]
    except ValueError:
        await update.message.reply_text(
            "⚠️ Couldn't parse that. Send numeric IDs separated by commas, e.g. `123,456`",
            parse_mode="Markdown"
        )
        return BC_AWAITING_TARGET_IDS

    if not ids:
        await update.message.reply_text("⚠️ No valid IDs found. Try again.")
        return BC_AWAITING_TARGET_IDS

    context.user_data["bc_ids"] = ids
    await update.message.reply_text(
        f"Got {len(ids)} user ID(s).\n\n"
        "Now send me the message.\n"
        "• Plain text, OR a photo with a caption.\n"
        "• Use `{name}` to auto-insert each user's first name.",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard()
    )
    return BC_AWAITING_MESSAGE


async def bc_receive_message_and_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    target = context.user_data.get("bc_target")
    if target == "all":
        target_ids = storage.get_all_user_ids()
    else:
        target_ids = context.user_data.get("bc_ids", [])

    if not target_ids:
        await update.message.reply_text("⚠️ No recipients found. Cancelling.")
        context.user_data.clear()
        return ConversationHandler.END

    photo_file_id = None
    caption_template = None
    text_template = None

    if update.message.photo:
        photo_file_id = update.message.photo[-1].file_id
        caption_template = update.message.caption or ""
    elif update.message.text:
        text_template = update.message.text
    else:
        await update.message.reply_text("⚠️ Please send text or a photo with caption.")
        return BC_AWAITING_MESSAGE

    status_msg = await update.message.reply_text(f"📣 Sending to {len(target_ids)} user(s)...")

    sent, failed = 0, 0
    for uid in target_ids:
        try:
            name = storage.get_display_name(uid)
            if photo_file_id is not None:
                caption = caption_template.replace("{name}", name) if caption_template else None
                await context.bot.send_photo(
                    chat_id=uid, photo=photo_file_id, caption=caption, parse_mode="Markdown"
                )
            else:
                personalized = text_template.replace("{name}", name)
                await context.bot.send_message(chat_id=uid, text=personalized, parse_mode="Markdown")
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)  # ~20 msgs/sec, safely under Telegram's rate limit

    await status_msg.edit_text(
        f"✅ Broadcast complete.\nSent: {sent}\nFailed (blocked bot / left, etc): {failed}"
    )
    context.user_data.clear()
    return ConversationHandler.END


async def bc_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    await query.message.edit_text("🛠️ *Admin Panel*", parse_mode="Markdown", reply_markup=admin_menu_keyboard())
    return ConversationHandler.END


broadcast_conversation = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(bc_start_all, pattern="^adm_bc_all$"),
        CallbackQueryHandler(bc_start_specific, pattern="^adm_bc_specific$"),
    ],
    states={
        BC_AWAITING_TARGET_IDS: [
            CallbackQueryHandler(bc_cancel, pattern="^adm_root$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, bc_receive_target_ids),
        ],
        BC_AWAITING_MESSAGE: [
            CallbackQueryHandler(bc_cancel, pattern="^adm_root$"),
            MessageHandler((filters.TEXT & ~filters.COMMAND) | filters.PHOTO, bc_receive_message_and_send),
        ],
    },
    fallbacks=[CallbackQueryHandler(bc_cancel, pattern="^adm_root$")],
    per_message=False,
)


# ═══════════════════════════════════════════════════════════════════

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("admin", admin_command))
app.add_handler(broadcast_conversation)
app.add_handler(CallbackQueryHandler(joined_callback, pattern="^joined$"))
app.add_handler(CallbackQueryHandler(admin_menu_router, pattern="^adm_"))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))


async def healthz(request):
    """Health-check endpoint for cron-job.org / UptimeRobot to keep the free Render instance awake."""
    return web.Response(text="OK")


async def telegram_webhook(request):
    """Receives updates from Telegram and hands them to the PTB application."""
    data = await request.json()
    update = Update.de_json(data, app.bot)
    await app.update_queue.put(update)
    return web.Response(text="OK")


async def main():
    webhook_url = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/webhook"

    await storage.load_users()
    await app.bot.set_webhook(url=webhook_url)

    aio_app = web.Application()
    aio_app.router.add_get("/healthz", healthz)
    aio_app.router.add_post("/webhook", telegram_webhook)

    runner = web.AppRunner(aio_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

    async with app:
        await app.start()
        print(f"Bot is running. Webhook: {webhook_url}  Health check: /healthz")
        await asyncio.Event().wait()  # run forever
        await app.stop()


if __name__ == "__main__":
    asyncio.run(main())
