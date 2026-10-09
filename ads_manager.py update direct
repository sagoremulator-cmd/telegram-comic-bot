"""
Admin UI + conversation flows for:
  - Text Ads (Ads.py-style pool, shown on a per-user global cooldown)
  - Big Ads (individually scheduled recurring campaigns: daily/weekly at a set time)
  - Gateway frequency (how often the GitHub landing page gateway triggers)

All data is persisted via storage.py (Gist-backed), so nothing here is lost on redeploy.
"""

import os
import asyncio
import time
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler
)

import storage
import formatting

# Private channel used as a durable, reliable backing store for ad media.
# We copy every uploaded ad photo/video here once, and use THIS copy's file_id
# for all future sends — protects against the (rare) case where a file_id tied
# only to an admin's personal chat with the bot becomes unusable later.
STORAGE_CHANNEL_ID = int(os.getenv("LIBRARY_CHANNEL_ID", "-1003906982358"))


async def _archive_media_to_channel(bot, message):
    """
    Forwards an incoming photo/video message into the private storage channel.
    forward_message returns a full Message object (unlike copy_message, which only
    returns a bare MessageId) — so we can read back a fresh, durable file_id from
    the forwarded copy sitting permanently in the channel.
    Falls back to the original file_id if forwarding fails for any reason (e.g.
    missing bot permissions), so ad creation never breaks even if archiving does.
    """
    try:
        forwarded = await bot.forward_message(
            chat_id=STORAGE_CHANNEL_ID,
            from_chat_id=message.chat_id,
            message_id=message.message_id,
        )
        if forwarded.photo:
            return forwarded.photo[-1].file_id, "photo"
        elif forwarded.video:
            return forwarded.video.file_id, "video"
    except Exception as e:
        print(f"[ads_manager] Failed to archive media to storage channel: {e}")

    # Fallback: use the original file_id if archiving didn't work
    if message.photo:
        return message.photo[-1].file_id, "photo"
    elif message.video:
        return message.video.file_id, "video"
    return None, None

WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# ═══════════════════════════════════════════════════════════════════
# Conversation states
# ═══════════════════════════════════════════════════════════════════
(
    AD_AWAITING_TEXT,
    AD_AWAITING_MEDIA_CHOICE,
    AD_AWAITING_MEDIA,
    AD_AWAITING_BUTTON_TEXT,
    AD_AWAITING_BUTTON_URL,
    AD_PREVIEW,
    AD_AWAITING_FREQ_HOURS,
    AD_AWAITING_EDIT_FIELD,
    BIGAD_AWAITING_REPEAT_TYPE,
    BIGAD_AWAITING_WEEKDAY,
    BIGAD_AWAITING_HOUR,
    BIGAD_AWAITING_MINUTE,
    GW_AWAITING_FREQ,
) = range(13)


# ═══════════════════════════════════════════════════════════════════
# Shared keyboards
# ═══════════════════════════════════════════════════════════════════

def ads_settings_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Text Ads (pool)", callback_data="ta_menu")],
        [InlineKeyboardButton("🎯 Big Ads (scheduled)", callback_data="ba_menu")],
        [InlineKeyboardButton("🌐 Gateway Frequency", callback_data="gw_menu")],
        [InlineKeyboardButton("🔙 Back", callback_data="adm_root")],
    ])


def cancel_kb(back_to="adm_ads_settings"):
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data=back_to)]])


def yes_no_kb(yes_data, no_data, back_to="adm_ads_settings"):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Yes", callback_data=yes_data),
         InlineKeyboardButton("🚫 No", callback_data=no_data)],
        [InlineKeyboardButton("🔙 Cancel", callback_data=back_to)],
    ])


# ═══════════════════════════════════════════════════════════════════
# TEXT ADS — list / manage screens
# ═══════════════════════════════════════════════════════════════════

def ta_menu_keyboard():
    ads = storage.get_all_text_ads()
    kb = []
    for ad in ads:
        status = "✅" if ad.get("enabled") else "🚫"
        label = f"{status} {ad['headline'][:30]}"
        kb.append([InlineKeyboardButton(label, callback_data=f"ta_view_{ad['id']}")])
    kb.append([InlineKeyboardButton("➕ Add New Ad", callback_data="ta_add")])
    kb.append([InlineKeyboardButton(f"⏱️ Frequency: {storage.get_text_ads_frequency()}h", callback_data="ta_freq")])
    kb.append([InlineKeyboardButton("🔙 Back", callback_data="adm_ads_settings")])
    return InlineKeyboardMarkup(kb)


def ta_manage_keyboard(ad_id):
    ad = storage.get_text_ad(ad_id)
    toggle_label = "🚫 Disable" if ad and ad.get("enabled") else "✅ Enable"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(toggle_label, callback_data=f"ta_toggle_{ad_id}")],
        [InlineKeyboardButton("🗑️ Delete", callback_data=f"ta_delete_{ad_id}")],
        [InlineKeyboardButton("🔙 Back", callback_data="ta_menu")],
    ])


def render_ad_preview_text(draft):
    headline = draft.get("headline", "")
    body = draft.get("body", "")
    return f"{headline}\n{body}"


# ═══════════════════════════════════════════════════════════════════
# TEXT ADS — router for simple (non-conversation) button taps
# ═══════════════════════════════════════════════════════════════════

async def ads_router(update: Update, context: ContextTypes.DEFAULT_TYPE, admin_ids):
    """Handles all ta_*, ba_*, gw_* callback buttons that are single-tap (not multi-step)."""
    query = update.callback_query
    if query.from_user.id not in admin_ids:
        await query.answer("Not authorized.", show_alert=True)
        return
    await query.answer()
    data = query.data

    if data == "adm_ads_settings":
        await query.message.edit_text(
            "📝 *Ads Settings*", parse_mode="Markdown", reply_markup=ads_settings_menu_keyboard()
        )

    elif data == "ta_menu":
        await query.message.edit_text(
            "📋 *Text Ads (Pool)*\n\nThese rotate on a per-user cooldown.\nTap an ad to manage it.",
            parse_mode="Markdown", reply_markup=ta_menu_keyboard()
        )

    elif data.startswith("ta_view_"):
        ad_id = data.replace("ta_view_", "")
        ad = storage.get_text_ad(ad_id)
        if not ad:
            print(f"[ads_manager] ta_view_ requested unknown ad_id: {ad_id!r}. "
                  f"Known ids: {[a['id'] for a in storage.get_all_text_ads()]}")
            await query.message.edit_text(
                f"⚠️ Ad not found (id: {ad_id}).\nIt may have been deleted, or is a "
                f"duplicate from an earlier migration run. Try /migrate_ads again or "
                f"delete this stale entry from the list.",
                reply_markup=ta_menu_keyboard()
            )
            return
        status = "✅ Enabled" if ad.get("enabled") else "🚫 Disabled"
        media_desc = ad.get("media_type", "none") or "none"
        text = (
            f"*{ad['headline']}*\n{ad['body']}\n\n"
            f"Status: {status}\n"
            f"Media: {media_desc}\n"
            f"Button: {ad.get('button_text') or '(none)'} → {ad.get('button_url') or '(none)'}"
        )
        try:
            await query.message.edit_text(text, parse_mode="Markdown", reply_markup=ta_manage_keyboard(ad_id))
        except Exception as e:
            print(f"[ads_manager] Failed to render ta_view_ for {ad_id}: {e}")
            # Markdown parse failure (e.g. unescaped * in headline/body) — retry without parse_mode
            await query.message.edit_text(text, reply_markup=ta_manage_keyboard(ad_id))

    elif data.startswith("ta_toggle_"):
        ad_id = data.replace("ta_toggle_", "")
        await storage.toggle_text_ad(ad_id)
        ad = storage.get_text_ad(ad_id)
        status = "✅ Enabled" if ad and ad.get("enabled") else "🚫 Disabled"
        await query.answer(f"Ad is now {status}", show_alert=False)
        await query.message.edit_reply_markup(reply_markup=ta_manage_keyboard(ad_id))

    elif data.startswith("ta_delete_"):
        ad_id = data.replace("ta_delete_", "")
        await storage.delete_text_ad(ad_id)
        await query.answer("Deleted.", show_alert=False)
        await query.message.edit_text("📋 *Text Ads (Pool)*", parse_mode="Markdown", reply_markup=ta_menu_keyboard())

    elif data == "ba_menu":
        await query.message.edit_text(
            "🎯 *Big Ads (Scheduled)*\n\nEach one runs on its own recurring schedule.\nTap one to manage it.",
            parse_mode="Markdown", reply_markup=ba_menu_keyboard()
        )

    elif data.startswith("ba_view_"):
        ad_id = data.replace("ba_view_", "")
        ad = storage.get_big_ad(ad_id)
        if not ad:
            await query.message.edit_text("Ad not found (maybe deleted).", reply_markup=ba_menu_keyboard())
            return
        status = "✅ Enabled" if ad.get("enabled") else "🚫 Disabled"
        sched = ad.get("schedule", {})
        if sched.get("type") == "daily":
            sched_desc = f"Daily at {sched.get('hour', 0):02d}:{sched.get('minute', 0):02d}"
        else:
            wd = WEEKDAY_NAMES[sched.get("weekday", 0)]
            sched_desc = f"Weekly on {wd} at {sched.get('hour', 0):02d}:{sched.get('minute', 0):02d}"
        stats = storage.get_big_ad_stats(ad_id)
        text = (
            f"*{ad['headline']}*\n{ad['body']}\n\n"
            f"Status: {status}\n"
            f"Schedule: {sched_desc}\n"
            f"Media: {ad.get('media_type') or 'none'}\n"
            f"Button: {ad.get('button_text') or '(none)'}\n\n"
            f"📊 Runs: {stats['runs']} | Sent: {stats['total_sent']} | "
            f"Failed: {stats['total_failed']} | Clicks: {stats['total_clicks']}"
        )
        await query.message.edit_text(text, parse_mode="Markdown", reply_markup=ba_manage_keyboard(ad_id))

    elif data.startswith("ba_toggle_"):
        ad_id = data.replace("ba_toggle_", "")
        await storage.toggle_big_ad(ad_id)
        ad = storage.get_big_ad(ad_id)
        status = "✅ Enabled" if ad and ad.get("enabled") else "🚫 Disabled"
        await query.answer(f"Ad is now {status}", show_alert=False)
        await query.message.edit_reply_markup(reply_markup=ba_manage_keyboard(ad_id))

    elif data.startswith("ba_delete_"):
        ad_id = data.replace("ba_delete_", "")
        await storage.delete_big_ad(ad_id)
        await query.answer("Deleted.", show_alert=False)
        await query.message.edit_text("🎯 *Big Ads (Scheduled)*", parse_mode="Markdown", reply_markup=ba_menu_keyboard())

    elif data == "gw_menu":
        current = storage.get_gateway_frequency()
        await query.message.edit_text(
            f"🌐 *Gateway Frequency*\n\n"
            f"Currently: every *{current}th* comic conversion routes through the ad-gateway landing page.\n\n"
            f"Tap below to change it.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✏️ Change Frequency", callback_data="gw_edit")],
                [InlineKeyboardButton("🔙 Back", callback_data="adm_ads_settings")],
            ])
        )


def ba_menu_keyboard():
    ads = storage.get_all_big_ads()
    kb = []
    for ad in ads:
        status = "✅" if ad.get("enabled") else "🚫"
        label = f"{status} {ad['headline'][:30]}"
        kb.append([InlineKeyboardButton(label, callback_data=f"ba_view_{ad['id']}")])
    kb.append([InlineKeyboardButton("➕ Add New Big Ad", callback_data="ba_add")])
    kb.append([InlineKeyboardButton("🔙 Back", callback_data="adm_ads_settings")])
    return InlineKeyboardMarkup(kb)


def ba_manage_keyboard(ad_id):
    ad = storage.get_big_ad(ad_id)
    toggle_label = "🚫 Disable" if ad and ad.get("enabled") else "✅ Enable"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(toggle_label, callback_data=f"ba_toggle_{ad_id}")],
        [InlineKeyboardButton("🗑️ Delete", callback_data=f"ba_delete_{ad_id}")],
        [InlineKeyboardButton("🔙 Back", callback_data="ba_menu")],
    ])


# ═══════════════════════════════════════════════════════════════════
# ADD TEXT AD — conversation flow with preview
# ═══════════════════════════════════════════════════════════════════

async def ta_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["ad_draft"] = {}
    await query.message.edit_text(
        "➕ *New Text Ad*\n\n"
        "Send the ad text now.\n"
        "First line = headline, rest = body. Example:\n\n"
        "`🔥 Big Offer!`\n`Get 50% off today only.`",
        parse_mode="Markdown",
        reply_markup=cancel_kb("ta_menu")
    )
    return AD_AWAITING_TEXT


async def ad_receive_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw_text = update.message.text
    entities = update.message.entities
    styled = formatting.entities_to_markdownv2(raw_text, entities)

    lines = styled.split("\n", 1)
    headline = lines[0].strip()
    body = lines[1].strip() if len(lines) > 1 else ""
    context.user_data["ad_draft"]["headline"] = headline
    context.user_data["ad_draft"]["body"] = body

    await update.message.reply_text(
        "🖼️ *Attach a picture or video?*",
        parse_mode="Markdown",
        reply_markup=yes_no_kb("ad_media_yes", "ad_media_no", back_to="ta_menu")
    )
    return AD_AWAITING_MEDIA_CHOICE


async def ad_media_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "ad_media_yes":
        await query.message.edit_text(
            "Send the photo or video now.",
            reply_markup=cancel_kb("ta_menu")
        )
        return AD_AWAITING_MEDIA
    else:
        context.user_data["ad_draft"]["media_file_id"] = None
        context.user_data["ad_draft"]["media_type"] = None
        await query.message.edit_text(
            "Send the *button label*.\nExample: `Join Now`",
            parse_mode="Markdown",
            reply_markup=cancel_kb("ta_menu")
        )
        return AD_AWAITING_BUTTON_TEXT


async def ad_receive_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not (update.message.photo or update.message.video):
        await update.message.reply_text("⚠️ Please send a photo or video.")
        return AD_AWAITING_MEDIA

    file_id, media_type = await _archive_media_to_channel(context.bot, update.message)
    context.user_data["ad_draft"]["media_file_id"] = file_id
    context.user_data["ad_draft"]["media_type"] = media_type

    await update.message.reply_text(
        "Send the *button label*.\nExample: `Join Now`",
        parse_mode="Markdown",
        reply_markup=cancel_kb("ta_menu")
    )
    return AD_AWAITING_BUTTON_TEXT


async def ad_receive_button_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["ad_draft"]["button_text"] = update.message.text.strip()
    await update.message.reply_text(
        "Now send the *button URL*.\nMust start with http:// or https://",
        parse_mode="Markdown",
        reply_markup=cancel_kb("ta_menu")
    )
    return AD_AWAITING_BUTTON_URL


async def ad_receive_button_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        await update.message.reply_text("⚠️ Must start with http:// or https://. Try again.")
        return AD_AWAITING_BUTTON_URL
    context.user_data["ad_draft"]["button_url"] = url

    draft = context.user_data["ad_draft"]
    preview_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(draft["button_text"], url=draft["button_url"])],
    ])
    caption = render_ad_preview_text(draft)

    if draft.get("media_file_id"):
        if draft["media_type"] == "photo":
            await update.message.reply_photo(draft["media_file_id"], caption=caption,
                                              parse_mode="MarkdownV2", reply_markup=preview_kb)
        else:
            await update.message.reply_video(draft["media_file_id"], caption=caption,
                                              parse_mode="MarkdownV2", reply_markup=preview_kb)
    else:
        await update.message.reply_text(caption, parse_mode="MarkdownV2", reply_markup=preview_kb)

    await update.message.reply_text(
        "☝️ *This is the preview.*\n\nSave this ad?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💾 Save Ad", callback_data="ad_save")],
            [InlineKeyboardButton("❌ Cancel", callback_data="ta_menu")],
        ])
    )
    return AD_PREVIEW


async def ad_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    draft = context.user_data.get("ad_draft", {})
    await storage.add_text_ad(draft)
    context.user_data.clear()
    await query.message.edit_text("✅ Ad saved.")
    await context.bot.send_message(
        query.message.chat_id, "📋 *Text Ads (Pool)*", parse_mode="Markdown", reply_markup=ta_menu_keyboard()
    )
    return ConversationHandler.END


async def ad_cancel_to_ta_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    await query.message.edit_text(
        "📋 *Text Ads (Pool)*", parse_mode="Markdown", reply_markup=ta_menu_keyboard()
    )
    return ConversationHandler.END


# ── Text ad frequency editor ──

async def ta_freq_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.edit_text(
        f"⏱️ *Text Ads Frequency*\n\nCurrently: {storage.get_text_ads_frequency()} hour(s).\n\n"
        "Send the new cooldown in hours (e.g. `2`).",
        parse_mode="Markdown",
        reply_markup=cancel_kb("ta_menu")
    )
    return AD_AWAITING_FREQ_HOURS


async def ta_freq_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip()
    try:
        hours = float(raw)
        if hours <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("⚠️ Send a positive number, e.g. `2` or `0.5`.", parse_mode="Markdown")
        return AD_AWAITING_FREQ_HOURS

    await storage.set_text_ads_frequency(hours)
    await update.message.reply_text(f"✅ Text ads frequency set to {hours}h.")
    await update.message.reply_text(
        "📋 *Text Ads (Pool)*", parse_mode="Markdown", reply_markup=ta_menu_keyboard()
    )
    return ConversationHandler.END


# ═══════════════════════════════════════════════════════════════════
# ADD BIG AD — conversation flow with schedule pickers + preview
# ═══════════════════════════════════════════════════════════════════

async def ba_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["ad_draft"] = {}
    await query.message.edit_text(
        "➕ *New Big Ad*\n\n"
        "Send the ad text now.\n"
        "First line = headline, rest = body.",
        parse_mode="Markdown",
        reply_markup=cancel_kb("ba_menu")
    )
    return AD_AWAITING_TEXT


async def bigad_receive_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw_text = update.message.text
    entities = update.message.entities
    styled = formatting.entities_to_markdownv2(raw_text, entities)

    lines = styled.split("\n", 1)
    context.user_data["ad_draft"]["headline"] = lines[0].strip()
    context.user_data["ad_draft"]["body"] = lines[1].strip() if len(lines) > 1 else ""
    await update.message.reply_text(
        "🖼️ *Attach a picture or video?*",
        parse_mode="Markdown",
        reply_markup=yes_no_kb("bigad_media_yes", "bigad_media_no", back_to="ba_menu")
    )
    return AD_AWAITING_MEDIA_CHOICE


async def bigad_media_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "bigad_media_yes":
        await query.message.edit_text("Send the photo or video now.", reply_markup=cancel_kb("ba_menu"))
        return AD_AWAITING_MEDIA
    else:
        context.user_data["ad_draft"]["media_file_id"] = None
        context.user_data["ad_draft"]["media_type"] = None
        await query.message.edit_text(
            "Send the *button label*.", parse_mode="Markdown", reply_markup=cancel_kb("ba_menu")
        )
        return AD_AWAITING_BUTTON_TEXT


async def bigad_receive_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not (update.message.photo or update.message.video):
        await update.message.reply_text("⚠️ Please send a photo or video.")
        return AD_AWAITING_MEDIA

    file_id, media_type = await _archive_media_to_channel(context.bot, update.message)
    context.user_data["ad_draft"]["media_file_id"] = file_id
    context.user_data["ad_draft"]["media_type"] = media_type

    await update.message.reply_text(
        "Send the *button label*.", parse_mode="Markdown", reply_markup=cancel_kb("ba_menu")
    )
    return AD_AWAITING_BUTTON_TEXT


async def bigad_receive_button_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["ad_draft"]["button_text"] = update.message.text.strip()
    await update.message.reply_text(
        "Now send the *button URL*.", parse_mode="Markdown", reply_markup=cancel_kb("ba_menu")
    )
    return AD_AWAITING_BUTTON_URL


async def bigad_receive_button_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        await update.message.reply_text("⚠️ Must start with http:// or https://. Try again.")
        return AD_AWAITING_BUTTON_URL
    context.user_data["ad_draft"]["button_url"] = url

    await update.message.reply_text(
        "🗓️ *Repeat: Daily or Weekly?*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📅 Daily", callback_data="bigad_repeat_daily")],
            [InlineKeyboardButton("🗓️ Weekly", callback_data="bigad_repeat_weekly")],
            [InlineKeyboardButton("🔙 Cancel", callback_data="ba_menu")],
        ])
    )
    return BIGAD_AWAITING_REPEAT_TYPE


async def bigad_repeat_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "bigad_repeat_daily":
        context.user_data["ad_draft"]["schedule"] = {"type": "daily"}
        await query.message.edit_text("🕐 *Pick the hour (24h):*", parse_mode="Markdown", reply_markup=hour_picker_kb())
        return BIGAD_AWAITING_HOUR
    else:
        context.user_data["ad_draft"]["schedule"] = {"type": "weekly"}
        kb = [[InlineKeyboardButton(day, callback_data=f"bigad_wd_{i}")] for i, day in enumerate(WEEKDAY_NAMES)]
        kb.append([InlineKeyboardButton("🔙 Cancel", callback_data="ba_menu")])
        await query.message.edit_text("📅 *Pick the day:*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        return BIGAD_AWAITING_WEEKDAY


def hour_picker_kb():
    rows = []
    for start in range(0, 24, 6):
        rows.append([InlineKeyboardButton(f"{h:02d}", callback_data=f"bigad_hr_{h}") for h in range(start, start + 6)])
    rows.append([InlineKeyboardButton("🔙 Cancel", callback_data="ba_menu")])
    return InlineKeyboardMarkup(rows)


def minute_picker_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(":00", callback_data="bigad_min_0"),
         InlineKeyboardButton(":15", callback_data="bigad_min_15"),
         InlineKeyboardButton(":30", callback_data="bigad_min_30"),
         InlineKeyboardButton(":45", callback_data="bigad_min_45")],
        [InlineKeyboardButton("🔙 Cancel", callback_data="ba_menu")],
    ])


async def bigad_weekday_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    weekday = int(query.data.replace("bigad_wd_", ""))
    context.user_data["ad_draft"]["schedule"]["weekday"] = weekday
    await query.message.edit_text("🕐 *Pick the hour (24h):*", parse_mode="Markdown", reply_markup=hour_picker_kb())
    return BIGAD_AWAITING_HOUR


async def bigad_hour_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    hour = int(query.data.replace("bigad_hr_", ""))
    context.user_data["ad_draft"]["schedule"]["hour"] = hour
    await query.message.edit_text("🕐 *Pick the minute:*", parse_mode="Markdown", reply_markup=minute_picker_kb())
    return BIGAD_AWAITING_MINUTE


async def bigad_minute_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    minute = int(query.data.replace("bigad_min_", ""))
    draft = context.user_data["ad_draft"]
    draft["schedule"]["minute"] = minute

    sched = draft["schedule"]
    if sched["type"] == "daily":
        sched_desc = f"Daily at {sched['hour']:02d}:{sched['minute']:02d}"
    else:
        sched_desc = f"Weekly on {WEEKDAY_NAMES[sched['weekday']]} at {sched['hour']:02d}:{sched['minute']:02d}"

    preview_kb = InlineKeyboardMarkup([[InlineKeyboardButton(draft["button_text"], url=draft["button_url"])]])
    caption = render_ad_preview_text(draft) + f"\n\n🗓️ {formatting._escape(sched_desc)}"

    if draft.get("media_file_id"):
        if draft["media_type"] == "photo":
            await query.message.reply_photo(draft["media_file_id"], caption=caption,
                                             parse_mode="MarkdownV2", reply_markup=preview_kb)
        else:
            await query.message.reply_video(draft["media_file_id"], caption=caption,
                                             parse_mode="MarkdownV2", reply_markup=preview_kb)
    else:
        await query.message.reply_text(caption, parse_mode="MarkdownV2", reply_markup=preview_kb)

    await query.message.reply_text(
        "☝️ *This is the preview.*\n\nSave this Big Ad?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💾 Save Big Ad", callback_data="bigad_save")],
            [InlineKeyboardButton("❌ Cancel", callback_data="ba_menu")],
        ])
    )
    return AD_PREVIEW


async def bigad_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    draft = context.user_data.get("ad_draft", {})
    await storage.add_big_ad(draft)
    context.user_data.clear()
    await query.message.edit_text("✅ Big Ad saved and scheduled.")
    await context.bot.send_message(
        query.message.chat_id, "🎯 *Big Ads (Scheduled)*", parse_mode="Markdown", reply_markup=ba_menu_keyboard()
    )
    return ConversationHandler.END


async def bigad_cancel_to_ba_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    await query.message.edit_text("🎯 *Big Ads (Scheduled)*", parse_mode="Markdown", reply_markup=ba_menu_keyboard())
    return ConversationHandler.END


# ── Gateway frequency editor ──

async def gw_edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.edit_text(
        f"🌐 *Gateway Frequency*\n\nCurrently: every {storage.get_gateway_frequency()}th conversion.\n\n"
        "Send the new number (e.g. `5` means every 5th comic goes through the ad gateway).",
        parse_mode="Markdown",
        reply_markup=cancel_kb("adm_ads_settings")
    )
    return GW_AWAITING_FREQ


async def gw_receive_freq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip()
    try:
        n = int(raw)
        if n <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("⚠️ Send a positive whole number, e.g. `5`.")
        return GW_AWAITING_FREQ

    await storage.set_gateway_frequency(n)
    await update.message.reply_text(f"✅ Gateway frequency set to every {n}th conversion.")
    await update.message.reply_text(
        "📝 *Ads Settings*", parse_mode="Markdown", reply_markup=ads_settings_menu_keyboard()
    )
    return ConversationHandler.END


# ═══════════════════════════════════════════════════════════════════
# Conversation handler builders (called from main.py, needs admin_ids for auth)
# ═══════════════════════════════════════════════════════════════════

def build_text_ad_conversation():
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(ta_add_start, pattern="^ta_add$")],
        states={
            AD_AWAITING_TEXT: [
                CallbackQueryHandler(ad_cancel_to_ta_menu, pattern="^ta_menu$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, ad_receive_text),
            ],
            AD_AWAITING_MEDIA_CHOICE: [
                CallbackQueryHandler(ad_cancel_to_ta_menu, pattern="^ta_menu$"),
                CallbackQueryHandler(ad_media_choice, pattern="^ad_media_(yes|no)$"),
            ],
            AD_AWAITING_MEDIA: [
                CallbackQueryHandler(ad_cancel_to_ta_menu, pattern="^ta_menu$"),
                MessageHandler(filters.PHOTO | filters.VIDEO, ad_receive_media),
            ],
            AD_AWAITING_BUTTON_TEXT: [
                CallbackQueryHandler(ad_cancel_to_ta_menu, pattern="^ta_menu$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, ad_receive_button_text),
            ],
            AD_AWAITING_BUTTON_URL: [
                CallbackQueryHandler(ad_cancel_to_ta_menu, pattern="^ta_menu$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, ad_receive_button_url),
            ],
            AD_PREVIEW: [
                CallbackQueryHandler(ad_cancel_to_ta_menu, pattern="^ta_menu$"),
                CallbackQueryHandler(ad_save, pattern="^ad_save$"),
            ],
        },
        fallbacks=[CallbackQueryHandler(ad_cancel_to_ta_menu, pattern="^ta_menu$")],
        per_message=False,
    )


def build_text_ad_freq_conversation():
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(ta_freq_start, pattern="^ta_freq$")],
        states={
            AD_AWAITING_FREQ_HOURS: [
                CallbackQueryHandler(ad_cancel_to_ta_menu, pattern="^ta_menu$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, ta_freq_receive),
            ],
        },
        fallbacks=[CallbackQueryHandler(ad_cancel_to_ta_menu, pattern="^ta_menu$")],
        per_message=False,
    )


def build_big_ad_conversation():
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(ba_add_start, pattern="^ba_add$")],
        states={
            AD_AWAITING_TEXT: [
                CallbackQueryHandler(bigad_cancel_to_ba_menu, pattern="^ba_menu$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, bigad_receive_text),
            ],
            AD_AWAITING_MEDIA_CHOICE: [
                CallbackQueryHandler(bigad_cancel_to_ba_menu, pattern="^ba_menu$"),
                CallbackQueryHandler(bigad_media_choice, pattern="^bigad_media_(yes|no)$"),
            ],
            AD_AWAITING_MEDIA: [
                CallbackQueryHandler(bigad_cancel_to_ba_menu, pattern="^ba_menu$"),
                MessageHandler(filters.PHOTO | filters.VIDEO, bigad_receive_media),
            ],
            AD_AWAITING_BUTTON_TEXT: [
                CallbackQueryHandler(bigad_cancel_to_ba_menu, pattern="^ba_menu$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, bigad_receive_button_text),
            ],
            AD_AWAITING_BUTTON_URL: [
                CallbackQueryHandler(bigad_cancel_to_ba_menu, pattern="^ba_menu$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, bigad_receive_button_url),
            ],
            BIGAD_AWAITING_REPEAT_TYPE: [
                CallbackQueryHandler(bigad_cancel_to_ba_menu, pattern="^ba_menu$"),
                CallbackQueryHandler(bigad_repeat_choice, pattern="^bigad_repeat_(daily|weekly)$"),
            ],
            BIGAD_AWAITING_WEEKDAY: [
                CallbackQueryHandler(bigad_cancel_to_ba_menu, pattern="^ba_menu$"),
                CallbackQueryHandler(bigad_weekday_choice, pattern="^bigad_wd_\\d$"),
            ],
            BIGAD_AWAITING_HOUR: [
                CallbackQueryHandler(bigad_cancel_to_ba_menu, pattern="^ba_menu$"),
                CallbackQueryHandler(bigad_hour_choice, pattern="^bigad_hr_\\d+$"),
            ],
            BIGAD_AWAITING_MINUTE: [
                CallbackQueryHandler(bigad_cancel_to_ba_menu, pattern="^ba_menu$"),
                CallbackQueryHandler(bigad_minute_choice, pattern="^bigad_min_\\d+$"),
            ],
            AD_PREVIEW: [
                CallbackQueryHandler(bigad_cancel_to_ba_menu, pattern="^ba_menu$"),
                CallbackQueryHandler(bigad_save, pattern="^bigad_save$"),
            ],
        },
        fallbacks=[CallbackQueryHandler(bigad_cancel_to_ba_menu, pattern="^ba_menu$")],
        per_message=False,
    )


def build_gateway_freq_conversation():
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(gw_edit_start, pattern="^gw_edit$")],
        states={
            GW_AWAITING_FREQ: [
                CallbackQueryHandler(lambda u, c: gw_cancel(u, c), pattern="^adm_ads_settings$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, gw_receive_freq),
            ],
        },
        fallbacks=[CallbackQueryHandler(lambda u, c: gw_cancel(u, c), pattern="^adm_ads_settings$")],
        per_message=False,
    )


async def gw_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    await query.message.edit_text(
        "📝 *Ads Settings*", parse_mode="Markdown", reply_markup=ads_settings_menu_keyboard()
    )
    return ConversationHandler.END


# ═══════════════════════════════════════════════════════════════════
# Big Ad scheduler loop — checks every 60s for due recurring campaigns
# ═══════════════════════════════════════════════════════════════════

async def big_ad_scheduler_loop(bot, get_user_ids_fn, click_base_url):
    while True:
        try:
            due = storage.get_due_big_ads()
            for ad in due:
                target_ids = get_user_ids_fn()
                ad_id = ad["id"]
                tracked_url = f"{click_base_url}/bigadclick/{ad_id}?url={ad['button_url']}" if ad.get("button_url") else None
                reply_markup = (
                    InlineKeyboardMarkup([[InlineKeyboardButton(ad["button_text"], url=tracked_url)]])
                    if tracked_url else None
                )
                caption = render_ad_preview_text(ad)

                sent, failed = 0, 0
                for uid in target_ids:
                    try:
                        if ad.get("media_file_id"):
                            if ad["media_type"] == "photo":
                                await bot.send_photo(uid, ad["media_file_id"], caption=caption,
                                                      parse_mode="MarkdownV2", reply_markup=reply_markup)
                            else:
                                await bot.send_video(uid, ad["media_file_id"], caption=caption,
                                                      parse_mode="MarkdownV2", reply_markup=reply_markup)
                        else:
                            await bot.send_message(uid, caption, parse_mode="MarkdownV2", reply_markup=reply_markup)
                        sent += 1
                    except Exception:
                        failed += 1
                    await asyncio.sleep(0.05)

                await storage.mark_big_ad_ran(ad_id, sent, failed)
        except Exception as e:
            print(f"[big_ad_scheduler] Error: {e}")

        await asyncio.sleep(60)
