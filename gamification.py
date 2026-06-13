import json
import os
from datetime import datetime, timedelta

LEVELS = [
    (0, "Seedling"),
    (100, "Sapling"),
    (300, "Investor"),
    (600, "Analyst"),
    (1000, "Strategist"),
    (1500, "Fund Manager"),
    (2500, "Legend"),
]

from db import load_json, save_json

def get_level_info(xp):
    current = LEVELS[0]
    next_level = None
    for i, (threshold, name) in enumerate(LEVELS):
        if xp >= threshold:
            current = (threshold, name)
            next_level = LEVELS[i + 1] if i + 1 < len(LEVELS) else None
        else:
            break

    level_num = LEVELS.index(current) + 1

    if next_level:
        xp_to_next = next_level[0] - xp
        progress_pct = round(((xp - current[0]) / (next_level[0] - current[0])) * 100)
    else:
        xp_to_next = 0
        progress_pct = 100

    return {
        "level": level_num,
        "level_name": current[1],
        "xp": xp,
        "xp_to_next": xp_to_next,
        "progress_pct": progress_pct
    }

def ensure_gamification_fields(user):
    user.setdefault("xp", 0)
    user.setdefault("coins", 0)
    user.setdefault("streak", 0)
    user.setdefault("last_active", None)
    return user

def award_xp(username, amount):
    users = load_json("data/users.json")
    if username not in users:
        return None
    user = ensure_gamification_fields(users[username])
    user["xp"] += amount
    save_json("data/users.json", users)
    return user["xp"]

def update_streak(username):
    users = load_json("data/users.json")
    if username not in users:
        return 0, 0
    user = ensure_gamification_fields(users[username])

    today = datetime.now().date()
    last_active_str = user.get("last_active")
    xp_awarded = 0

    if last_active_str is None:
        user["streak"] = 1
        xp_awarded = 10
    else:
        last_active = datetime.fromisoformat(last_active_str).date()
        if last_active == today:
            pass
        elif last_active == today - timedelta(days=1):
            user["streak"] += 1
            xp_awarded = 10
            if user["streak"] % 7 == 0:
                xp_awarded += 50
                user["coins"] += 100
        else:
            user["streak"] = 1
            xp_awarded = 10

    if xp_awarded > 0:
        user["xp"] += xp_awarded
        user["last_active"] = today.isoformat()
        save_json("data/users.json", users)

    return user["streak"], xp_awarded

def get_rank(username):
    users = load_json("data/users.json")
    scored = []
    for name, u in users.items():
        scored.append((name, u.get("xp", 0)))
    scored.sort(key=lambda x: x[1], reverse=True)
    for i, (name, xp) in enumerate(scored):
        if name == username:
            return i + 1
    return len(scored)

def get_gamification_data(username):
    users = load_json("data/users.json")
    user = users.get(username, {})
    user = ensure_gamification_fields(user)
    level_info = get_level_info(user["xp"])
    return {
        **level_info,
        "streak": user["streak"],
        "coins": user["coins"],
        "rank": get_rank(username)
    }
