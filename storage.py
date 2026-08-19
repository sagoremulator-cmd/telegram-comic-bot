"""
Persistent user storage backed by a private GitHub Gist.

Why a Gist: Render's free-tier disk is wiped on every redeploy, so anything
written to local disk (a plain JSON file) does NOT survive a `git push`.
A Gist lives on GitHub's servers, completely separate from Render, so it
survives redeploys, restarts, and sleep/wake cycles forever.

Data captured per user (only what Telegram's Bot API actually exposes —
phone numbers and emails are NOT accessible to bots, ever, by any means):
    - user_id        (always present)
    - first_name     (always present)
    - last_name      (present if the user has one set)
    - username       (present if the user has one set, e.g. @something)
    - language_code  (their Telegram app language, e.g. "en")
    - joined         (ISO timestamp of when we first saw them)
"""

import os
import json
import time
import httpx

GITHUB_TOKEN = os.getenv("GIST_TOKEN")
GIST_ID = os.getenv("GIST_ID")
GIST_FILENAME = "users.json"

GITHUB_API = f"https://api.github.com/gists/{GIST_ID}"
HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
}

# In-memory cache: {user_id: {first_name, last_name, username, language_code, joined}}
USERS_CACHE = {}

# In-memory cache of view events: [{"user_id": int, "ts": "YYYY-MM-DD HH:MM:SS"}, ...]
GATEWAY_VIEWS = []
TEXT_AD_VIEWS = []

# Broadcast history: [{"id": str, "sent": int, "failed": int, "clicks": int,
#                       "ts": "YYYY-MM-DD HH:MM:SS", "preview": str}, ...]
BROADCAST_HISTORY = []

# Scheduled (not-yet-sent) broadcasts:
# [{"id": str, "run_at": "YYYY-MM-DD HH:MM:SS", "target": "all"|list[int],
#   "text": str|None, "photo_file_id": str|None, "caption": str|None,
#   "button_text": str|None, "button_url": str|None}, ...]
SCHEDULED_BROADCASTS = []

# Click events: [{"broadcast_id": str, "user_id": int, "ts": "..."}]
CLICK_EVENTS = []

# ── "Ads.py-style" pool ads: shown to users on a per-user cooldown ──
# TEXT_ADS: [{"id", "headline", "body", "media_file_id", "media_type" ("photo"|"video"|None),
#             "button_text", "button_url", "enabled", "created"}, ...]
TEXT_ADS = []
TEXT_ADS_FREQUENCY_HOURS = 1  # global cooldown for this whole pool, admin-editable

# Per-user cooldown tracking for the text ads pool: {user_id: last_shown_ts (float)}
TEXT_ADS_LAST_SHOWN = {}

# ── "Big Ads": individually scheduled recurring campaigns ──
# BIG_ADS: [{"id", "headline", "body", "media_file_id", "media_type", "button_text", "button_url",
#            "enabled", "schedule": {"type": "daily"|"weekly", "hour": int, "minute": int,
#            "weekday": int|None (0=Mon..6=Sun, only for weekly)}, "last_run": "YYYY-MM-DD HH:MM"|None,
#            "created"}, ...]
BIG_ADS = []

# Big ad stats: sends and clicks, similar shape to broadcast history
# BIG_AD_SENDS: [{"big_ad_id", "ts", "sent", "failed"}]
BIG_AD_SENDS = []
# BIG_AD_CLICKS: [{"big_ad_id", "ts"}]
BIG_AD_CLICKS = []

# ── Gateway ads (GitHub landing page) frequency: every Nth comic conversion ──
GATEWAY_FREQUENCY = 5  # admin-editable, default matches current hardcoded behavior


async def load_users():
    """Fetch the current user list + all logs from the Gist into memory. Call once at startup."""
    global USERS_CACHE, GATEWAY_VIEWS, TEXT_AD_VIEWS
    global BROADCAST_HISTORY, SCHEDULED_BROADCASTS, CLICK_EVENTS
    global TEXT_ADS, TEXT_ADS_FREQUENCY_HOURS, TEXT_ADS_LAST_SHOWN
    global BIG_ADS, BIG_AD_SENDS, BIG_AD_CLICKS, GATEWAY_FREQUENCY
    async with httpx.AsyncClient() as client:
        resp = await client.get(GITHUB_API, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        content = data["files"][GIST_FILENAME]["content"]
        parsed = json.loads(content)
        USERS_CACHE = {int(uid): info for uid, info in parsed.get("users", {}).items()}
        GATEWAY_VIEWS = parsed.get("gateway_views", [])
        TEXT_AD_VIEWS = parsed.get("text_ad_views", [])
        BROADCAST_HISTORY = parsed.get("broadcast_history", [])
        SCHEDULED_BROADCASTS = parsed.get("scheduled_broadcasts", [])
        CLICK_EVENTS = parsed.get("click_events", [])
        TEXT_ADS = parsed.get("text_ads", [])
        TEXT_ADS_FREQUENCY_HOURS = parsed.get("text_ads_frequency_hours", 1)
        TEXT_ADS_LAST_SHOWN = {int(uid): ts for uid, ts in parsed.get("text_ads_last_shown", {}).items()}
        BIG_ADS = parsed.get("big_ads", [])
        BIG_AD_SENDS = parsed.get("big_ad_sends", [])
        BIG_AD_CLICKS = parsed.get("big_ad_clicks", [])
        GATEWAY_FREQUENCY = parsed.get("gateway_frequency", 5)
    print(f"[storage] Loaded {len(USERS_CACHE)} users, "
          f"{len(GATEWAY_VIEWS)} gateway views, {len(TEXT_AD_VIEWS)} text ad views, "
          f"{len(BROADCAST_HISTORY)} past broadcasts, {len(SCHEDULED_BROADCASTS)} scheduled, "
          f"{len(CLICK_EVENTS)} clicks, {len(TEXT_ADS)} text ads, {len(BIG_ADS)} big ads from Gist.")
    return USERS_CACHE


async def _save_all():
    """Push the current in-memory state back to the Gist."""
    payload = {
        "files": {
            GIST_FILENAME: {
                "content": json.dumps({
                    "users": USERS_CACHE,
                    "gateway_views": GATEWAY_VIEWS,
                    "text_ad_views": TEXT_AD_VIEWS,
                    "broadcast_history": BROADCAST_HISTORY,
                    "scheduled_broadcasts": SCHEDULED_BROADCASTS,
                    "click_events": CLICK_EVENTS,
                    "text_ads": TEXT_ADS,
                    "text_ads_frequency_hours": TEXT_ADS_FREQUENCY_HOURS,
                    "text_ads_last_shown": TEXT_ADS_LAST_SHOWN,
                    "big_ads": BIG_ADS,
                    "big_ad_sends": BIG_AD_SENDS,
                    "big_ad_clicks": BIG_AD_CLICKS,
                    "gateway_frequency": GATEWAY_FREQUENCY,
                }, indent=2)
            }
        }
    }
    async with httpx.AsyncClient() as client:
        resp = await client.patch(GITHUB_API, headers=HEADERS, json=payload, timeout=15)
        resp.raise_for_status()


async def register_user(tg_user):
    """
    Record (or update) a user's public profile info.
    Call this on every incoming message/command, cheap no-op if nothing changed.
    tg_user is a telegram.User object (update.effective_user).
    """
    user_id = tg_user.id
    existing = USERS_CACHE.get(user_id)

    new_info = {
        "first_name": tg_user.first_name or "",
        "last_name": tg_user.last_name or "",
        "username": tg_user.username or "",
        "language_code": tg_user.language_code or "",
        "joined": existing["joined"] if existing else time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    if existing == new_info:
        return  # nothing changed, skip the write

    USERS_CACHE[user_id] = new_info
    try:
        await _save_all()
    except Exception as e:
        print(f"[storage] Failed to save to Gist: {e}")


def get_all_user_ids():
    return list(USERS_CACHE.keys())


def get_user_count():
    return len(USERS_CACHE)


def get_display_name(user_id):
    """Best-effort name for {name} placeholder in broadcasts."""
    info = USERS_CACHE.get(user_id)
    if not info:
        return "there"
    return info.get("first_name") or "there"


async def log_gateway_view(user_id):
    """Call every time a user is sent the GitHub landing page (Mondiad ads gateway)."""
    GATEWAY_VIEWS.append({"user_id": user_id, "ts": time.strftime("%Y-%m-%d %H:%M:%S")})
    try:
        await _save_all()
    except Exception as e:
        print(f"[storage] Failed to save gateway view: {e}")


async def log_text_ad_view(user_id):
    """Call every time a text/referral ad is actually shown to a user (Ads.py)."""
    TEXT_AD_VIEWS.append({"user_id": user_id, "ts": time.strftime("%Y-%m-%d %H:%M:%S")})
    try:
        await _save_all()
    except Exception as e:
        print(f"[storage] Failed to save text ad view: {e}")


def _count_views(events, period):
    """period: 'today' | 'month' | 'total'"""
    if period == "total":
        return len(events)
    now = time.localtime()
    count = 0
    for e in events:
        try:
            ts = time.strptime(e["ts"], "%Y-%m-%d %H:%M:%S")
        except (KeyError, ValueError):
            continue
        if period == "today":
            if ts.tm_year == now.tm_year and ts.tm_yday == now.tm_yday:
                count += 1
        elif period == "month":
            if ts.tm_year == now.tm_year and ts.tm_mon == now.tm_mon:
                count += 1
    return count


def get_gateway_stats():
    return {
        "today": _count_views(GATEWAY_VIEWS, "today"),
        "month": _count_views(GATEWAY_VIEWS, "month"),
        "total": _count_views(GATEWAY_VIEWS, "total"),
    }


def get_text_ad_stats():
    return {
        "today": _count_views(TEXT_AD_VIEWS, "today"),
        "month": _count_views(TEXT_AD_VIEWS, "month"),
        "total": _count_views(TEXT_AD_VIEWS, "total"),
    }


# ── Broadcast history + click tracking ──

async def record_broadcast_result(broadcast_id, sent, failed, preview):
    """Call after a broadcast finishes sending, to log it in history."""
    BROADCAST_HISTORY.append({
        "id": broadcast_id,
        "sent": sent,
        "failed": failed,
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "preview": preview[:80],  # keep it short
    })
    try:
        await _save_all()
    except Exception as e:
        print(f"[storage] Failed to save broadcast history: {e}")


async def log_click(broadcast_id, user_id):
    """Call when a user taps a tracked broadcast button link."""
    CLICK_EVENTS.append({
        "broadcast_id": broadcast_id,
        "user_id": user_id,
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
    })
    try:
        await _save_all()
    except Exception as e:
        print(f"[storage] Failed to save click event: {e}")


def get_click_count(broadcast_id):
    return sum(1 for c in CLICK_EVENTS if c["broadcast_id"] == broadcast_id)


def get_recent_broadcasts(limit=10):
    """Most recent broadcasts first, each with live click count attached."""
    recent = list(reversed(BROADCAST_HISTORY[-limit:]))
    for b in recent:
        b["clicks"] = get_click_count(b["id"])
    return recent


# ── Scheduled broadcasts ──

async def add_scheduled_broadcast(entry):
    """entry is a dict, see SCHEDULED_BROADCASTS docstring at top of file."""
    SCHEDULED_BROADCASTS.append(entry)
    try:
        await _save_all()
    except Exception as e:
        print(f"[storage] Failed to save scheduled broadcast: {e}")


async def remove_scheduled_broadcast(broadcast_id):
    global SCHEDULED_BROADCASTS
    SCHEDULED_BROADCASTS = [b for b in SCHEDULED_BROADCASTS if b["id"] != broadcast_id]
    try:
        await _save_all()
    except Exception as e:
        print(f"[storage] Failed to remove scheduled broadcast: {e}")


def get_due_scheduled_broadcasts():
    """Returns scheduled broadcasts whose run_at time has passed."""
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    return [b for b in SCHEDULED_BROADCASTS if b["run_at"] <= now]


def get_pending_scheduled_broadcasts():
    return list(SCHEDULED_BROADCASTS)


# ── Text Ads (Ads.py-style pool, per-user global cooldown) ──

async def add_text_ad(ad):
    """ad: dict with headline, body, media_file_id, media_type, button_text, button_url"""
    ad["id"] = ad.get("id") or _new_id()
    ad["enabled"] = True
    ad["created"] = time.strftime("%Y-%m-%d %H:%M:%S")
    TEXT_ADS.append(ad)
    await _save_all()
    return ad["id"]


async def update_text_ad(ad_id, **fields):
    for ad in TEXT_ADS:
        if ad["id"] == ad_id:
            ad.update(fields)
            await _save_all()
            return True
    return False


async def delete_text_ad(ad_id):
    global TEXT_ADS
    TEXT_ADS = [a for a in TEXT_ADS if a["id"] != ad_id]
    await _save_all()


async def toggle_text_ad(ad_id):
    for ad in TEXT_ADS:
        if ad["id"] == ad_id:
            ad["enabled"] = not ad["enabled"]
            await _save_all()
            return ad["enabled"]
    return None


def get_text_ad(ad_id):
    for ad in TEXT_ADS:
        if ad["id"] == ad_id:
            return ad
    return None


def get_all_text_ads():
    return list(TEXT_ADS)


async def set_text_ads_frequency(hours):
    global TEXT_ADS_FREQUENCY_HOURS
    TEXT_ADS_FREQUENCY_HOURS = hours
    await _save_all()


def get_text_ads_frequency():
    return TEXT_ADS_FREQUENCY_HOURS


def pick_text_ad_for_user(user_id):
    """Returns an enabled ad if the user's pool cooldown has passed, else None."""
    import random
    enabled = [a for a in TEXT_ADS if a.get("enabled")]
    if not enabled:
        return None
    last_shown = TEXT_ADS_LAST_SHOWN.get(user_id, 0)
    if time.time() - last_shown < TEXT_ADS_FREQUENCY_HOURS * 3600:
        return None
    return random.choice(enabled)


async def mark_text_ad_shown(user_id):
    TEXT_ADS_LAST_SHOWN[user_id] = time.time()
    await _save_all()


# ── Big Ads (individually scheduled recurring campaigns) ──

def _new_id():
    import uuid
    return uuid.uuid4().hex[:10]


async def add_big_ad(ad):
    """ad: dict with headline, body, media_file_id, media_type, button_text, button_url, schedule"""
    ad["id"] = ad.get("id") or _new_id()
    ad["enabled"] = True
    ad["last_run"] = None
    ad["created"] = time.strftime("%Y-%m-%d %H:%M:%S")
    BIG_ADS.append(ad)
    await _save_all()
    return ad["id"]


async def update_big_ad(ad_id, **fields):
    for ad in BIG_ADS:
        if ad["id"] == ad_id:
            ad.update(fields)
            await _save_all()
            return True
    return False


async def delete_big_ad(ad_id):
    global BIG_ADS
    BIG_ADS = [a for a in BIG_ADS if a["id"] != ad_id]
    await _save_all()


async def toggle_big_ad(ad_id):
    for ad in BIG_ADS:
        if ad["id"] == ad_id:
            ad["enabled"] = not ad["enabled"]
            await _save_all()
            return ad["enabled"]
    return None


def get_big_ad(ad_id):
    for ad in BIG_ADS:
        if ad["id"] == ad_id:
            return ad
    return None


def get_all_big_ads():
    return list(BIG_ADS)


def get_due_big_ads():
    """
    Returns big ads whose recurring schedule is due right now (checked once a minute
    by the scheduler loop). A daily ad is due if current H:M matches and it hasn't
    already run today. A weekly ad additionally must match today's weekday.
    """
    now = time.localtime()
    now_hm = (now.tm_hour, now.tm_min)
    today_str = time.strftime("%Y-%m-%d")
    due = []
    for ad in BIG_ADS:
        if not ad.get("enabled"):
            continue
        sched = ad.get("schedule", {})
        if sched.get("hour") != now_hm[0] or sched.get("minute") != now_hm[1]:
            continue
        if sched.get("type") == "weekly" and sched.get("weekday") != now.tm_wday:
            continue
        last_run = ad.get("last_run")
        if last_run == today_str:
            continue  # already ran today, don't double-fire within the same minute window
        due.append(ad)
    return due


async def mark_big_ad_ran(ad_id, sent, failed):
    today_str = time.strftime("%Y-%m-%d")
    for ad in BIG_ADS:
        if ad["id"] == ad_id:
            ad["last_run"] = today_str
    BIG_AD_SENDS.append({
        "big_ad_id": ad_id, "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "sent": sent, "failed": failed
    })
    await _save_all()


async def log_big_ad_click(ad_id):
    BIG_AD_CLICKS.append({"big_ad_id": ad_id, "ts": time.strftime("%Y-%m-%d %H:%M:%S")})
    await _save_all()


def get_big_ad_stats(ad_id):
    sends = [s for s in BIG_AD_SENDS if s["big_ad_id"] == ad_id]
    clicks = [c for c in BIG_AD_CLICKS if c["big_ad_id"] == ad_id]
    total_sent = sum(s["sent"] for s in sends)
    total_failed = sum(s["failed"] for s in sends)
    return {
        "runs": len(sends),
        "total_sent": total_sent,
        "total_failed": total_failed,
        "total_clicks": len(clicks),
    }


# ── Gateway ads frequency (GitHub landing page, every Nth conversion) ──

async def set_gateway_frequency(n):
    global GATEWAY_FREQUENCY
    GATEWAY_FREQUENCY = n
    await _save_all()


def get_gateway_frequency():
    return GATEWAY_FREQUENCY
