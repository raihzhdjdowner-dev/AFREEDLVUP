# -*- coding: utf-8 -*-
"""
User Manager — Admin-created users with account limits & expiry time
Stores users in users.json with per-user accounts isolation
"""

import json
import os
import time
import secrets
import string
import asyncio
from typing import Dict, List, Optional, Any

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH") or os.path.join(PROJECT_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)
USERS_FILE = os.path.join(DATA_DIR, "users.json")

# One-time migration: preserve an existing bundled users.json when the
# newly-attached Railway Volume is empty. Never overwrite existing volume data.
_LEGACY_USERS_FILE = os.path.join(PROJECT_DIR, "users.json")
try:
    if (not os.path.exists(USERS_FILE)
            and os.path.isfile(_LEGACY_USERS_FILE)
            and os.path.abspath(USERS_FILE) != os.path.abspath(_LEGACY_USERS_FILE)):
        import shutil
        shutil.copy2(_LEGACY_USERS_FILE, USERS_FILE)
        print(f"[PERSISTENCE] Migrated users.json -> {USERS_FILE}")
except Exception as e:
    print(f"[PERSISTENCE] users.json migration skipped: {e}")

print(f"[PERSISTENCE] user_manager DATA_DIR={DATA_DIR}")
_users_lock = asyncio.Lock()


# ==================== PASSWORD GENERATOR ====================
def generate_password(length: int = 10) -> str:
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


# ==================== STORAGE ====================
def _load_users() -> Dict[str, Any]:
    if not os.path.exists(USERS_FILE):
        return {}
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        return data
    except Exception:
        return {}


def _save_users(data: Dict[str, Any]):
    try:
        tmp = USERS_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, USERS_FILE)
    except Exception as e:
        print(f"[USER-MANAGER] Save error: {e}")


# ==================== USER OPERATIONS ====================

async def create_user(username: str, password: str, account_limit: int,
                      duration_value: int, duration_unit: str) -> Dict[str, Any]:
    """
    Create a new user with account limit and expiry.
    duration_unit: "minutes" | "hours" | "days"
    Returns dict with user info or {"error": "..."}
    """
    async with _users_lock:
        username = str(username).strip()
        password = str(password).strip()

        if not username or not password:
            return {"error": "Username and password required"}

        if len(username) < 3:
            return {"error": "Username must be at least 3 characters"}

        if len(password) < 4:
            return {"error": "Password must be at least 4 characters"}

        try:
            account_limit = int(account_limit)
            if account_limit < 1:
                return {"error": "Account limit must be at least 1"}
        except Exception:
            return {"error": "Invalid account limit"}

        try:
            duration_value = int(duration_value)
            if duration_value < 1:
                return {"error": "Duration must be at least 1"}
        except Exception:
            return {"error": "Invalid duration"}

        unit = str(duration_unit).lower().strip()
        if unit not in ("minutes", "hours", "days"):
            return {"error": "Invalid duration unit"}

        multiplier = {"minutes": 60, "hours": 3600, "days": 86400}[unit]
        duration_seconds = duration_value * multiplier

        users = _load_users()

        if username in users:
            return {"error": "Username already exists"}

        now = time.time()
        expiry = now + duration_seconds

        users[username] = {
            "username": username,
            "password": password,
            "account_limit": account_limit,
            "duration_seconds": duration_seconds,
            "duration_value": duration_value,
            "duration_unit": unit,
            "created_at": now,
            "expires_at": expiry,
            "accounts": [],
            "total_accounts_added": 0,
            "last_login": None,
            "is_active": True
        }
        _save_users(users)

        return {
            "status": "ok",
            "username": username,
            "password": password,
            "account_limit": account_limit,
            "expires_at": expiry,
            "duration_seconds": duration_seconds
        }


async def validate_user(username: str, password: str) -> Dict[str, Any]:
    """
    Validate login. Returns user dict if valid, else {"error": "..."}.
    Also auto-checks expiry.
    """
    async with _users_lock:
        users = _load_users()
        username = str(username).strip()
        password = str(password).strip()

        if username not in users:
            return {"error": "Invalid username or password"}

        user = users[username]

        if user.get("password") != password:
            return {"error": "Invalid username or password"}

        now = time.time()
        if now >= user.get("expires_at", 0):
            return {"error": "Account expired. Contact admin."}

        user["last_login"] = now
        _save_users(users)

        return {
            "status": "ok",
            "username": username,
            "account_limit": user.get("account_limit", 1),
            "expires_at": user.get("expires_at", 0),
            "accounts": user.get("accounts", []),
            "total_accounts_added": user.get("total_accounts_added", 0)
        }


async def get_user(username: str) -> Optional[Dict[str, Any]]:
    async with _users_lock:
        users = _load_users()
        return users.get(str(username).strip())


async def is_user_expired(username: str) -> bool:
    user = await get_user(username)
    if not user:
        return True
    return time.time() >= user.get("expires_at", 0)


async def add_account_to_user(username: str, account_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Add an account to user's list. Checks account_limit and expiry.
    """
    async with _users_lock:
        users = _load_users()
        username = str(username).strip()

        if username not in users:
            return {"error": "User not found"}

        user = users[username]

        if time.time() >= user.get("expires_at", 0):
            return {"error": "Account expired"}

        accounts = user.get("accounts", [])
        limit = user.get("account_limit", 1)

        if len(accounts) >= limit:
            return {"error": f"Account limit reached ({limit}). Remove one first."}

        # prevent duplicate
        acc_id = str(account_data.get("uid") or account_data.get("token", "")[:20])
        for acc in accounts:
            existing_id = str(acc.get("uid") or acc.get("token", "")[:20])
            if existing_id == acc_id:
                return {"error": "Account already added"}

        account_data["added_at"] = time.time()
        accounts.append(account_data)
        user["accounts"] = accounts
        user["total_accounts_added"] = user.get("total_accounts_added", 0) + 1
        _save_users(users)

        return {"status": "ok", "accounts": accounts}


async def remove_account_from_user(username: str, account_identifier: str) -> Dict[str, Any]:
    async with _users_lock:
        users = _load_users()
        username = str(username).strip()

        if username not in users:
            return {"error": "User not found"}

        user = users[username]
        accounts = user.get("accounts", [])

        new_accounts = []
        removed = False
        for acc in accounts:
            existing_id = str(acc.get("uid") or acc.get("token", "")[:20])
            if existing_id == str(account_identifier):
                removed = True
                continue
            new_accounts.append(acc)

        if not removed:
            return {"error": "Account not found"}

        user["accounts"] = new_accounts
        _save_users(users)

        return {"status": "ok", "accounts": new_accounts}


async def list_all_users() -> List[Dict[str, Any]]:
    async with _users_lock:
        users = _load_users()
        now = time.time()
        result = []
        for uname, u in users.items():
            remaining = max(0, u.get("expires_at", 0) - now)
            result.append({
                "username": uname,
                "password": u.get("password", ""),
                "account_limit": u.get("account_limit", 1),
                "accounts_count": len(u.get("accounts", [])),
                "total_accounts_added": u.get("total_accounts_added", 0),
                "created_at": u.get("created_at", 0),
                "expires_at": u.get("expires_at", 0),
                "remaining_seconds": int(remaining),
                "is_active": remaining > 0,
                "last_login": u.get("last_login"),
                "duration_value": u.get("duration_value", 0),
                "duration_unit": u.get("duration_unit", "hours")
            })
        result.sort(key=lambda x: x.get("created_at", 0), reverse=True)
        return result


async def delete_user(username: str) -> Dict[str, Any]:
    async with _users_lock:
        users = _load_users()
        username = str(username).strip()
        if username not in users:
            return {"error": "User not found"}
        del users[username]
        _save_users(users)
        return {"status": "ok"}


async def extend_user_time(username: str, duration_value: int, duration_unit: str) -> Dict[str, Any]:
    async with _users_lock:
        users = _load_users()
        username = str(username).strip()
        if username not in users:
            return {"error": "User not found"}

        try:
            duration_value = int(duration_value)
            if duration_value < 1:
                return {"error": "Duration must be at least 1"}
        except Exception:
            return {"error": "Invalid duration"}

        unit = str(duration_unit).lower().strip()
        if unit not in ("minutes", "hours", "days"):
            return {"error": "Invalid duration unit"}

        multiplier = {"minutes": 60, "hours": 3600, "days": 86400}[unit]
        extra = duration_value * multiplier

        user = users[username]
        current_expiry = user.get("expires_at", time.time())
        base = max(current_expiry, time.time())
        user["expires_at"] = base + extra
        user["duration_value"] = duration_value
        user["duration_unit"] = unit
        user["duration_seconds"] = extra
        _save_users(users)

        return {"status": "ok", "expires_at": user["expires_at"]}


def get_admin_credentials() -> Dict[str, str]:
    return {
        "username": "14444446555",
        "password": "8325703815"
    }