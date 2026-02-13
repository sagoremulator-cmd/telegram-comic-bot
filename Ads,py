import time
import random
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

LAST_AD_TIME = {}  # track last ad shown per user

ADS = [
    {
        "headline": "*#Ads PR GRAM Promote Anything *",
        "body": "Get Members for your Channel/Group/Bot For Free",
        "cta": {"label": "Join Now", "url": "https://t.me/gram_piarbot?start=5083713667"}
    },
    {
        "headline": "*#Ads Another Sponsor*",
        "body": "CoolBot Best Deals Right Now",
        "cta": {"label": "Join Now", "url": "https://example.com"}
    }
]

def get_ads_keyboard(ad):
    return InlineKeyboardMarkup([[InlineKeyboardButton(ad["cta"]["label"], url=ad["cta"]["url"])]])

async def maybe_show_ads(update):
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
