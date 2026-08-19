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

import storage
import ads_manager

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
    Every Nth conversion per user (N = storage.get_gateway_frequency(), admin-editable)
    goes through the GitHub landing page. All other conversions go direct to nhentai.
    Returns (url, is_gateway) so callers can log gateway views.
    """
    count = USER_CONVERT_COUNT.get(user_id, 0) + 1
    USER_CONVERT_COUNT[user_id] = count

    frequency = storage.get_gateway_frequency()
    if count % frequency == 0:
        return f"{GITHUB_PAGE}?c={code}", True
    else:
        return f"https://nhentai.net/g/{code}/", False


async def maybe_show_text_ad(update: Update, context):
    """
    Storage-backed replacement for the old Ads.py pool.
    Picks an enabled ad if this user's pool cooldown has passed, sends it
    (text, or photo/video + caption), and returns True if one was shown.
    """
    user_id = update.effective_user.id
    ad = storage.pick_text_ad_for_user(user_id)
    if not ad:
        return False

    caption = f"{ad['headline']}\n{ad['body']}"
    reply_markup = None
    if ad.get("button_text") and ad.get("button_url"):
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(ad["button_text"], url=ad["button_url"])]])

    target_message = update.effective_message
    try:
        if ad.get("media_file_id"):
            if ad["media_type"] == "photo":
                await target_message.reply_photo(
                    ad["media_file_id"], caption=caption, parse_mode="Markdown",
                    reply_markup=reply_markup, protect_content=True
                )
            else:
                await target_message.reply_video(
                    ad["media_file_id"], caption=caption, parse_mode="Markdown",
                    reply_markup=reply_markup, protect_content=True
                )
        else:
            await target_message.reply_text(
                caption, parse_mode="Markdown", reply_markup=reply_markup, protect_content=True
            )
    except Exception as e:
        print(f"[ads] Failed to send text ad: {e}")
        return False

    await storage.mark_text_ad_shown(user_id)
    return True
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

    shown = await maybe_show_text_ad(update, context)
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

import uuid

BASE_URL = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}"

# Conversation states for the broadcast flow
(
    BC_AWAITING_MESSAGE,
    BC_AWAITING_TARGET_IDS,
    BC_AWAITING_BUTTON_CHOICE,
    BC_AWAITING_BUTTON_TEXT,
    BC_AWAITING_BUTTON_URL,
    BC_AWAITING_SEND_TIMING,
    BC_AWAITING_SCHEDULE_TIME,
) = range(7)


def is_admin(user_id):
    return user_id in ADMIN_IDS


def admin_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Stats", callback_data="adm_stats")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="adm_broadcast")],
        [InlineKeyboardButton("🗓️ Scheduled Broadcasts", callback_data="adm_scheduled")],
        [InlineKeyboardButton("📜 Broadcast History", callback_data="adm_history")],
        [InlineKeyboardButton("📝 Ads Settings", callback_data="adm_ads_settings")],
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


def yes_no_keyboard(yes_data, no_data):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Yes", callback_data=yes_data),
         InlineKeyboardButton("🚫 No", callback_data=no_data)],
        [InlineKeyboardButton("🔙 Cancel", callback_data="adm_root")],
    ])


def timing_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Send Now", callback_data="bc_time_now")],
        [InlineKeyboardButton("🗓️ Schedule for Later", callback_data="bc_time_later")],
        [InlineKeyboardButton("🔙 Cancel", callback_data="adm_root")],
    ])


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/admin — entry point. Silently ignored for non-admins."""
    if not is_admin(update.effective_user.id):
        return
    await update.message.reply_text("🛠️ *Admin Panel*", parse_mode="Markdown", reply_markup=admin_menu_keyboard())


LEGACY_ADS = [
    {
        "headline": "*#Ads PR GRAM Promote Anything*",
        "body": "Get Members for your Channel/Group/Bot For Free",
        "button_text": "Join Now", "button_url": "https://t.me/gram_piarbot?start=5083713667"
    },
    {
        "headline": "*#Ads Inside Ads Monetize Telegram Channel*",
        "body": "High Paying Monetization Service In Telegram",
        "button_text": "Monetize Now", "button_url": "https://t.me/InsideAds_bot/open?startapp=r_5083713667"
    },
    {
        "headline": "*#Ads Bitget Official*",
        "body": "💰Get up to 500USDT welcome pack on your first launch and Enjoy 50% off transaction fees!",
        "button_text": "Join Now",
        "button_url": "https://t.me/BitgetOfficialBot/Bitget?startapp=JwnaGhlngUX3oFNY1AUuJHFa38jeKvF"
    },
    {
        "headline": "*#Ads FoxiGrow *",
        "body": "Earn rewards by completing tasks, Minimum Withdrawal 2USDT",
        "button_text": "Earn Now", "button_url": "https://t.me/FoxiGrowbot?start=ref_5083713667"
    },
    {
        "headline": "*#Ads Hot Wallet*",
        "body": "Mine HOT On Near Protocol",
        "button_text": "Mine Now", "button_url": "https://app.hot-labs.org/link?7814048-village-279238"
    },
    {
        "headline": "*#Ads Gmail Farmer*",
        "body": "Create Gmail Account And Get Paid",
        "button_text": "Join Now", "button_url": "https://t.me/GmailFarmerBot?start=5083713667"
    },
]


async def migrate_legacy_ads_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /migrate_ads — one-time command to import the old hardcoded Ads.py list into the
    new Gist-backed Text Ads system. Safe to run multiple times; it skips ads that
    look already-imported (matched by headline) so it won't create duplicates.
    """
    if not is_admin(update.effective_user.id):
        return

    existing_headlines = {ad["headline"] for ad in storage.get_all_text_ads()}
    imported = 0
    skipped = 0

    for legacy in LEGACY_ADS:
        if legacy["headline"] in existing_headlines:
            skipped += 1
            continue
        await storage.add_text_ad({
            "headline": legacy["headline"],
            "body": legacy["body"],
            "media_file_id": None,
            "media_type": None,
            "button_text": legacy["button_text"],
            "button_url": legacy["button_url"],
        })
        imported += 1

    await update.message.reply_text(
        f"✅ Migration complete.\nImported: {imported}\nSkipped (already present): {skipped}\n\n"
        f"Check them in /admin → 📝 Ads Settings → 📋 Text Ads (pool)."
    )


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

    elif data == "adm_history":
        recent = storage.get_recent_broadcasts(limit=10)
        if not recent:
            text = "📜 *Broadcast History*\n\nNo broadcasts sent yet."
        else:
            lines = ["📜 *Broadcast History* (most recent first)\n"]
            for b in recent:
                lines.append(
                    f"🕐 {b['ts']}\n"
                    f"   Sent: {b['sent']} | Failed: {b['failed']} | Clicks: {b['clicks']}\n"
                    f"   \"{b['preview']}\""
                )
            text = "\n\n".join(lines)
        await query.message.edit_text(
            text, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="adm_root")]])
        )

    elif data == "adm_scheduled":
        pending = storage.get_pending_scheduled_broadcasts()
        if not pending:
            text = "🗓️ *Scheduled Broadcasts*\n\nNothing scheduled right now."
            kb = [[InlineKeyboardButton("🔙 Back", callback_data="adm_root")]]
        else:
            lines = ["🗓️ *Scheduled Broadcasts*\n"]
            kb = []
            for b in pending:
                target_desc = "Everyone" if b["target"] == "all" else f"{len(b['target'])} specific user(s)"
                preview = (b.get("text") or b.get("caption") or "")[:40]
                lines.append(f"🕐 {b['run_at']} → {target_desc}\n   \"{preview}\"")
                kb.append([InlineKeyboardButton(f"❌ Cancel: {b['run_at']}", callback_data=f"adm_unschedule_{b['id']}")])
            kb.append([InlineKeyboardButton("🔙 Back", callback_data="adm_root")])
            text = "\n\n".join(lines)
        await query.message.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("adm_unschedule_"):
        broadcast_id = data.replace("adm_unschedule_", "")
        await storage.remove_scheduled_broadcast(broadcast_id)
        await query.answer("Cancelled.", show_alert=False)
        # Re-render the scheduled list
        pending = storage.get_pending_scheduled_broadcasts()
        if not pending:
            text = "🗓️ *Scheduled Broadcasts*\n\nNothing scheduled right now."
            kb = [[InlineKeyboardButton("🔙 Back", callback_data="adm_root")]]
        else:
            lines = ["🗓️ *Scheduled Broadcasts*\n"]
            kb = []
            for b in pending:
                target_desc = "Everyone" if b["target"] == "all" else f"{len(b['target'])} specific user(s)"
                preview = (b.get("text") or b.get("caption") or "")[:40]
                lines.append(f"🕐 {b['run_at']} → {target_desc}\n   \"{preview}\"")
                kb.append([InlineKeyboardButton(f"❌ Cancel: {b['run_at']}", callback_data=f"adm_unschedule_{b['id']}")])
            kb.append([InlineKeyboardButton("🔙 Back", callback_data="adm_root")])
            text = "\n\n".join(lines)
        await query.message.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


# ── Broadcast conversation ──
# Flow: pick target -> compose message -> optional button+link -> send now / schedule

async def bc_start_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("Not authorized.", show_alert=True)
        return ConversationHandler.END
    await query.answer()
    context.user_data.clear()
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
    context.user_data.clear()
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


async def bc_receive_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stores the composed message, then asks whether to attach a tracked button."""
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    if update.message.photo:
        context.user_data["bc_photo_file_id"] = update.message.photo[-1].file_id
        context.user_data["bc_caption"] = update.message.caption or ""
        context.user_data["bc_text"] = None
    elif update.message.text:
        context.user_data["bc_text"] = update.message.text
        context.user_data["bc_photo_file_id"] = None
        context.user_data["bc_caption"] = None
    else:
        await update.message.reply_text("⚠️ Please send text or a photo with caption.")
        return BC_AWAITING_MESSAGE

    await update.message.reply_text(
        "🔗 *Add a link button to this broadcast?*\n\n"
        "This lets you track how many people tap it (click analytics).",
        parse_mode="Markdown",
        reply_markup=yes_no_keyboard("bc_button_yes", "bc_button_no")
    )
    return BC_AWAITING_BUTTON_CHOICE


async def bc_button_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("Not authorized.", show_alert=True)
        return ConversationHandler.END
    await query.answer()

    if query.data == "bc_button_yes":
        await query.message.edit_text(
            "Send me the *button label* (short text shown on the button).\nExample: `📖 Read Now`",
            parse_mode="Markdown",
            reply_markup=cancel_keyboard()
        )
        return BC_AWAITING_BUTTON_TEXT
    else:
        context.user_data["bc_button_text"] = None
        context.user_data["bc_button_url"] = None
        await query.message.edit_text(
            "⏱️ *When should this be sent?*",
            parse_mode="Markdown",
            reply_markup=timing_keyboard()
        )
        return BC_AWAITING_SEND_TIMING


async def bc_receive_button_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    context.user_data["bc_button_text"] = update.message.text.strip()
    await update.message.reply_text(
        "Now send me the *URL* this button should link to.\nExample: `https://t.me/ArcComic`",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard()
    )
    return BC_AWAITING_BUTTON_URL


async def bc_receive_button_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    url = update.message.text.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        await update.message.reply_text("⚠️ That doesn't look like a valid URL. Must start with http:// or https://")
        return BC_AWAITING_BUTTON_URL
    context.user_data["bc_button_url"] = url
    await update.message.reply_text(
        "⏱️ *When should this be sent?*",
        parse_mode="Markdown",
        reply_markup=timing_keyboard()
    )
    return BC_AWAITING_SEND_TIMING


async def bc_send_timing_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("Not authorized.", show_alert=True)
        return ConversationHandler.END
    await query.answer()

    if query.data == "bc_time_now":
        await query.message.edit_text("📣 Sending now...")
        await _execute_broadcast(context, chat_id_for_status=query.message.chat_id, bot=context.bot)
        context.user_data.clear()
        return ConversationHandler.END
    else:
        await query.message.edit_text(
            "🗓️ *Schedule Broadcast*\n\n"
            "Send me the exact date & time (24-hour format, your local time):\n"
            "`YYYY-MM-DD HH:MM`\n\n"
            "Example: `2026-08-20 14:30`",
            parse_mode="Markdown",
            reply_markup=cancel_keyboard()
        )
        return BC_AWAITING_SCHEDULE_TIME


async def bc_receive_schedule_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    raw = update.message.text.strip()
    try:
        parsed = time.strptime(raw, "%Y-%m-%d %H:%M")
    except ValueError:
        await update.message.reply_text(
            "⚠️ Couldn't parse that. Use the exact format `YYYY-MM-DD HH:MM`, e.g. `2026-08-20 14:30`",
            parse_mode="Markdown"
        )
        return BC_AWAITING_SCHEDULE_TIME

    run_at = time.strftime("%Y-%m-%d %H:%M:00", parsed)
    if run_at <= time.strftime("%Y-%m-%d %H:%M:%S"):
        await update.message.reply_text("⚠️ That time is in the past. Send a future date/time.")
        return BC_AWAITING_SCHEDULE_TIME

    target = context.user_data.get("bc_target")
    target_value = "all" if target == "all" else context.user_data.get("bc_ids", [])

    entry = {
        "id": uuid.uuid4().hex[:10],
        "run_at": run_at,
        "target": target_value,
        "text": context.user_data.get("bc_text"),
        "photo_file_id": context.user_data.get("bc_photo_file_id"),
        "caption": context.user_data.get("bc_caption"),
        "button_text": context.user_data.get("bc_button_text"),
        "button_url": context.user_data.get("bc_button_url"),
    }
    await storage.add_scheduled_broadcast(entry)

    await update.message.reply_text(
        f"✅ Scheduled for *{run_at}*.\nYou can view/cancel it anytime from 🗓️ Scheduled Broadcasts in the admin menu.",
        parse_mode="Markdown"
    )
    context.user_data.clear()
    return ConversationHandler.END


async def bc_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    await query.message.edit_text("🛠️ *Admin Panel*", parse_mode="Markdown", reply_markup=admin_menu_keyboard())
    return ConversationHandler.END


def build_broadcast_button(button_text, button_url, broadcast_id):
    """Wraps the destination URL in our own /click redirect so we can count taps."""
    if not button_text or not button_url:
        return None
    tracked_url = f"{BASE_URL}/click/{broadcast_id}?url={button_url}"
    return InlineKeyboardMarkup([[InlineKeyboardButton(button_text, url=tracked_url)]])


async def _execute_broadcast(context, chat_id_for_status, bot):
    """Sends a broadcast immediately using data staged in context.user_data. Used by both
    the 'Send Now' path and the scheduler loop (via a lightweight shim)."""
    ud = context.user_data
    target = ud.get("bc_target")
    target_ids = storage.get_all_user_ids() if target == "all" else ud.get("bc_ids", [])

    if not target_ids:
        await bot.send_message(chat_id_for_status, "⚠️ No recipients found. Cancelled.")
        return

    broadcast_id = uuid.uuid4().hex[:10]
    reply_markup = build_broadcast_button(ud.get("bc_button_text"), ud.get("bc_button_url"), broadcast_id)

    photo_file_id = ud.get("bc_photo_file_id")
    caption_template = ud.get("bc_caption")
    text_template = ud.get("bc_text")

    sent, failed = 0, 0
    for uid in target_ids:
        try:
            name = storage.get_display_name(uid)
            if photo_file_id:
                caption = caption_template.replace("{name}", name) if caption_template else None
                await bot.send_photo(
                    chat_id=uid, photo=photo_file_id, caption=caption,
                    parse_mode="Markdown", reply_markup=reply_markup
                )
            else:
                personalized = text_template.replace("{name}", name)
                await bot.send_message(
                    chat_id=uid, text=personalized, parse_mode="Markdown", reply_markup=reply_markup
                )
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)  # ~20 msgs/sec, safely under Telegram's rate limit

    preview = (text_template or caption_template or "")[:80]
    await storage.record_broadcast_result(broadcast_id, sent, failed, preview)

    await bot.send_message(
        chat_id_for_status,
        f"✅ Broadcast complete.\nSent: {sent}\nFailed (blocked bot / left, etc): {failed}"
        + ("\n🔗 Click tracking is active for this broadcast." if reply_markup else "")
    )


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
            MessageHandler((filters.TEXT & ~filters.COMMAND) | filters.PHOTO, bc_receive_message),
        ],
        BC_AWAITING_BUTTON_CHOICE: [
            CallbackQueryHandler(bc_cancel, pattern="^adm_root$"),
            CallbackQueryHandler(bc_button_choice, pattern="^bc_button_(yes|no)$"),
        ],
        BC_AWAITING_BUTTON_TEXT: [
            CallbackQueryHandler(bc_cancel, pattern="^adm_root$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, bc_receive_button_text),
        ],
        BC_AWAITING_BUTTON_URL: [
            CallbackQueryHandler(bc_cancel, pattern="^adm_root$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, bc_receive_button_url),
        ],
        BC_AWAITING_SEND_TIMING: [
            CallbackQueryHandler(bc_cancel, pattern="^adm_root$"),
            CallbackQueryHandler(bc_send_timing_choice, pattern="^bc_time_(now|later)$"),
        ],
        BC_AWAITING_SCHEDULE_TIME: [
            CallbackQueryHandler(bc_cancel, pattern="^adm_root$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, bc_receive_schedule_time),
        ],
    },
    fallbacks=[CallbackQueryHandler(bc_cancel, pattern="^adm_root$")],
    per_message=False,
)


# ── Background scheduler loop: checks every 60s for due scheduled broadcasts ──

async def scheduler_loop(bot):
    while True:
        try:
            due = storage.get_due_scheduled_broadcasts()
            for entry in due:
                target_ids = storage.get_all_user_ids() if entry["target"] == "all" else entry["target"]
                broadcast_id = entry["id"]
                reply_markup = build_broadcast_button(entry.get("button_text"), entry.get("button_url"), broadcast_id)

                sent, failed = 0, 0
                for uid in target_ids:
                    try:
                        name = storage.get_display_name(uid)
                        if entry.get("photo_file_id"):
                            caption = entry["caption"].replace("{name}", name) if entry.get("caption") else None
                            await bot.send_photo(
                                chat_id=uid, photo=entry["photo_file_id"], caption=caption,
                                parse_mode="Markdown", reply_markup=reply_markup
                            )
                        else:
                            personalized = (entry.get("text") or "").replace("{name}", name)
                            await bot.send_message(
                                chat_id=uid, text=personalized, parse_mode="Markdown", reply_markup=reply_markup
                            )
                        sent += 1
                    except Exception:
                        failed += 1
                    await asyncio.sleep(0.05)

                preview = (entry.get("text") or entry.get("caption") or "")[:80]
                await storage.record_broadcast_result(broadcast_id, sent, failed, preview)
                await storage.remove_scheduled_broadcast(broadcast_id)

                for admin_id in ADMIN_IDS:
                    try:
                        await bot.send_message(
                            admin_id,
                            f"✅ Scheduled broadcast sent.\nSent: {sent}\nFailed: {failed}"
                        )
                    except Exception:
                        pass
        except Exception as e:
            print(f"[scheduler] Error: {e}")

        await asyncio.sleep(60)  # check once a minute


# ═══════════════════════════════════════════════════════════════════

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("admin", admin_command))
app.add_handler(CommandHandler("migrate_ads", migrate_legacy_ads_command))
app.add_handler(broadcast_conversation)
app.add_handler(ads_manager.build_text_ad_conversation())
app.add_handler(ads_manager.build_text_ad_freq_conversation())
app.add_handler(ads_manager.build_big_ad_conversation())
app.add_handler(ads_manager.build_gateway_freq_conversation())
app.add_handler(CallbackQueryHandler(joined_callback, pattern="^joined$"))
app.add_handler(CallbackQueryHandler(
    lambda u, c: ads_manager.ads_router(u, c, ADMIN_IDS),
    pattern="^(ta_|ba_|gw_|adm_ads_settings)"
))
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


async def click_redirect(request):
    """
    Tracked-link redirect for broadcast buttons.
    /click/<broadcast_id>?url=<real destination>
    Logs the click then 302-redirects the user to the real URL.
    """
    broadcast_id = request.match_info.get("broadcast_id")
    real_url = request.query.get("url")
    if not real_url:
        return web.Response(status=400, text="Missing url parameter")

    # We don't have a reliable Telegram user_id here (this is a plain HTTP click,
    # not a bot update), so we log the click anonymously against the broadcast.
    await storage.log_click(broadcast_id, user_id=0)

    raise web.HTTPFound(location=real_url)


async def big_ad_click_redirect(request):
    """
    Tracked-link redirect for Big Ad buttons.
    /bigadclick/<big_ad_id>?url=<real destination>
    """
    big_ad_id = request.match_info.get("big_ad_id")
    real_url = request.query.get("url")
    if not real_url:
        return web.Response(status=400, text="Missing url parameter")

    await storage.log_big_ad_click(big_ad_id)
    raise web.HTTPFound(location=real_url)


async def main():
    webhook_url = f"{BASE_URL}/webhook"

    await storage.load_users()
    await app.bot.set_webhook(url=webhook_url)

    aio_app = web.Application()
    aio_app.router.add_get("/healthz", healthz)
    aio_app.router.add_post("/webhook", telegram_webhook)
    aio_app.router.add_get("/click/{broadcast_id}", click_redirect)
    aio_app.router.add_get("/bigadclick/{big_ad_id}", big_ad_click_redirect)

    runner = web.AppRunner(aio_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

    async with app:
        await app.start()
        asyncio.create_task(scheduler_loop(app.bot))
        asyncio.create_task(ads_manager.big_ad_scheduler_loop(app.bot, storage.get_all_user_ids, BASE_URL))
        print(f"Bot is running. Webhook: {webhook_url}  Health check: /healthz  Schedulers: active")
        await asyncio.Event().wait()  # run forever
        await app.stop()


if __name__ == "__main__":
    asyncio.run(main())
