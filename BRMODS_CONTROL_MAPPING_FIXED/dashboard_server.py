# -*- coding: utf-8 -*-
"""
FreeFire Level Up Bot — Web Dashboard Server
Admin + User system with per-user isolation, limits, expiry.
Async (aiohttp).  Fully compatible with Main.py (BR bot) and user_manager.py.
"""

import asyncio
import json
import os
import time
import secrets
import re
import copy
from typing import Dict, List, Any, Optional

from aiohttp import web

try:
    from user_manager import (
        create_user, validate_user, get_user, add_account_to_user,
        remove_account_from_user, list_all_users, delete_user,
        extend_user_time, get_admin_credentials, is_user_expired,
    )
except Exception:
    # Fallbacks — allow dashboard_server to import even if user_manager is missing.
    async def create_user(*a, **k): return {"error": "user_manager unavailable"}
    async def validate_user(*a, **k): return {"error": "user_manager unavailable"}
    async def get_user(*a, **k): return None
    async def add_account_to_user(*a, **k): return {"error": "user_manager unavailable"}
    async def remove_account_from_user(*a, **k): return {"error": "user_manager unavailable"}
    async def list_all_users(*a, **k): return []
    async def delete_user(*a, **k): return {"error": "user_manager unavailable"}
    async def extend_user_time(*a, **k): return {"error": "user_manager unavailable"}
    async def is_user_expired(*a, **k): return False
    def get_admin_credentials(): return {"username": "admin", "password": "admin"}



# ==================== RAILWAY PERSISTENT STORAGE ====================
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH") or os.path.join(PROJECT_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

def _persistent_path(filename: str) -> str:
    return os.path.join(DATA_DIR, filename)

def _migrate_legacy_file(filename: str) -> str:
    target = _persistent_path(filename)
    legacy = os.path.join(PROJECT_DIR, filename)
    try:
        if not os.path.exists(target) and os.path.isfile(legacy) and os.path.abspath(target) != os.path.abspath(legacy):
            import shutil
            shutil.copy2(legacy, target)
            print(f"[PERSISTENCE] Migrated {filename} -> {target}")
    except Exception as e:
        print(f"[PERSISTENCE] Migration skipped for {filename}: {e}")
    return target

# ==================== UPI PAYMENT SYSTEM ====================
PAYMENT_CONFIG_FILE = _migrate_legacy_file("payment_config.json")
PAYMENT_REQUESTS_FILE = _migrate_legacy_file("payment_requests.json")
PAYMENT_UPLOAD_DIR = os.path.join(DATA_DIR, "payment_uploads")
os.makedirs(PAYMENT_UPLOAD_DIR, exist_ok=True)
print(f"[PERSISTENCE] DATA_DIR={DATA_DIR}")
DEFAULT_PAYMENT_CONFIG = {
    "upi_id": "yourupi@upi",
    "qr_file": "",
    "plans": {
        "Starting": {"price": 99, "days": 1, "accounts": 3},
        "Basic": {"price": 199, "days": 2, "accounts": 3},
        "Premium": {"price": 249, "days": 3, "accounts": 4},
        "Safe": {"price": 699, "days": 7, "accounts": 5},
    },
}

def _payment_config():
    cfg = copy.deepcopy(DEFAULT_PAYMENT_CONFIG)
    try:
        if os.path.exists(PAYMENT_CONFIG_FILE):
            with open(PAYMENT_CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            cfg["upi_id"] = str(saved.get("upi_id", cfg["upi_id"]))
            cfg["qr_file"] = str(saved.get("qr_file", ""))
            if isinstance(saved.get("plans"), dict):
                for name, defaults in cfg["plans"].items():
                    item = saved["plans"].get(name, {})
                    if isinstance(item, dict):
                        defaults["price"] = float(item.get("price", defaults["price"]))
                        defaults["days"] = int(item.get("days", defaults["days"]))
                        defaults["accounts"] = int(item.get("accounts", defaults["accounts"]))
    except Exception:
        pass
    return cfg

def _save_payment_config(cfg):
    with open(PAYMENT_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

def _payment_requests():
    try:
        if os.path.exists(PAYMENT_REQUESTS_FILE):
            with open(PAYMENT_REQUESTS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        pass
    return []

def _save_payment_requests(items):
    with open(PAYMENT_REQUESTS_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2, ensure_ascii=False)

def _safe_filename(name):
    name = os.path.basename(str(name or "upload"))
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)

def _payment_public_config():
    cfg = _payment_config()
    plans = {}
    for name, item in cfg["plans"].items():
        plans[name] = {
            "price": item["price"],
            "days": item["days"],
            "accounts": item["accounts"],
        }
    return {"upi_id": cfg["upi_id"], "qr_file": cfg["qr_file"], "plans": plans}

# ==================== EXP TABLE ====================
EXP_TABLE: Dict[int, int] = {
    1: 0, 2: 48, 3: 202, 4: 544, 5: 1012, 6: 1844, 7: 2792, 8: 3800,
    9: 4870, 10: 6004, 11: 7192, 12: 8448, 13: 9760, 14: 11140, 15: 12566,
    16: 14060, 17: 15610, 18: 17224, 19: 18902, 20: 20632, 21: 22424, 22: 24278,
    23: 26192, 24: 28166, 25: 30200, 26: 32294, 27: 34448, 28: 37804, 29: 41274,
    30: 44870, 31: 48582, 32: 53394, 33: 58566, 34: 64096, 35: 69994, 36: 76460,
    37: 83506, 38: 91128, 39: 99322, 40: 108092, 41: 120144, 42: 133266, 43: 147472,
    44: 162760, 45: 179126, 46: 196572, 47: 215368, 48: 235516, 49: 257010, 50: 279860,
    51: 304056, 52: 348318, 53: 394982, 54: 444044, 55: 495508, 56: 549364, 57: 633756,
    58: 721744, 59: 813336, 60: 908522, 61: 1041438, 62: 1180352, 63: 1325266,
    64: 1476184, 65: 1634300, 66: 1840946, 67: 2056594, 68: 2281242, 69: 2514880,
    70: 2757530, 71: 3059506, 72: 3372284, 73: 3699456, 74: 4041030, 75: 4397002,
    76: 4829104, 77: 5282204, 78: 5756304, 79: 6251408, 80: 6776502, 81: 7381324,
    82: 8043154, 83: 8752982, 84: 9510808, 85: 10316338, 86: 11277190, 87: 12291748,
    88: 13360304, 89: 14482858, 90: 15659418, 91: 17026708, 92: 18453950, 93: 19941280,
    94: 21488570, 95: 23095858, 96: 24763138, 97: 26490428, 98: 28378704, 99: 30124996,
    100: 32032884,
}


def calculate_level_progress(level: int, current_exp: int) -> Dict[str, Any]:
    level = max(1, level)
    next_level = min(100, level + 1)
    base_exp = EXP_TABLE.get(level, 0)
    target_exp = EXP_TABLE.get(next_level, base_exp + 50000)

    needed = max(1, target_exp - base_exp)
    earned = max(0, current_exp - base_exp)
    remaining = max(0, target_exp - current_exp)
    pct = min(100.0, max(0.0, (earned / needed) * 100.0))

    return {
        "next_level": next_level,
        "base_exp": base_exp,
        "target_exp": target_exp,
        "needed_for_level": needed,
        "earned_in_level": earned,
        "remaining_exp": remaining,
        "progress_pct": round(pct, 1),
    }


# ==================== GLOBAL BOT STATE ====================
class BotState:
    def __init__(self):
        # --- core (used by dashboard + Main.py) ---
        self.accounts: Dict[str, Dict[str, Any]] = {}
        self.logs: List[Dict[str, Any]] = []
        self.max_logs = 200
        self.total_matches = 0
        self.total_matches_started = 0
        self.total_gained_exp = 0
        self.start_time = time.time()

        # --- attributes Main.py reads/writes directly ---
        self.account_workers: Dict[str, asyncio.Task] = {}
        self.account_token_map: Dict[str, str] = {}      # uid<->token/prefix
        self.auth_to_game_id: Dict[str, str] = {}        # guest uid -> game id
        self.game_to_auth_id: Dict[str, str] = {}        # game id -> guest uid
        self.paused_accounts: set = set()
        self.refresh_callbacks: Dict[str, Any] = {}
        self.account_credentials: Dict[str, Dict[str, Any]] = {}
        self.active_writers: Dict[str, set] = {}
        self.active_match_tasks: Dict[str, set] = {}
        self.active_aux_tasks: Dict[str, set] = {}
        self.account_links: Dict[str, str] = {}          # legacy alias

    # ---------- writers ----------
    def register_writer(self, uid: str, writer):
        uid_str = str(uid)
        self.active_writers.setdefault(uid_str, set()).add(writer)

    def unregister_writer(self, uid: str, writer):
        uid_str = str(uid)
        s = self.active_writers.get(uid_str)
        if s:
            s.discard(writer)
            if not s:
                self.active_writers.pop(uid_str, None)

    def _runtime_candidates(self, uid: str):
        uid_str = str(uid or "").strip()
        candidates = set()
        if not uid_str:
            return candidates
        candidates.add(uid_str)
        for mapping in (self.auth_to_game_id, self.game_to_auth_id, self.account_token_map):
            mapped = mapping.get(uid_str)
            if mapped:
                candidates.add(str(mapped))
                candidates.add(str(mapped)[:16])
        acc = self.accounts.get(uid_str)
        if acc:
            for key in ("uid", "actual_uid", "display_uid", "auth_uid", "token"):
                val = acc.get(key)
                if val:
                    candidates.add(str(val))
                    if key == "token":
                        candidates.add(str(val)[:16])
        cred = self.account_credentials.get(uid_str)
        if cred:
            for key in ("account_id", "auth_uid", "token", "auth_token"):
                val = cred.get(key)
                if val:
                    candidates.add(str(val))
                    if key in ("token", "auth_token"):
                        candidates.add(str(val)[:16])
        return {c for c in candidates if c}

    def register_match_task(self, uid: str, task):
        for c in self._runtime_candidates(uid) or {str(uid)}:
            self.active_match_tasks.setdefault(c, set()).add(task)

    def unregister_match_task(self, uid: str, task):
        for c in list(self._runtime_candidates(uid) or {str(uid)}):
            tasks = self.active_match_tasks.get(c)
            if tasks:
                tasks.discard(task)
                if not tasks:
                    self.active_match_tasks.pop(c, None)

    def register_aux_task(self, uid: str, task):
        for c in self._runtime_candidates(uid) or {str(uid)}:
            self.active_aux_tasks.setdefault(c, set()).add(task)

    def unregister_aux_task(self, uid: str, task):
        for c in list(self._runtime_candidates(uid) or {str(uid)}):
            tasks = self.active_aux_tasks.get(c)
            if tasks:
                tasks.discard(task)
                if not tasks:
                    self.active_aux_tasks.pop(c, None)

    def cancel_account_runtime(self, uid: str, reason: str = "manual") -> int:
        candidates = self._runtime_candidates(uid) or {str(uid)}
        tasks = set()
        for c in candidates:
            task = self.account_workers.get(c)
            if task:
                tasks.add(task)
            tasks.update(self.active_match_tasks.get(c, set()))
            tasks.update(self.active_aux_tasks.get(c, set()))

        # Close every live TCP writer before cancelling workers.
        for c in list(candidates):
            for w in list(self.active_writers.get(c, set())):
                try:
                    if not (hasattr(w, "is_closing") and w.is_closing()):
                        w.close()
                except Exception:
                    pass
            self.active_writers.pop(c, None)

        cancelled = 0
        for task in tasks:
            try:
                if not task.done():
                    task.cancel()
                    cancelled += 1
            except Exception:
                pass

        self.log(f"[RUNTIME] {reason.upper()} UID {str(uid)} | cancelled={cancelled}", "warning", str(uid))
        return cancelled

    def clear_account_runtime_maps(self, uid: str):
        candidates = self._runtime_candidates(uid) or {str(uid)}
        for c in candidates:
            self.paused_accounts.discard(c)
            self.account_workers.pop(c, None)
            self.account_credentials.pop(c, None)
            self.active_writers.pop(c, None)
            self.active_match_tasks.pop(c, None)
            self.active_aux_tasks.pop(c, None)
        for a, g in list(self.auth_to_game_id.items()):
            if a in candidates or g in candidates:
                self.auth_to_game_id.pop(a, None)
        for g, a in list(self.game_to_auth_id.items()):
            if g in candidates or a in candidates:
                self.game_to_auth_id.pop(g, None)
        for k, v in list(self.account_token_map.items()):
            if k in candidates or str(v) in candidates:
                self.account_token_map.pop(k, None)

    def close_writers_for_account(self, uid: str):
        candidates = self._runtime_candidates(uid) or {str(uid)}
        for c in list(candidates):
            for w in list(self.active_writers.get(c, set())):
                try:
                    if hasattr(w, "is_closing") and w.is_closing():
                        continue
                    w.close()
                except Exception:
                    pass
            self.active_writers.pop(c, None)

    # ---------- logs ----------
    def log(self, message: str, level: str = "info", uid: Optional[str] = None):
        self.logs.append({
            "time": time.strftime("%H:%M:%S"),
            "level": level,
            "message": message,
            "uid": str(uid) if uid else None,
        })
        if len(self.logs) > self.max_logs:
            self.logs.pop(0)

    # ---------- account registration ----------
    def register_account(self, uid: str, nickname: str, region: str, level: int,
                         exp: int, likes: int = 0, token: Optional[str] = None,
                         auth_uid: Optional[str] = None,
                         owner: Optional[str] = None):
        uid_str = str(uid)
        auth_uid_str = str(auth_uid) if auth_uid else self.game_to_auth_id.get(uid_str, "")
        if auth_uid_str:
            self.auth_to_game_id[auth_uid_str] = uid_str
            self.game_to_auth_id[uid_str] = auth_uid_str
            self.account_token_map[auth_uid_str] = uid_str
            self.account_token_map[uid_str] = auth_uid_str
        if token:
            self.account_token_map[uid_str] = token
            self.account_token_map[token[:16]] = uid_str
            if auth_uid_str:
                self.account_token_map[auth_uid_str] = token

        prog = calculate_level_progress(level or 1, exp)
        lvl_val = level or 1

        if uid_str not in self.accounts:
            self.accounts[uid_str] = {
                "uid": uid_str,
                "display_uid": uid_str,
                "actual_uid": uid_str,
                "auth_uid": auth_uid_str or "",
                "nickname": nickname or f"Player_{uid_str[:6]}",
                "region": region or "BD",
                "level": lvl_val,
                "next_level": prog["next_level"],
                "initial_exp": exp,
                "current_exp": exp,
                "gained_exp": 0,
                "remaining_exp": prog["remaining_exp"],
                "target_exp": prog["target_exp"],
                "needed_for_level": prog["needed_for_level"],
                "earned_in_level": prog["earned_in_level"],
                "progress_pct": prog["progress_pct"],
                "likes": likes or 0,
                "status": "PAUSED" if self.is_paused(uid_str) else "ONLINE",
                "matches_played": 0,
                "active_matches": 0,
                "last_match_time": None,
                "last_updated": time.strftime("%H:%M:%S"),
                "token": token or "",
                "start_time": time.time(),
                "is_paused": self.is_paused(uid_str),
                "paused_at": time.time() if self.is_paused(uid_str) else None,
                "total_pause_duration": 0.0,
                "owner": owner,
                "added_at": time.time(),
            }
        else:
            acc = self.accounts[uid_str]
            if auth_uid_str:
                acc["auth_uid"] = auth_uid_str
            if nickname:
                acc["nickname"] = nickname
            if region:
                acc["region"] = region
            if level:
                acc["level"] = level
            if token:
                acc["token"] = token
            acc["current_exp"] = exp
            acc["gained_exp"] = max(0, exp - acc["initial_exp"])
            acc["next_level"] = prog["next_level"]
            acc["remaining_exp"] = prog["remaining_exp"]
            acc["target_exp"] = prog["target_exp"]
            acc["needed_for_level"] = prog["needed_for_level"]
            acc["earned_in_level"] = prog["earned_in_level"]
            acc["progress_pct"] = prog["progress_pct"]
            acc["likes"] = likes
            if not acc.get("is_paused"):
                acc["status"] = "ONLINE"
            acc["last_updated"] = time.strftime("%H:%M:%S")
            if owner:
                acc["owner"] = owner

        self.recalc_totals()

    def update_exp(self, uid: str, current_exp: int, level: Optional[int] = None):
        uid_str = str(uid)
        acc = self.accounts.get(uid_str)
        if not acc:
            return
        old_exp = acc["current_exp"]
        old_level = acc.get("level", 1)
        acc["current_exp"] = current_exp
        if level is not None and level > 0:
            acc["level"] = level
        acc["gained_exp"] = max(0, current_exp - acc["initial_exp"])

        prog = calculate_level_progress(acc["level"], current_exp)
        acc["next_level"] = prog["next_level"]
        acc["remaining_exp"] = prog["remaining_exp"]
        acc["target_exp"] = prog["target_exp"]
        acc["needed_for_level"] = prog["needed_for_level"]
        acc["earned_in_level"] = prog["earned_in_level"]
        acc["progress_pct"] = prog["progress_pct"]
        acc["last_updated"] = time.strftime("%H:%M:%S")

        if old_level < 3 and acc["level"] >= 3:
            self.log(f"🎉 LEVEL UP! UID {uid_str} ({acc['nickname']}) reached Level {acc['level']}!",
                     "success", uid_str)

        diff = current_exp - old_exp
        if diff > 0:
            self.log(
                f"★ UID {uid_str} ({acc['nickname']}) gained +{diff:,} EXP | "
                f"Level {acc['level']} ({prog['progress_pct']}% - {prog['remaining_exp']:,} EXP to Lvl {prog['next_level']})",
                "success", uid_str
            )
        self.recalc_totals()

    def get_account_level(self, uid: str) -> int:
        uid_str = str(uid)
        acc = self.accounts.get(uid_str)
        if not acc:
            mapped = self.game_to_auth_id.get(uid_str) or self.auth_to_game_id.get(uid_str)
            if mapped and mapped in self.accounts:
                acc = self.accounts[mapped]
        return int(acc.get("level", 1) or 1) if acc else 1

    def get_account_mode(self, uid: str) -> str:
        return "BR" if self.get_account_level(uid) < 3 else "LONE_WOLF"

    def update_status(self, uid: str, status: str, active_matches: Optional[int] = None):
        uid_str = str(uid)
        if uid_str in self.accounts:
            self.accounts[uid_str]["status"] = status
            if active_matches is not None:
                self.accounts[uid_str]["active_matches"] = active_matches
            self.accounts[uid_str]["last_updated"] = time.strftime("%H:%M:%S")

    def increment_match_started(self):
        self.total_matches_started += 1

    def increment_match(self, uid: str):
        uid_str = str(uid)
        self.total_matches += 1
        if uid_str in self.accounts:
            acc = self.accounts[uid_str]
            acc["matches_played"] += 1
            acc["last_match_time"] = time.strftime("%H:%M:%S")
            acc["last_updated"] = time.strftime("%H:%M:%S")
            self.log(f"⚔ Match #{acc['matches_played']} finished for {acc['nickname']} ({uid_str})",
                     "info", uid_str)

    def get_account_uptime(self, uid_str: str) -> int:
        acc = self.accounts.get(uid_str)
        if not acc:
            mapped = self.game_to_auth_id.get(uid_str) or self.auth_to_game_id.get(uid_str)
            if mapped and mapped in self.accounts:
                acc = self.accounts[mapped]
        if not acc:
            return 0
        start_t = acc.get("start_time", time.time())
        total_pause = acc.get("total_pause_duration", 0.0)
        if acc.get("is_paused") and acc.get("paused_at"):
            return max(0, int(acc["paused_at"] - start_t - total_pause))
        return max(0, int(time.time() - start_t - total_pause))

    # ---------- pause ----------
    def is_paused(self, uid: str) -> bool:
        uid_str = str(uid)
        if uid_str in self.paused_accounts:
            return True
        game_id = self.auth_to_game_id.get(uid_str)
        if game_id and game_id in self.paused_accounts:
            return True
        auth_uid = self.game_to_auth_id.get(uid_str)
        if auth_uid and auth_uid in self.paused_accounts:
            return True
        acc = self.accounts.get(uid_str) or (self.accounts.get(game_id) if game_id else None)
        if acc and acc.get("is_paused"):
            return True
        return False

    def toggle_pause(self, uid: str) -> bool:
        uid_str = str(uid)
        candidates = {uid_str}
        if uid_str in self.auth_to_game_id:
            candidates.add(self.auth_to_game_id[uid_str])
        if uid_str in self.game_to_auth_id:
            candidates.add(self.game_to_auth_id[uid_str])

        target_acc = None
        target_key = uid_str
        for c in candidates:
            if c in self.accounts:
                target_acc = self.accounts[c]
                target_key = c
                break

        is_now_paused = not self.is_paused(uid_str)
        if is_now_paused:
            for c in candidates:
                self.paused_accounts.add(c)
            self.close_writers_for_account(uid_str)
            for c in list(candidates):
                for task in list(self.active_match_tasks.get(c, set())):
                    try:
                        if not task.done():
                            task.cancel()
                    except Exception:
                        pass
            if target_acc:
                target_acc["is_paused"] = True
                target_acc["paused_at"] = time.time()
                target_acc["status"] = "PAUSED"
            nick = target_acc.get("nickname", target_key) if target_acc else target_key
            self.log(f"⏸ UID {target_key} ({nick}) paused.", "warning", target_key)
            cb = self.refresh_callbacks.get("on_pause_toggle")
            if cb:
                try: asyncio.create_task(cb(target_key, True))
                except Exception: pass
        else:
            for c in candidates:
                self.paused_accounts.discard(c)
            if target_acc:
                target_acc["is_paused"] = False
                if target_acc.get("paused_at"):
                    pause_dur = time.time() - target_acc["paused_at"]
                    target_acc["total_pause_duration"] = target_acc.get("total_pause_duration", 0.0) + pause_dur
                    target_acc["paused_at"] = None
                target_acc["status"] = "ONLINE"
            nick = target_acc.get("nickname", target_key) if target_acc else target_key
            self.log(f"▶ UID {target_key} ({nick}) resumed.", "success", target_key)
            cb = self.refresh_callbacks.get("on_pause_toggle")
            if cb:
                try: asyncio.create_task(cb(target_key, False))
                except Exception: pass

        return is_now_paused

    def toggle_pause_all(self) -> bool:
        any_active = any(not self.is_paused(k) for k in self.accounts.keys())
        for k in list(self.accounts.keys()):
            current_paused = self.is_paused(k)
            if any_active and not current_paused:
                self.toggle_pause(k)
            elif not any_active and current_paused:
                self.toggle_pause(k)
        return any_active

    def recalc_totals(self):
        self.total_gained_exp = sum(acc.get("gained_exp", 0) for acc in self.accounts.values())


bot_state = BotState()


# ==================== SESSIONS ====================
_sessions: Dict[str, Dict[str, Any]] = {}
_session_lock = asyncio.Lock()
SESSION_TTL = 86400


def _gen_session_id() -> str:
    return secrets.token_urlsafe(32)


async def create_session(username: str, is_admin: bool = False) -> str:
    async with _session_lock:
        sid = _gen_session_id()
        _sessions[sid] = {"username": username, "is_admin": is_admin, "created_at": time.time()}
        return sid


async def get_session(sid: Optional[str]) -> Optional[Dict[str, Any]]:
    if not sid:
        return None
    async with _session_lock:
        s = _sessions.get(sid)
        if not s:
            return None
        if time.time() - s["created_at"] > SESSION_TTL:
            _sessions.pop(sid, None)
            return None
        return s


async def destroy_session(sid: Optional[str]):
    if not sid:
        return
    async with _session_lock:
        _sessions.pop(sid, None)


def _get_sid(request: web.Request) -> Optional[str]:
    return request.cookies.get("sid")


def _json_error(msg: str, status: int = 400) -> web.Response:
    return web.json_response({"status": "error", "error": msg}, status=status)


# ==================== TEMPLATES ====================
TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")


def load_template(name: str) -> str:
    path = os.path.join(TEMPLATES_DIR, name)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            pass
    return f"<!doctype html><html><body style='background:#0a0a12;color:#fff;font-family:sans-serif;text-align:center;padding:60px'><h1>TAZHINI BOT</h1><p>{name} not found</p></body></html>"


# ==================== POPUP CONFIG ====================
POPUP_CONFIG_FILE = _migrate_legacy_file("popup_config.json")

DEFAULT_POPUP = {
    "enabled": True,
    "header": "Important Update",
    "title": "Server Maintenance",
    "message": "The bot is currently being upgraded. Please check back soon.",
    "button_text": "Contact Support",
    "button_link": "https://t.me/",
    "icon_class": "fa-solid fa-circle-check",
    "icon_color": "#22c55e",
    "updated_at": 0,
}


def _load_popup_config() -> Dict[str, Any]:
    if not os.path.exists(POPUP_CONFIG_FILE):
        return dict(DEFAULT_POPUP)
    try:
        with open(POPUP_CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        cfg = dict(DEFAULT_POPUP)
        cfg.update(data or {})
        return cfg
    except Exception:
        return dict(DEFAULT_POPUP)


def _save_popup_config(cfg: Dict[str, Any]):
    try:
        tmp = POPUP_CONFIG_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        os.replace(tmp, POPUP_CONFIG_FILE)
    except Exception as e:
        print(f"[POPUP] Save error: {e}")


# ==================== PAGE ROUTES ====================

async def handle_payment_page(request: web.Request) -> web.Response:
    return web.Response(text=load_template("payment.html"), content_type="text/html", charset="utf-8")

async def handle_payment_file(request: web.Request) -> web.StreamResponse:
    name = _safe_filename(request.match_info.get("name", ""))
    path = os.path.join(PAYMENT_UPLOAD_DIR, name)
    if not os.path.isfile(path):
        raise web.HTTPNotFound()
    return web.FileResponse(path)

async def api_public_payment(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok", "payment": _payment_public_config()})

async def api_submit_payment(request: web.Request) -> web.Response:
    try:
        reader = await request.multipart()
        fields = {}
        screenshot_name = ""
        os.makedirs(PAYMENT_UPLOAD_DIR, exist_ok=True)

        while True:
            part = await reader.next()
            if part is None:
                break
            if part.name == "screenshot":
                original = _safe_filename(part.filename or "payment.png")
                ext = os.path.splitext(original)[1].lower()
                if ext not in {".png", ".jpg", ".jpeg", ".webp"}:
                    return _json_error("Only PNG, JPG, JPEG or WEBP screenshots are allowed", 400)
                filename = f"payment_{int(time.time())}_{secrets.token_hex(5)}{ext}"
                target = os.path.join(PAYMENT_UPLOAD_DIR, filename)
                size = 0
                with open(target, "wb") as f:
                    while True:
                        chunk = await part.read_chunk()
                        if not chunk:
                            break
                        size += len(chunk)
                        if size > 5 * 1024 * 1024:
                            f.close()
                            try: os.remove(target)
                            except OSError: pass
                            return _json_error("Screenshot must be 5 MB or smaller", 400)
                        f.write(chunk)
                screenshot_name = filename
            else:
                fields[part.name] = (await part.text()).strip()

        plan = fields.get("plan", "")
        cfg = _payment_config()
        if plan not in cfg["plans"]:
            return _json_error("Invalid plan", 400)
        if not fields.get("customer_name") or not fields.get("contact") or not fields.get("utr"):
            return _json_error("Name, contact and UTR are required", 400)
        if not screenshot_name:
            return _json_error("Payment screenshot is required", 400)

        item = cfg["plans"][plan]
        req = {
            "id": secrets.token_hex(8),
            "created_at": int(time.time()),
            "customer_name": fields["customer_name"][:100],
            "contact": fields["contact"][:100],
            "utr": fields["utr"][:100],
            "plan": plan,
            "amount": item["price"],
            "screenshot": screenshot_name,
            "status": "pending",
            "active": True,
        }
        items = _payment_requests()
        items.insert(0, req)
        _save_payment_requests(items)
        return web.json_response({"status": "ok", "request_id": req["id"], "message": "Payment request submitted. Admin verification is required."})
    except Exception as e:
        return _json_error(str(e), 500)

async def api_admin_payment_settings(request: web.Request) -> web.Response:
    err = await _require_admin(request)
    if err: return err
    return web.json_response({"status": "ok", "payment": _payment_public_config()})

async def api_admin_save_payment_settings(request: web.Request) -> web.Response:
    err = await _require_admin(request)
    if err: return err
    try:
        data = await request.json()
        cfg = _payment_config()
        cfg["upi_id"] = str(data.get("upi_id", cfg["upi_id"])).strip()[:120]
        plans = data.get("plans", {})
        for name in cfg["plans"]:
            item = plans.get(name, {}) if isinstance(plans, dict) else {}
            if "price" in item:
                price = float(item["price"])
                if price < 0 or price > 1000000:
                    raise ValueError("Invalid plan price")
                cfg["plans"][name]["price"] = price
            if "days" in item:
                cfg["plans"][name]["days"] = max(1, int(item["days"]))
            if "accounts" in item:
                cfg["plans"][name]["accounts"] = max(1, int(item["accounts"]))
        _save_payment_config(cfg)
        return web.json_response({"status": "ok", "payment": _payment_public_config()})
    except Exception as e:
        return _json_error(str(e), 400)

async def api_admin_upload_qr(request: web.Request) -> web.Response:
    err = await _require_admin(request)
    if err: return err
    try:
        reader = await request.multipart()
        part = await reader.next()
        if not part or part.name != "qr":
            return _json_error("QR image is required", 400)
        ext = os.path.splitext(_safe_filename(part.filename or "qr.png"))[1].lower()
        if ext not in {".png", ".jpg", ".jpeg", ".webp"}:
            return _json_error("Only PNG, JPG, JPEG or WEBP QR images are allowed", 400)
        os.makedirs(PAYMENT_UPLOAD_DIR, exist_ok=True)
        filename = f"upi_qr{ext}"
        target = os.path.join(PAYMENT_UPLOAD_DIR, filename)
        size = 0
        with open(target, "wb") as f:
            while True:
                chunk = await part.read_chunk()
                if not chunk: break
                size += len(chunk)
                if size > 3 * 1024 * 1024:
                    f.close()
                    try: os.remove(target)
                    except OSError: pass
                    return _json_error("QR image must be 3 MB or smaller", 400)
                f.write(chunk)
        cfg = _payment_config()
        cfg["qr_file"] = filename
        _save_payment_config(cfg)
        return web.json_response({"status": "ok", "qr_file": filename})
    except Exception as e:
        return _json_error(str(e), 500)

async def api_admin_payment_requests(request: web.Request) -> web.Response:
    err = await _require_admin(request)
    if err: return err
    return web.json_response({"status": "ok", "requests": _payment_requests()})

async def api_admin_payment_action(request: web.Request) -> web.Response:
    err = await _require_admin(request)
    if err: return err
    try:
        data = await request.json()
        req_id = str(data.get("id", ""))
        action = str(data.get("action", "")).lower()
        items = _payment_requests()
        found = None
        for item in items:
            if item.get("id") == req_id:
                found = item
                break
        if not found:
            return _json_error("Payment request not found", 404)
        if action == "verify":
            found["status"] = "verified"
            found["verified_at"] = int(time.time())
            found["active"] = True
        elif action == "reject":
            found["status"] = "rejected"
            found["active"] = False
        elif action == "activate":
            found["active"] = True
        elif action == "deactivate":
            found["active"] = False
        else:
            return _json_error("Invalid action", 400)
        _save_payment_requests(items)
        return web.json_response({"status": "ok", "request": found})
    except Exception as e:
        return _json_error(str(e), 400)

async def handle_root(request: web.Request) -> web.Response:
    # Render the landing-page prices from the same admin-managed payment config.
    # This makes the displayed card prices update even when browser JS/cache is stale.
    html = load_template("landing.html")
    try:
        plans = _payment_config().get("plans", {})
        for plan_name in ("Starting", "Basic", "Premium", "Safe"):
            item = plans.get(plan_name, {})
            price = item.get("price", "")
            try:
                price_text = f"{float(price):g}"
            except Exception:
                price_text = str(price)
            html = html.replace(
                f'data-plan-price="{plan_name}">{plan_name}',
                f'data-plan-price="{plan_name}">{plan_name}'
            )
            marker = f'data-plan-price="{plan_name}">'
            pos = html.find(marker)
            if pos != -1:
                start = pos + len(marker)
                end = html.find('</span>', start)
                if end != -1:
                    html = html[:start] + price_text + html[end:]
    except Exception:
        pass
    return web.Response(
        text=html,
        content_type="text/html",
        charset="utf-8",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0", "Pragma": "no-cache"}
    )


async def handle_login_page(request: web.Request) -> web.Response:
    return web.Response(text=load_template("login.html"), content_type="text/html", charset="utf-8")


async def handle_admin_login_page(request: web.Request) -> web.Response:
    return web.Response(text=load_template("admin_login.html"), content_type="text/html", charset="utf-8")


async def handle_admin_page(request: web.Request) -> web.Response:
    sess = await get_session(_get_sid(request))
    if not sess or not sess.get("is_admin"):
        return web.HTTPFound("/admin-login")
    return web.Response(text=load_template("admin.html"), content_type="text/html", charset="utf-8")


async def handle_dashboard_page(request: web.Request) -> web.Response:
    sid = _get_sid(request)
    sess = await get_session(sid)
    if not sess or sess.get("is_admin"):
        return web.HTTPFound("/login")
    if await is_user_expired(sess["username"]):
        await destroy_session(sid)
        return web.HTTPFound("/login?expired=1")
    return web.Response(text=load_template("dashboard.html"), content_type="text/html", charset="utf-8")


# ==================== AUTH API ====================
async def api_user_login(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        username = str(data.get("username", "")).strip()
        password = str(data.get("password", "")).strip()
        if not username or not password:
            return _json_error("Username and password required")
        result = await validate_user(username, password)
        if "error" in result:
            return _json_error(result["error"], 401)
        sid = await create_session(username, is_admin=False)
        resp = web.json_response({
            "status": "ok",
            "username": username,
            "account_limit": result.get("account_limit"),
            "expires_at": result.get("expires_at"),
        })
        resp.set_cookie("sid", sid, httponly=True, samesite="Lax", max_age=SESSION_TTL)
        return resp
    except Exception as e:
        return _json_error(str(e), 500)


async def api_admin_login(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        username = str(data.get("username", "")).strip()
        password = str(data.get("password", "")).strip()
        creds = get_admin_credentials()
        if username != creds["username"] or password != creds["password"]:
            return _json_error("Invalid admin credentials", 401)
        sid = await create_session(username, is_admin=True)
        resp = web.json_response({"status": "ok"})
        resp.set_cookie("sid", sid, httponly=True, samesite="Lax", max_age=SESSION_TTL)
        return resp
    except Exception as e:
        return _json_error(str(e), 500)


async def api_logout(request: web.Request) -> web.Response:
    await destroy_session(_get_sid(request))
    resp = web.json_response({"status": "ok"})
    resp.del_cookie("sid")
    return resp


# ==================== ADMIN API ====================
async def _require_admin(request: web.Request) -> Optional[web.Response]:
    sess = await get_session(_get_sid(request))
    if not sess or not sess.get("is_admin"):
        return _json_error("Unauthorized", 401)
    return None


async def api_admin_create_user(request: web.Request) -> web.Response:
    err = await _require_admin(request)
    if err: return err
    try:
        data = await request.json()
        result = await create_user(
            username=data.get("username", ""),
            password=data.get("password", ""),
            account_limit=data.get("account_limit", 1),
            duration_value=data.get("duration_value", 1),
            duration_unit=data.get("duration_unit", "hours"),
        )
        if "error" in result:
            return _json_error(result["error"])
        return web.json_response(result)
    except Exception as e:
        return _json_error(str(e), 500)


async def api_admin_list_users(request: web.Request) -> web.Response:
    err = await _require_admin(request)
    if err: return err
    try:
        users = await list_all_users()
        return web.json_response({"status": "ok", "users": users})
    except Exception as e:
        return _json_error(str(e), 500)


async def api_admin_delete_user(request: web.Request) -> web.Response:
    err = await _require_admin(request)
    if err: return err
    try:
        data = await request.json()
        username = str(data.get("username", "")).strip()
        result = await delete_user(username)
        if "error" in result:
            return _json_error(result["error"])
        # cancel any worker keyed with "{username}::..."
        for key, task in list(bot_state.account_workers.items()):
            if key.startswith(f"{username}::"):
                task.cancel()
                bot_state.account_workers.pop(key, None)
        return web.json_response(result)
    except Exception as e:
        return _json_error(str(e), 500)


async def api_admin_extend_user(request: web.Request) -> web.Response:
    err = await _require_admin(request)
    if err: return err
    try:
        data = await request.json()
        result = await extend_user_time(
            username=data.get("username", ""),
            duration_value=data.get("duration_value", 1),
            duration_unit=data.get("duration_unit", "hours"),
        )
        if "error" in result:
            return _json_error(result["error"])
        return web.json_response(result)
    except Exception as e:
        return _json_error(str(e), 500)


async def api_admin_get_popup(request: web.Request) -> web.Response:
    err = await _require_admin(request)
    if err: return err
    return web.json_response({"status": "ok", "popup": _load_popup_config()})


async def api_admin_save_popup(request: web.Request) -> web.Response:
    err = await _require_admin(request)
    if err: return err
    try:
        data = await request.json()
        cfg = _load_popup_config()
        for k in ("enabled", "header", "title", "message", "button_text",
                  "button_link", "icon_class", "icon_color"):
            if k in data:
                cfg[k] = bool(data[k]) if k == "enabled" else str(data[k])
        cfg["updated_at"] = int(time.time())
        _save_popup_config(cfg)
        return web.json_response({"status": "ok", "popup": cfg})
    except Exception as e:
        return _json_error(str(e), 500)


# ==================== USER API ====================
async def _require_user(request: web.Request) -> Optional[web.Response]:
    sess = await get_session(_get_sid(request))
    if not sess or sess.get("is_admin"):
        return _json_error("Unauthorized", 401)
    return None


def _build_user_accounts(username: str, user: Dict[str, Any]) -> List[Dict[str, Any]]:
    now = time.time()
    result_accounts = []

    for acc in user.get("accounts", []):
        user_uid = str(acc.get("uid") or acc.get("token", "")[:20])
        user_token_prefix = str(acc.get("token", ""))[:20] if acc.get("token") else ""
        merged = None

        for bot_uid, bot_acc in bot_state.accounts.items():
            bot_uid_str = str(bot_uid)
            bot_actual = str(bot_acc.get("actual_uid", ""))
            bot_display = str(bot_acc.get("display_uid", ""))
            bot_auth = str(bot_acc.get("auth_uid", ""))
            bot_token = str(bot_acc.get("token", ""))
            if (bot_uid_str == user_uid or bot_actual == user_uid or
                    bot_display == user_uid or bot_auth == user_uid or
                    (user_token_prefix and (bot_uid_str == user_token_prefix or
                                            bot_token[:20] == user_token_prefix))):
                # A proven match from this user's stored UID/token is enough to
                # attach the live native-login account to this dashboard user.
                if not bot_acc.get("owner"):
                    bot_acc["owner"] = username
                merged = dict(bot_acc)
                real_uid = bot_actual or bot_uid_str
                merged["uid"] = real_uid
                merged["display_uid"] = real_uid
                merged["actual_uid"] = real_uid
                merged["user_input_uid"] = user_uid
                merged["added_at"] = acc.get("added_at", bot_acc.get("added_at", now))
                break

        if merged is None:
            prog = calculate_level_progress(1, 0)
            merged = {
                "uid": user_uid,
                "display_uid": user_uid,
                "actual_uid": user_uid,
                "user_input_uid": user_uid,
                "nickname": f"Player_{user_uid[:6]}",
                "region": "BD",
                "level": 1,
                "initial_exp": 0,
                "current_exp": 0,
                "gained_exp": 0,
                "likes": 0,
                "status": "CONNECTING",
                "matches_played": 0,
                "active_matches": 0,
                "last_match_time": None,
                "last_updated": time.strftime("%H:%M:%S"),
                "added_at": acc.get("added_at", now),
                "owner": username,
                "nickname": acc.get("nickname") or f"Player_{user_uid[:6]}",
                "region": acc.get("region") or "BD",
                "level": int(acc.get("level") or 1),
                "initial_exp": int(acc.get("initial_exp", acc.get("exp", 0)) or 0),
                "current_exp": int(acc.get("current_exp", acc.get("exp", 0)) or 0),
                "gained_exp": int(acc.get("gained_exp", 0) or 0),
                **{k: prog[k] for k in ("next_level", "remaining_exp", "target_exp",
                                        "needed_for_level", "earned_in_level", "progress_pct")},
            }
        result_accounts.append(merged)
    return result_accounts


async def api_user_stats(request: web.Request) -> web.Response:
    err = await _require_user(request)
    if err: return err
    try:
        sess = await get_session(_get_sid(request))
        username = sess["username"]
        user = await get_user(username)
        if not user:
            return _json_error("User not found", 404)

        now = time.time()
        remaining = max(0, user.get("expires_at", 0) - now)
        result_accounts = _build_user_accounts(username, user)

        # overlay fresh bot_state data
        for acc in result_accounts:
            real_uid = str(acc.get("actual_uid") or acc.get("uid") or "")
            user_input_uid = str(acc.get("user_input_uid") or "")
            fresh = None
            for check_key in [real_uid, user_input_uid, str(acc.get("uid", ""))]:
                if check_key and check_key in bot_state.accounts:
                    cand = bot_state.accounts[check_key]
                    if (cand.get("owner") == username or
                            str(cand.get("auth_uid", "")) == user_input_uid or
                            str(cand.get("display_uid", "")) == user_input_uid):
                        if fresh is None or cand.get("current_exp", 0) > fresh.get("current_exp", 0):
                            fresh = cand
            if fresh:
                for k in ("current_exp", "gained_exp", "level", "nickname", "region",
                          "status", "matches_played", "active_matches", "last_updated",
                          "likes", "next_level", "remaining_exp", "target_exp",
                          "needed_for_level", "earned_in_level", "progress_pct",
                          "is_paused", "paused_at", "total_pause_duration"):
                    if k in fresh:
                        acc[k] = fresh[k]

        total_gained = sum(a.get("gained_exp", 0) for a in result_accounts)
        total_matches = sum(a.get("matches_played", 0) for a in result_accounts)

        return web.json_response({
            "status": "ok",
            "username": username,
            "account_limit": user.get("account_limit", 1),
            "accounts_used": len(user.get("accounts", [])),
            "remaining_seconds": int(remaining),
            "expires_at": user.get("expires_at", 0),
            "accounts": result_accounts,
            "total_gained_exp": total_gained,
            "total_matches": total_matches,
            "created_at": user.get("created_at", 0),
            "total_accounts_added": user.get("total_accounts_added", 0),
        })
    except Exception as e:
        return _json_error(str(e), 500)


async def api_user_add_account(request: web.Request) -> web.Response:
    err = await _require_user(request)
    if err: return err
    try:
        sess = await get_session(_get_sid(request))
        username = sess["username"]
        data = await request.json()

        payload = {}
        if data.get("token"):
            payload["token"] = str(data["token"]).strip()
        elif data.get("uid") and data.get("password"):
            payload["uid"] = str(data["uid"]).strip()
            payload["password"] = str(data["password"]).strip()
        else:
            return _json_error("Provide UID+Password or Token")

        result = await add_account_to_user(username, payload)
        if "error" in result:
            return _json_error(result["error"])

        cb = bot_state.refresh_callbacks.get("on_user_account_added")
        if cb:
            asyncio.create_task(cb(username, payload))
        # legacy name
        cb2 = bot_state.refresh_callbacks.get("on_account_added")
        if cb2:
            asyncio.create_task(cb2(payload))
        return web.json_response({"status": "ok"})
    except Exception as e:
        return _json_error(str(e), 500)


async def _resolve_user_account_runtime(username: str, requested_id: str):
    """Resolve a dashboard card ID to the user's stored account and all live aliases.

    The dashboard displays the native/game UID, while users.json can store the
    login/auth UID (or token prefix).  Control endpoints must accept either.
    """
    user = await get_user(username)
    if not user:
        return None, set(), None

    requested = str(requested_id or "").strip()
    selected = None
    aliases = set()

    # First match the stored account directly.
    for acc in user.get("accounts", []):
        stored_uid = str(acc.get("uid") or "").strip()
        stored_token = str(acc.get("token") or "").strip()
        token_prefix = stored_token[:20] if stored_token else ""
        if requested and requested in {stored_uid, token_prefix}:
            selected = acc
            break

    # If the card contains the native/game UID, resolve it through live bot state.
    if selected is None and requested:
        for bot_uid, live in list(bot_state.accounts.items()):
            live_ids = {
                str(bot_uid).strip(),
                str(live.get("uid") or "").strip(),
                str(live.get("actual_uid") or "").strip(),
                str(live.get("display_uid") or "").strip(),
                str(live.get("auth_uid") or "").strip(),
            }
            live_token = str(live.get("token") or "").strip()
            if live_token:
                live_ids.add(live_token[:20])
            if requested not in live_ids:
                continue

            live_owner = str(live.get("owner") or "").strip()
            live_auth = str(live.get("auth_uid") or "").strip()
            live_token_prefix = live_token[:20] if live_token else ""
            for acc in user.get("accounts", []):
                stored_uid = str(acc.get("uid") or "").strip()
                stored_token = str(acc.get("token") or "").strip()
                stored_prefix = stored_token[:20] if stored_token else ""
                if (live_owner == str(username) or
                        (stored_uid and stored_uid == live_auth) or
                        (stored_prefix and stored_prefix == live_token_prefix)):
                    selected = acc
                    if not live.get("owner"):
                        live["owner"] = username
                    break
            if selected is not None:
                break

    if selected is None:
        return None, set(), None

    stored_uid = str(selected.get("uid") or "").strip()
    stored_token = str(selected.get("token") or "").strip()
    if stored_uid:
        aliases.add(stored_uid)
    if stored_token:
        aliases.add(stored_token[:20])
        aliases.add(f"tok_{stored_token[:20]}")

    # Collect every live/native alias belonging to this stored account.
    for bot_uid, live in list(bot_state.accounts.items()):
        live_ids = {
            str(bot_uid).strip(),
            str(live.get("uid") or "").strip(),
            str(live.get("actual_uid") or "").strip(),
            str(live.get("display_uid") or "").strip(),
            str(live.get("auth_uid") or "").strip(),
        }
        live_token = str(live.get("token") or "").strip()
        if live_token:
            live_ids.add(live_token[:20])
        if (str(live.get("owner") or "").strip() == str(username) or
                (stored_uid and str(live.get("auth_uid") or "").strip() == stored_uid) or
                (stored_token and live_token[:20] == stored_token[:20])):
            aliases.update(x for x in live_ids if x)
            if not live.get("owner"):
                live["owner"] = username

    # Expand through existing runtime maps as a final compatibility layer.
    expanded = set(aliases)
    for a in list(aliases):
        try:
            expanded.update(bot_state._runtime_candidates(a))
        except Exception:
            pass
    return selected, {x for x in expanded if x}, stored_uid or (stored_token[:20] if stored_token else requested)


async def api_user_remove_account(request: web.Request) -> web.Response:
    err = await _require_user(request)
    if err: return err
    try:
        sess = await get_session(_get_sid(request))
        username = sess["username"]
        data = await request.json()
        acc_id = str(data.get("account_id", "")).strip()
        if not acc_id:
            return _json_error("account_id required")

        selected, aliases, stored_id = await _resolve_user_account_runtime(username, acc_id)
        if selected is None:
            return _json_error("Account not found")

        # HARD STOP FIRST: cancel every resolved runtime alias before deleting persistence.
        runtime_cancelled = 0
        for alias in sorted(aliases):
            runtime_cancelled += bot_state.cancel_account_runtime(alias, "delete")

        r = await remove_account_from_user(username, stored_id)
        if "status" not in r:
            return _json_error(r.get("error", "Account not found"))

        for alias in list(aliases):
            bot_state.accounts.pop(alias, None)
        bot_state.clear_account_runtime_maps(stored_id)
        for alias in list(aliases):
            bot_state.clear_account_runtime_maps(alias)
        bot_state.recalc_totals()
        bot_state.log(f"[DELETE SUCCESS] {username} | UID {acc_id} | runtime_cancelled={runtime_cancelled}", "success", acc_id)

        cb = bot_state.refresh_callbacks.get("on_account_deleted")
        if cb:
            try: asyncio.create_task(cb(list(aliases)))
            except Exception: pass
        return web.json_response({"status": "ok", "runtime_cancelled": runtime_cancelled})
    except Exception as e:
        bot_state.log(f"[DELETE FAILED] {e}", "error")
        return _json_error(str(e), 500)


async def api_user_pause_account(request: web.Request) -> web.Response:
    err = await _require_user(request)
    if err: return err
    try:
        sess = await get_session(_get_sid(request))
        username = sess["username"]
        data = await request.json()
        acc_id = str(data.get("account_id", "")).strip()
        if not acc_id:
            return _json_error("account_id required")

        selected, aliases, stored_id = await _resolve_user_account_runtime(username, acc_id)
        if selected is None:
            return _json_error("Account not found", 404)

        # Toggle using the displayed/native ID, then mirror state to all aliases.
        paused = bot_state.toggle_pause(acc_id)
        for alias in aliases:
            if alias == acc_id:
                continue
            try:
                if bot_state.is_paused(alias) != paused:
                    bot_state.toggle_pause(alias)
            except Exception:
                pass
        bot_state.log(f"[PAUSE] {username} | UID {acc_id} | paused={paused}", "warning" if paused else "success", acc_id)
        return web.json_response({"status": "ok", "is_paused": paused})
    except Exception as e:
        return _json_error(str(e), 500)


async def api_user_pause_all(request: web.Request) -> web.Response:
    err = await _require_user(request)
    if err: return err
    try:
        sess = await get_session(_get_sid(request))
        username = sess["username"]
        user = await get_user(username)
        if not user:
            return _json_error("User not found", 404)
        ids = []
        for acc in user.get("accounts", []):
            selected, aliases, stored_id = await _resolve_user_account_runtime(
                username, str(acc.get("uid") or acc.get("token", "")[:20]))
            if selected is not None:
                ids.append((stored_id, aliases))
        any_active = any(not bot_state.is_paused(a) for _, aliases in ids for a in aliases)
        desired = any_active
        for stored_id, aliases in ids:
            for alias in aliases or {stored_id}:
                if bot_state.is_paused(alias) != desired:
                    bot_state.toggle_pause(alias)
        bot_state.log(f"[PAUSE ALL] {username} | paused={desired}", "warning" if desired else "success")
        return web.json_response({"status": "ok", "all_paused": desired})
    except Exception as e:
        return _json_error(str(e), 500)


async def api_user_restart_account(request: web.Request) -> web.Response:
    err = await _require_user(request)
    if err: return err
    try:
        sess = await get_session(_get_sid(request))
        username = sess["username"]
        data = await request.json()
        acc_id = str(data.get("account_id", "")).strip()
        if not acc_id:
            return _json_error("account_id required")

        selected, aliases, stored_id = await _resolve_user_account_runtime(username, acc_id)
        if selected is None:
            return _json_error("Account not found", 404)

        for alias in sorted(aliases):
            bot_state.cancel_account_runtime(alias, "restart")
            bot_state.paused_accounts.discard(alias)
        cb = bot_state.refresh_callbacks.get("on_restart_account")
        if cb:
            # Restart callback needs the persisted login/auth UID when the card shows game UID.
            await cb(stored_id)
        bot_state.log(f"[RESTART] {username} | UID {acc_id} | stored_id={stored_id}", "success", acc_id)
        return web.json_response({"status": "ok"})
    except Exception as e:
        bot_state.log(f"[RESTART FAILED] {e}", "error")
        return _json_error(str(e), 500)


async def api_user_refresh(request: web.Request) -> web.Response:
    err = await _require_user(request)
    if err: return err
    try:
        sess = await get_session(_get_sid(request))
        username = sess["username"]
        data = await request.json()
        acc_id = str(data.get("account_id", "")).strip()
        if not acc_id:
            return _json_error("account_id required")

        user = await get_user(username)
        if not user:
            return _json_error("User not found", 404)

        runtime_ids = bot_state._runtime_candidates(acc_id) or {acc_id}
        candidates = {acc_id}
        matched = False
        for acc in user.get("accounts", []):
            uid_val = str(acc.get("uid") or "")
            token_val = str(acc.get("token") or "")
            stored_ids = {x for x in (uid_val, token_val[:20]) if x}
            if stored_ids & runtime_ids or acc_id in stored_ids:
                matched = True
                if uid_val: candidates.add(uid_val)
                if token_val:
                    candidates.add(token_val[:20])
                    candidates.add(f"tok_{token_val[:20]}")
                break
        if not matched:
            return _json_error("Account not found", 404)

        for bot_uid, ba in bot_state.accounts.items():
            live_ids = {str(bot_uid), str(ba.get("actual_uid", "")),
                        str(ba.get("display_uid", "")), str(ba.get("auth_uid", "")),
                        str(ba.get("uid", "")), str(ba.get("token", ""))[:16]}
            if live_ids & runtime_ids:
                candidates.update(x for x in live_ids if x)

        cb = bot_state.refresh_callbacks.get("on_refresh_account")
        if cb:
            for c in candidates:
                if c:
                    try: asyncio.create_task(cb(c))
                    except Exception: pass

        await asyncio.sleep(1.0)
        # Return the fresh dashboard representation instead of an empty response.
        result_accounts = _build_user_accounts(username, user)
        result = next((a for a in result_accounts
                       if str(a.get("actual_uid") or a.get("uid")) in runtime_ids
                       or str(a.get("user_input_uid")) in runtime_ids), None)
        return web.json_response({"status": "ok", "account": result})
    except Exception as e:
        return _json_error(str(e), 500)


# ==================== PUBLIC API ====================
async def api_public_popup(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok", "popup": _load_popup_config()})


async def api_public_stats(request: web.Request) -> web.Response:
    accounts_data = list(bot_state.accounts.values())
    accounts_data.sort(key=lambda x: x.get("gained_exp", 0), reverse=True)
    uptime_sec = max(1, int(time.time() - bot_state.start_time))
    exp_per_hour = int((bot_state.total_gained_exp / uptime_sec) * 3600)
    return web.json_response({
        "total_accounts": len(bot_state.accounts),
        "total_matches": bot_state.total_matches,
        "total_matches_started": bot_state.total_matches_started,
        "total_gained_exp": bot_state.total_gained_exp,
        "exp_per_hour": exp_per_hour,
        "accounts": accounts_data,
        "logs": bot_state.logs[-80:],
        "uptime": uptime_sec,
    })


# ==================== SERVER START ====================
async def start_web_dashboard(host: str = "0.0.0.0", port: int = 20331):
    app = web.Application(client_max_size=4 * 1024 * 1024)

    # pages
    app.router.add_get("/", handle_root)
    app.router.add_get("/payment", handle_payment_page)
    app.router.add_get("/payment-files/{name}", handle_payment_file)
    app.router.add_get("/api/public/payment", api_public_payment)
    app.router.add_post("/api/payment/submit", api_submit_payment)
    app.router.add_get("/api/admin/payment-settings", api_admin_payment_settings)
    app.router.add_post("/api/admin/payment-settings", api_admin_save_payment_settings)
    app.router.add_post("/api/admin/payment-qr", api_admin_upload_qr)
    app.router.add_get("/api/admin/payment-requests", api_admin_payment_requests)
    app.router.add_post("/api/admin/payment-action", api_admin_payment_action)
    app.router.add_get("/login", handle_login_page)
    app.router.add_get("/admin-login", handle_admin_login_page)
    app.router.add_get("/admin", handle_admin_page)
    app.router.add_get("/dashboard", handle_dashboard_page)

    # auth
    app.router.add_post("/api/login", api_user_login)
    app.router.add_post("/api/admin/login", api_admin_login)
    app.router.add_post("/api/logout", api_logout)

    # admin
    app.router.add_post("/api/admin/create-user", api_admin_create_user)
    app.router.add_get("/api/admin/users", api_admin_list_users)
    app.router.add_post("/api/admin/delete-user", api_admin_delete_user)
    app.router.add_post("/api/admin/extend-user", api_admin_extend_user)
    app.router.add_get("/api/admin/get-popup", api_admin_get_popup)
    app.router.add_post("/api/admin/save-popup", api_admin_save_popup)

    # user
    app.router.add_get("/api/user/stats", api_user_stats)
    app.router.add_post("/api/user/add-account", api_user_add_account)
    app.router.add_post("/api/user/remove-account", api_user_remove_account)
    app.router.add_post("/api/user/pause-account", api_user_pause_account)
    app.router.add_post("/api/user/pause-all", api_user_pause_all)
    app.router.add_post("/api/user/restart-account", api_user_restart_account)
    app.router.add_post("/api/user/refresh", api_user_refresh)

    # public
    app.router.add_get("/api/public/popup", api_public_popup)
    app.router.add_get("/api/public/stats", api_public_stats)

    # legacy aliases used by older dashboard JS
    app.router.add_get("/api/stats", api_public_stats)
    app.router.add_post("/api/account/add", api_user_add_account)
    app.router.add_post("/api/account/delete", api_user_remove_account)
    app.router.add_post("/api/account/refresh", api_user_refresh)
    app.router.add_post("/api/account/pause", api_user_pause_account)
    app.router.add_post("/api/account/restart", api_user_restart_account)
    app.router.add_post("/api/account/pause_all", _alias_pause_all)
    app.router.add_post("/api/logs/clear", _alias_clear_logs)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    print(f"\033[92m[+] Web Dashboard running on http://localhost:{port}\033[0m")
    return runner


# ---------- legacy handlers ----------
async def _alias_pause(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        uid = str(data.get("uid", "")).strip()
        if not uid:
            return _json_error("UID is required")
        is_paused = bot_state.toggle_pause(uid)
        return web.json_response({"status": "ok", "is_paused": is_paused})
    except Exception as e:
        return _json_error(str(e), 500)


async def _alias_pause_all(request: web.Request) -> web.Response:
    try:
        paused = bot_state.toggle_pause_all()
        return web.json_response({"status": "ok", "all_paused": paused})
    except Exception as e:
        return _json_error(str(e), 500)


async def _alias_clear_logs(request: web.Request) -> web.Response:
    bot_state.logs.clear()
    return web.json_response({"status": "ok"})