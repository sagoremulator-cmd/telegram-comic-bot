import time
import random
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# Track last ad time per user (in memory only)
LAST_AD_TIME = {}

# Ads list — add as many entries as you want
ADS = [
    {
        "headline": "*#Ads PR GRAM Promote Anything*",
        "body": "Get Members for your Channel/Group/Bot For Free",
        "cta": {"label": "Join Now", "url": "https://t.me/gram_piarbot?start=5083713667"}
    },
    {
        "headline": "*#Ads Inside Ads Monetize Telegram Channel*",
        "body": "Highest Paying Monetization Service In Telegram",
        "cta": {"label": "Monetize Now", "url": "https://t.me/InsideAds_bot/open?startapp=r_5083713667"}
    },
    {
        "headline": "*#Ads Bitget Official *",
        "body": "💰Get up to 500USDT welcome pack on your first launch and Enjoy 50% off transaction fees!",
        "cta": {"label": "Join Now", "url": "https://t.me/BitgetOfficialBot/Bitget?startapp=JwnaGhlngUX3oFNY1AUuJHFa38jeKvF"}
    }
]

def get_ads_keyboard(ad):
    """Return keyboard with CTA button only"""
    return InlineKeyboardMarkup([[InlineKeyboardButton(ad["cta"]["label"], url=ad["cta"]["url"])]])

async def maybe_show_ads(update):
    """Show ads only if 6 hours passed since last ad for this user"""
    user_id = update.effective_user.id
    now = time.time()
    last_time = LAST_AD_TIME.get(user_id, 0)

    # 6 hours = 21600 seconds
    if now - last_time >= 21600:
        ad = random.choice(ADS)  # pick random ad
        await update.message.reply_text(
            f"{ad['headline']}\n{ad['body']}",
            reply_markup=get_ads_keyboard(ad),
            parse_mode="Markdown",
            protect_content=True
        )
        LAST_AD_TIME[user_id] = now
