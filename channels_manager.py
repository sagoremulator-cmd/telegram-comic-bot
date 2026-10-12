"""
Admin UI + conversation flow for managing mandatory ("join to use the bot") channels.
Same Gist-backed pattern as ads: Add / Edit fields / Remove, all persisted via storage.py.
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler

import storage

(
    CH_AWAITING_NAME,
    CH_AWAITING_USERNAME,
    CH_AWAITING_LINK,
    CH_AWAITING_EMOJI,
    CH_AWAITING_DURATION,
) = range(5)


def channels_menu_keyboard():
    channels = storage.get_all_required_channels()
    kb = []
    for ch in channels:
        emoji = ch.get("emoji") or "📌"
        kb.append([InlineKeyboardButton(f"{emoji} {ch['display_name']}", callback_data=f"ch_view_{ch['id']}")])
    kb.append([InlineKeyboardButton("➕ Add Channel", callback_data="ch_add")])
    kb.append([InlineKeyboardButton("⏱️ Mandatory Mode", callback_data="ch_mode_menu")])
    kb.append([InlineKeyboardButton("🔙 Back", callback_data="adm_root")])
    return InlineKeyboardMarkup(kb)


def mode_menu_text():
    mode = storage.get_mandatory_mode()
    duration = storage.get_mandatory_duration()
    mode_label = "🔒 Normal (wall immediately)" if mode == "normal" else f"⏱️ Duration ({duration} free comics)"
    return (
        "⏱️ *Mandatory Subscription Mode*\n\n"
        f"Current mode: *{mode_label}*\n\n"
        "• *Normal* — users must join all channels before using the bot at all (today's default).\n"
        "• *Duration* — new users can convert a set number of comics for free, "
        "then they're walled exactly like Normal mode until they join.\n\n"
        "Switching modes takes effect immediately and never removes your channel list."
    )


def mode_menu_keyboard():
    mode = storage.get_mandatory_mode()
    kb = []
    if mode == "normal":
        kb.append([InlineKeyboardButton("▶️ Switch to Duration Mode", callback_data="ch_mode_set_duration")])
    else:
        kb.append([InlineKeyboardButton("◀️ Switch back to Normal Mode", callback_data="ch_mode_set_normal")])
        kb.append([InlineKeyboardButton("✏️ Edit Free-Comic Count", callback_data="ch_mode_edit_duration")])
    kb.append([InlineKeyboardButton("🔙 Back", callback_data="ch_menu")])
    return InlineKeyboardMarkup(kb)


def channel_manage_keyboard(channel_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑️ Remove", callback_data=f"ch_remove_{channel_id}")],
        [InlineKeyboardButton("🔙 Back", callback_data="ch_menu")],
    ])


def cancel_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="ch_menu")]])


async def channels_router(update: Update, context: ContextTypes.DEFAULT_TYPE, admin_ids):
    query = update.callback_query
    if query.from_user.id not in admin_ids:
        await query.answer("Not authorized.", show_alert=True)
        return
    await query.answer()
    data = query.data

    if data == "ch_menu":
        await query.message.edit_text(
            "📢 *Mandatory Channels*\n\nUsers must join all of these to use the bot.\nTap one to manage it.",
            parse_mode="Markdown", reply_markup=channels_menu_keyboard()
        )

    elif data.startswith("ch_view_"):
        channel_id = data.replace("ch_view_", "")
        ch = storage.get_required_channel(channel_id)
        if not ch:
            await query.message.edit_text("Channel not found (maybe removed).", reply_markup=channels_menu_keyboard())
            return
        username_desc = f"@{ch['username']}" if ch.get("username") else "(none — can't auto-verify membership)"
        text = (
            f"{ch.get('emoji') or '📌'} *{ch['display_name']}*\n\n"
            f"Username: {username_desc}\n"
            f"Invite link: {ch['invite_link']}"
        )
        await query.message.edit_text(text, parse_mode="Markdown", reply_markup=channel_manage_keyboard(channel_id))

    elif data.startswith("ch_remove_"):
        channel_id = data.replace("ch_remove_", "")
        await storage.remove_required_channel(channel_id)
        await query.answer("Removed.", show_alert=False)
        await query.message.edit_text(
            "📢 *Mandatory Channels*", parse_mode="Markdown", reply_markup=channels_menu_keyboard()
        )

    elif data == "ch_mode_menu":
        await query.message.edit_text(
            mode_menu_text(), parse_mode="Markdown", reply_markup=mode_menu_keyboard()
        )

    elif data == "ch_mode_set_duration":
        await storage.set_mandatory_mode("duration")
        await query.answer("Switched to Duration mode.", show_alert=False)
        await query.message.edit_text(
            mode_menu_text(), parse_mode="Markdown", reply_markup=mode_menu_keyboard()
        )

    elif data == "ch_mode_set_normal":
        await storage.set_mandatory_mode("normal")
        await query.answer("Switched back to Normal mode.", show_alert=False)
        await query.message.edit_text(
            mode_menu_text(), parse_mode="Markdown", reply_markup=mode_menu_keyboard()
        )


async def ch_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["channel_draft"] = {}
    await query.message.edit_text(
        "➕ *Add Mandatory Channel*\n\nSend the display name (shown to users on the join button).\n"
        "Example: `Arc Comics`",
        parse_mode="Markdown",
        reply_markup=cancel_kb()
    )
    return CH_AWAITING_NAME


async def ch_receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["channel_draft"]["display_name"] = update.message.text.strip()
    await update.message.reply_text(
        "Send the channel's public *@username* (without the @), so the bot can verify "
        "membership automatically.\n\n"
        "If it's a private channel with no public username, send `none` — but note: "
        "the bot won't be able to auto-check membership for it, so the join button "
        "will show but verification will be skipped for this channel.",
        parse_mode="Markdown",
        reply_markup=cancel_kb()
    )
    return CH_AWAITING_USERNAME


async def ch_receive_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip().lstrip("@")
    context.user_data["channel_draft"]["username"] = None if raw.lower() == "none" else raw
    await update.message.reply_text(
        "Now send the *invite link* users will tap to join.\nExample: `https://t.me/+AbCdEfGhIjK`",
        parse_mode="Markdown",
        reply_markup=cancel_kb()
    )
    return CH_AWAITING_LINK


async def ch_receive_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        await update.message.reply_text("⚠️ Must start with http:// or https://. Try again.")
        return CH_AWAITING_LINK
    context.user_data["channel_draft"]["invite_link"] = url
    await update.message.reply_text(
        "Send an emoji to show next to this channel's name (or send `skip` to use the default 📌).",
        reply_markup=cancel_kb()
    )
    return CH_AWAITING_EMOJI


async def ch_receive_emoji(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip()
    emoji = None if raw.lower() == "skip" else raw
    draft = context.user_data["channel_draft"]
    draft["emoji"] = emoji or "📌"

    await storage.add_required_channel(draft)
    context.user_data.clear()

    await update.message.reply_text(f"✅ Channel added: {draft['emoji']} {draft['display_name']}")
    await update.message.reply_text(
        "📢 *Mandatory Channels*", parse_mode="Markdown", reply_markup=channels_menu_keyboard()
    )
    return ConversationHandler.END


async def ch_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    await query.message.edit_text(
        "📢 *Mandatory Channels*", parse_mode="Markdown", reply_markup=channels_menu_keyboard()
    )
    return ConversationHandler.END


async def ch_mode_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    await query.message.edit_text(
        mode_menu_text(), parse_mode="Markdown", reply_markup=mode_menu_keyboard()
    )
    return ConversationHandler.END


async def ch_mode_edit_duration_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    current = storage.get_mandatory_duration()
    await query.message.edit_text(
        f"✏️ *Edit Free-Comic Count*\n\nCurrent: *{current}* free comics before the wall.\n\n"
        "Send the new number.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="ch_mode_menu")]])
    )
    return CH_AWAITING_DURATION


async def ch_mode_receive_duration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip()
    if not raw.isdigit() or int(raw) < 1:
        await update.message.reply_text("⚠️ Send a whole number, 1 or higher.")
        return CH_AWAITING_DURATION
    await storage.set_mandatory_duration(int(raw))
    await update.message.reply_text(f"✅ Free-comic count set to {raw}.")
    await update.message.reply_text(
        mode_menu_text(), parse_mode="Markdown", reply_markup=mode_menu_keyboard()
    )
    return ConversationHandler.END


def build_channel_conversation():
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(ch_add_start, pattern="^ch_add$"),
            CallbackQueryHandler(ch_mode_edit_duration_start, pattern="^ch_mode_edit_duration$"),
        ],
        states={
            CH_AWAITING_NAME: [
                CallbackQueryHandler(ch_cancel, pattern="^ch_menu$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, ch_receive_name),
            ],
            CH_AWAITING_USERNAME: [
                CallbackQueryHandler(ch_cancel, pattern="^ch_menu$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, ch_receive_username),
            ],
            CH_AWAITING_LINK: [
                CallbackQueryHandler(ch_cancel, pattern="^ch_menu$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, ch_receive_link),
            ],
            CH_AWAITING_EMOJI: [
                CallbackQueryHandler(ch_cancel, pattern="^ch_menu$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, ch_receive_emoji),
            ],
            CH_AWAITING_DURATION: [
                CallbackQueryHandler(ch_mode_cancel, pattern="^ch_mode_menu$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, ch_mode_receive_duration),
            ],
        },
        fallbacks=[CallbackQueryHandler(ch_cancel, pattern="^ch_menu$")],
        per_message=False,
    )
