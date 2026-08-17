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


async def load_users():
    """Fetch the current user list + view logs from the Gist into memory. Call once at startup."""
    global USERS_CACHE, GATEWAY_VIEWS, TEXT_AD_VIEWS
    async with httpx.AsyncClient() as client:
        resp = await client.get(GITHUB_API, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        content = data["files"][GIST_FILENAME]["content"]
        parsed = json.loads(content)
        USERS_CACHE = {int(uid): info for uid, info in parsed.get("users", {}).items()}
        GATEWAY_VIEWS = parsed.get("gateway_views", [])
        TEXT_AD_VIEWS = parsed.get("text_ad_views", [])
    print(f"[storage] Loaded {len(USERS_CACHE)} users, "
          f"{len(GATEWAY_VIEWS)} gateway views, {len(TEXT_AD_VIEWS)} text ad views from Gist.")
    return USERS_CACHE


async def _save_all():
    """Push the current in-memory state (users + view logs) back to the Gist."""
    payload = {
        "files": {
            GIST_FILENAME: {
                "content": json.dumps({
                    "users": USERS_CACHE,
                    "gateway_views": GATEWAY_VIEWS,
                    "text_ad_views": TEXT_AD_VIEWS,
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
