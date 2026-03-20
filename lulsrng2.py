"""
LULS RNG 2 (online-first, one-file build)
Run:
  Windows: py lulsrng2.py
  macOS/Linux: python3 lulsrng2.py
"""

import sys
import subprocess


def _ensure(pkg: str, import_name: str = ""):
    try:
        __import__(import_name or pkg)
    except Exception:
        print(f"Installing {pkg}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])


_ensure("customtkinter")

import os
import ssl
import json
import time
import queue
import random
import hashlib
import threading
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox

try:
    import certifi
except Exception:
    certifi = None


# -----------------------------------------------------------------------------
# Config / Theme
# -----------------------------------------------------------------------------
APP_NAME = "LULS RNG 2"
CFG_FILE = os.path.join(os.path.dirname(__file__), "online_client_config.json")
LOCAL_SAVE = os.path.join(os.path.dirname(__file__), "lulsrng2_local_save.json")
ERROR_LOG = os.path.join(os.path.dirname(__file__), "lulsrng2_error.log")
DEFAULT_API_BASE = "https://render-47ff.onrender.com"
DEFAULT_API_TOKEN = "04ea193ec0537156f012b0f3a82f86a8"

WHITE = "#ffffff"
BG = "#eff6ff"
BG2 = "#dbeafe"
CARD = "#ffffff"
TEXT = "#0f172a"
MUTED = "#64748b"
ACCENT = "#0284c7"
ACCENT2 = "#0369a1"
PINK = "#ec4899"
RED = "#ef4444"
GREEN = "#16a34a"
AMBER = "#f59e0b"
BORDER = "#dbe2ef"

PITY_SOFT = 25
PITY_HARD = 35
LUCKY_SPAN = 10
LUCKY_BUY_COST = 300
BATTLE_SEND_COOLDOWN_SEC = 6
BATTLE_ACTION_COOLDOWN_SEC = 2
MAX_WAGER_FACTOR = 0.25
ROLL_CHEST_INTERVAL = 25
SLOW_TICK_MS = 400
HEARTBEAT_MS = 3000
LIVE_REFRESH_MS = 2500


def log_line(msg: str):
    ts = datetime.now().isoformat(timespec="seconds")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(ERROR_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def log_exc(prefix: str, exc: BaseException):
    log_line(f"{prefix}: {exc}")
    try:
        with open(ERROR_LOG, "a", encoding="utf-8") as f:
            f.write("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)) + "\n")
    except Exception:
        pass


def load_cloud_config() -> Tuple[str, str]:
    env_base = os.getenv("LULSRNG_API_BASE", "").strip()
    env_tok = os.getenv("LULSRNG_API_TOKEN", "").strip()
    if env_base:
        return env_base, env_tok
    try:
        with open(CFG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f) or {}
        base = str(cfg.get("api_base", "")).strip()
        tok = str(cfg.get("api_token", "")).strip()
        if base:
            return base, tok
    except Exception:
        pass
    return DEFAULT_API_BASE, DEFAULT_API_TOKEN


# -----------------------------------------------------------------------------
# Gameplay model
# -----------------------------------------------------------------------------
RARITY_ORDER = ["Common", "Uncommon", "Rare", "Epic", "Legendary", "Mythic", "Divine"]
RARITY_COLOR = {
    "Common": "#94a3b8",
    "Uncommon": "#22c55e",
    "Rare": "#3b82f6",
    "Epic": "#a855f7",
    "Legendary": "#f59e0b",
    "Mythic": "#ef4444",
    "Divine": "#06b6d4",
}
RARITY_WEIGHT = {
    "Common": 6200,
    "Uncommon": 2500,
    "Rare": 1000,
    "Epic": 240,
    "Legendary": 55,
    "Mythic": 5,
    "Divine": 1,
}
RARITY_POWER = {
    "Common": 1,
    "Uncommon": 3,
    "Rare": 8,
    "Epic": 20,
    "Legendary": 55,
    "Mythic": 140,
    "Divine": 320,
}
RARITY_COINS = {
    "Common": 1,
    "Uncommon": 2,
    "Rare": 5,
    "Epic": 13,
    "Legendary": 40,
    "Mythic": 130,
    "Divine": 420,
}
TITLES = {
    "Common": ["Gatekeeper", "Dust Walker", "Stone Foot", "Plain Blade", "Drift Soul", "Mild Hero"],
    "Uncommon": ["Bog Walker", "Night Stalker", "Cursed Coin", "Green Fang", "Echo Scout", "Iron Skin"],
    "Rare": ["Void Seeker", "Frost Herald", "Thunder Step", "Stormcaller", "Ash Hunter", "Moon Razor"],
    "Epic": ["Soulreaper", "Aether Weave", "Ruinbringer", "Chaos Bloom", "Phantom King", "Flux Guard"],
    "Legendary": ["Dragon Sovereign", "Eternal Flame", "Starshatter", "The Undying", "Doomforged", "Skybreaker"],
    "Mythic": ["Abyssal God", "Null Sovereign", "Heavenbreaker", "Cosmos Ender", "Singularity", "First Light"],
    "Divine": ["Astral Archon", "Crown of Aeons", "Paragon Zero", "Heaven's Verdict", "Omega Saint", "Infinite Oracle"],
}


def xp_needed(level: int) -> int:
    return int(110 * (level ** 1.45))


@dataclass
class State:
    level: int = 1
    xp: int = 0
    coins: int = 0
    shards: int = 0
    total_rolls: int = 0
    pity: int = 0
    rebirths: int = 0
    pvp_wins: int = 0
    pvp_losses: int = 0
    lucky_rolls: int = 0
    lucky_rolls_remaining: int = 0
    daily_claim_date: str = ""
    daily_streak: int = 0
    roll_chests_claimed: int = 0
    pvp_streak: int = 0
    total_boss_wins: int = 0
    total_rift_wins: int = 0
    total_wins: int = 0
    total_losses: int = 0
    updated_at_ts: float = 0.0
    best_rarity: str = "Common"
    inventory: Dict[str, int] = field(default_factory=dict)
    collection: List[str] = field(default_factory=list)
    battle_titles: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        equipped = self.battle_titles[0] if self.battle_titles else None
        return {
            "level": self.level,
            "xp": self.xp,
            "coins": self.coins,
            "shards": self.shards,
            "total_rolls": self.total_rolls,
            "pity": self.pity,
            "pity_counter": self.pity,
            "rebirths": self.rebirths,
            "pvp_wins": self.pvp_wins,
            "pvp_losses": self.pvp_losses,
            "lucky_rolls": self.lucky_rolls,
            "lucky_rolls_remaining": self.lucky_rolls_remaining,
            "daily_claim_date": self.daily_claim_date,
            "daily_streak": self.daily_streak,
            "roll_chests_claimed": self.roll_chests_claimed,
            "pvp_streak": self.pvp_streak,
            "total_boss_wins": self.total_boss_wins,
            "total_rift_wins": self.total_rift_wins,
            "total_wins": self.total_wins,
            "total_losses": self.total_losses,
            "updated_at_ts": self.updated_at_ts,
            "best_rarity": self.best_rarity,
            "highest_rarity_pulled": self.best_rarity,
            "equipped_title": equipped,
            "equipped_rarity": title_rarity(equipped) if equipped else None,
            "inventory": self.inventory,
            "collection": self.collection,
            "battle_titles": self.battle_titles,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "State":
        s = cls()
        if not isinstance(d, dict):
            return s
        s.level = max(1, int(d.get("level", 1)))
        s.xp = max(0, int(d.get("xp", 0)))
        s.coins = max(0, int(d.get("coins", 0)))
        s.shards = max(0, int(d.get("shards", 0)))
        s.total_rolls = max(0, int(d.get("total_rolls", 0)))
        s.pity = max(0, int(d.get("pity", d.get("pity_counter", 0))))
        s.rebirths = max(0, int(d.get("rebirths", 0)))
        s.pvp_wins = max(0, int(d.get("pvp_wins", 0)))
        s.pvp_losses = max(0, int(d.get("pvp_losses", 0)))
        s.lucky_rolls = max(0, int(d.get("lucky_rolls", 0)))
        s.lucky_rolls_remaining = max(0, int(d.get("lucky_rolls_remaining", 0)))
        s.daily_claim_date = str(d.get("daily_claim_date", "") or "")
        s.daily_streak = max(0, int(d.get("daily_streak", 0)))
        s.roll_chests_claimed = max(0, int(d.get("roll_chests_claimed", 0)))
        s.pvp_streak = max(0, int(d.get("pvp_streak", 0)))
        s.total_boss_wins = max(0, int(d.get("total_boss_wins", 0)))
        s.total_rift_wins = max(0, int(d.get("total_rift_wins", 0)))
        s.total_wins = max(0, int(d.get("total_wins", 0)))
        s.total_losses = max(0, int(d.get("total_losses", 0)))
        try:
            s.updated_at_ts = float(d.get("updated_at_ts", d.get("updated_at", 0.0)) or 0.0)
        except Exception:
            s.updated_at_ts = 0.0

        br = str(d.get("best_rarity", d.get("highest_rarity_pulled", "Common")))
        s.best_rarity = br if br in RARITY_ORDER else "Common"

        inv = d.get("inventory", {}) or {}
        parsed_inv = {}
        for k, v in inv.items():
            try:
                cnt = int(v)
            except Exception:
                continue
            if cnt > 0:
                parsed_inv[str(k)] = cnt
        s.inventory = parsed_inv

        col = d.get("collection", []) or []
        s.collection = [str(x) for x in col]

        bt = d.get("battle_titles", []) or []
        s.battle_titles = [str(x) for x in bt][:3]
        return s


class Engine:
    def __init__(self, st: Optional[State] = None):
        self.s = st or State()

    def save_local(self, touch: bool = True):
        if touch:
            self.s.updated_at_ts = time.time()
        try:
            with open(LOCAL_SAVE, "w", encoding="utf-8") as f:
                json.dump(self.s.to_dict(), f, indent=2)
        except Exception as e:
            log_exc("local save failed", e)

    @staticmethod
    def load_local() -> State:
        try:
            with open(LOCAL_SAVE, "r", encoding="utf-8") as f:
                return State.from_dict(json.load(f))
        except Exception:
            return State()

    def _best_rarity_update(self, rarity: str):
        if RARITY_ORDER.index(rarity) > RARITY_ORDER.index(self.s.best_rarity):
            self.s.best_rarity = rarity

    def _gain_xp(self, amount: int):
        self.s.xp += max(0, amount)
        while self.s.xp >= xp_needed(self.s.level):
            self.s.xp -= xp_needed(self.s.level)
            self.s.level += 1

    def _weights(self) -> Dict[str, float]:
        shift = 1.0 + self.s.rebirths * 0.16
        w = dict(RARITY_WEIGHT)
        w["Common"] *= max(0.38, 1.0 - self.s.rebirths * 0.08)
        w["Uncommon"] *= max(0.55, 1.0 - self.s.rebirths * 0.05)
        for r in ["Rare", "Epic", "Legendary", "Mythic", "Divine"]:
            w[r] *= shift

        if self.s.pity >= PITY_SOFT:
            w["Epic"] *= 4.0
            w["Legendary"] *= 3.5
            w["Mythic"] *= 2.2
        if self.s.pity >= PITY_HARD:
            w["Legendary"] *= 9.0
            w["Mythic"] *= 7.0
            w["Divine"] *= 5.0

        if self.s.lucky_rolls_remaining > 0:
            w["Common"] *= 0.38
            w["Uncommon"] *= 0.55
            w["Rare"] *= 1.75
            w["Epic"] *= 2.8
            w["Legendary"] *= 3.0
            w["Mythic"] *= 2.8
            w["Divine"] *= 2.0
        return w

    def roll(self) -> Tuple[str, str, int, bool, str]:
        pity_proc = self.s.pity >= PITY_HARD
        if pity_proc:
            rarity = random.choices(["Legendary", "Mythic", "Divine"], weights=[890, 100, 10], k=1)[0]
        else:
            w = self._weights()
            rarities = list(w.keys())
            rarity = random.choices(rarities, weights=[w[r] for r in rarities], k=1)[0]

        title = random.choice(TITLES[rarity])
        self.s.total_rolls += 1

        if RARITY_ORDER.index(rarity) >= RARITY_ORDER.index("Epic"):
            self.s.pity = 0
        else:
            self.s.pity += 1

        if self.s.lucky_rolls_remaining > 0:
            self.s.lucky_rolls_remaining -= 1

        self.s.inventory[title] = self.s.inventory.get(title, 0) + 1
        if title not in self.s.collection:
            self.s.collection.append(title)

        gain = RARITY_COINS[rarity] + self.s.rebirths + (self.s.level // 10)
        if self.s.lucky_rolls_remaining > 0:
            gain += 1
        self.s.coins += gain
        if RARITY_ORDER.index(rarity) >= RARITY_ORDER.index("Rare"):
            self.s.shards += 1 + (1 if rarity in ["Legendary", "Mythic"] else 0)

        chest_msg = ""
        chests_unlocked = self.s.total_rolls // ROLL_CHEST_INTERVAL
        if chests_unlocked > self.s.roll_chests_claimed:
            self.s.roll_chests_claimed += 1
            chest_coins = 120 + self.s.level * 3 + self.s.rebirths * 20
            self.s.coins += chest_coins
            if self.s.roll_chests_claimed % 4 == 0:
                self.s.lucky_rolls += 1
                chest_msg = f"Chest +{chest_coins}c +1 Lucky"
            else:
                chest_msg = f"Chest +{chest_coins}c"
        self._gain_xp(8 + RARITY_POWER[rarity])
        self._best_rarity_update(rarity)
        self.save_local()
        return title, rarity, gain, pity_proc, chest_msg

    def best_three_titles(self) -> List[str]:
        owned = [(t, c) for t, c in self.s.inventory.items() if c > 0]
        if not owned:
            return []
        owned.sort(key=lambda tc: (RARITY_ORDER.index(title_rarity(tc[0])), tc[1]), reverse=True)
        return [t for t, _ in owned[:3]]

    def get_battle_titles_for_pvp(self) -> List[str]:
        valid = [t for t in (self.s.battle_titles or []) if self.s.inventory.get(t, 0) > 0]
        if valid:
            return valid[:3]
        return self.best_three_titles()[:3]

    def set_best_three(self):
        self.s.battle_titles = self.best_three_titles()[:3]
        self.save_local()

    def activate_lucky(self) -> Tuple[bool, str]:
        if self.s.lucky_rolls_remaining > 0:
            return False, f"Lucky already active ({self.s.lucky_rolls_remaining} rolls left)."
        if self.s.lucky_rolls > 0:
            self.s.lucky_rolls -= 1
            self.s.lucky_rolls_remaining = LUCKY_SPAN
            self.save_local()
            return True, f"Lucky aura active for {LUCKY_SPAN} rolls."
        return False, "No Lucky charges. Buy one in Shop for 300 coins."

    def rebirth_cost(self) -> int:
        return 8000 + self.s.rebirths * 3500

    def rebirth(self) -> Tuple[bool, str]:
        if self.s.level < 25:
            return False, "Need level 25+."
        if self.s.coins < self.rebirth_cost():
            return False, "Not enough coins."
        if RARITY_ORDER.index(self.s.best_rarity) < RARITY_ORDER.index("Legendary"):
            return False, "Need Legendary+ before rebirth."
        keep_rebirths = self.s.rebirths + 1
        keep_lucky = self.s.lucky_rolls + 1
        self.s = State(rebirths=keep_rebirths, coins=350 * keep_rebirths, lucky_rolls=keep_lucky)
        self.save_local()
        return True, f"Rebirth complete. Rebirths: {keep_rebirths}. Lucky bank +1."

    def claim_daily(self) -> Tuple[bool, str]:
        today = datetime.now().strftime("%Y-%m-%d")
        if self.s.daily_claim_date == today:
            return False, "Daily already claimed today."
        prev = self.s.daily_claim_date
        streak = 1
        if prev:
            try:
                delta = (datetime.strptime(today, "%Y-%m-%d") - datetime.strptime(prev, "%Y-%m-%d")).days
                if delta == 1:
                    streak = min(30, self.s.daily_streak + 1)
            except Exception:
                streak = 1
        self.s.daily_streak = streak
        self.s.daily_claim_date = today
        coins = 300 + streak * 40 + self.s.level * 5
        shards = 1 + (1 if streak % 3 == 0 else 0)
        self.s.coins += coins
        self.s.shards += shards
        if streak % 7 == 0:
            self.s.lucky_rolls += 1
            bonus = " +1 Lucky"
        else:
            bonus = ""
        self.save_local()
        return True, f"Daily claimed: +{coins}c +{shards}s (streak {streak}){bonus}"


def title_rarity(title: Optional[str]) -> str:
    if not title:
        return "Common"
    for r, arr in TITLES.items():
        if title in arr:
            return r
    return "Common"


def title_power(title: str) -> int:
    r = title_rarity(title)
    base = RARITY_POWER[r]
    return int(base * random.uniform(0.86, 1.14))


def pvp_simulate(my_titles: List[str], opp_titles: List[str]) -> dict:
    rounds = []
    my_score = 0
    opp_score = 0
    duel_len = min(3, max(len(my_titles), len(opp_titles)))
    for i in range(duel_len):
        mt = my_titles[i] if i < len(my_titles) else random.choice(my_titles)
        ot = opp_titles[i] if i < len(opp_titles) else random.choice(opp_titles)
        mp = title_power(mt) + random.randint(0, 18)
        op = title_power(ot) + random.randint(0, 18)
        winner = "me" if mp >= op else "opp"
        if winner == "me":
            my_score += 1
        else:
            opp_score += 1
        rounds.append({
            "my_title": mt,
            "my_rarity": title_rarity(mt),
            "my_power": mp,
            "opp_title": ot,
            "opp_rarity": title_rarity(ot),
            "opp_power": op,
            "winner": winner,
        })
    if my_score == opp_score:
        winner = "me" if sum(r["my_power"] for r in rounds) >= sum(r["opp_power"] for r in rounds) else "opp"
    else:
        winner = "me" if my_score > opp_score else "opp"
    return {"rounds": rounds, "my_score": my_score, "opp_score": opp_score, "winner": winner}


# -----------------------------------------------------------------------------
# Online API client (Render RPC)
# -----------------------------------------------------------------------------
class CloudApi:
    def __init__(self, base_url: str, token: str):
        self.base_url = (base_url or "").strip().rstrip("/")
        self.token = token or ""
        self.connected = False
        self.last_error = ""
        self._next_reconnect = 0.0
        self._backoff = 2.0
        self._tls_unverified = False
        self.db_connected: Optional[bool] = None
        self.db_error: str = ""
        self._ssl = self._make_ssl()
        self.reconnect(force=True)

    def _make_ssl(self):
        try:
            if certifi:
                return ssl.create_default_context(cafile=certifi.where())
        except Exception:
            pass
        return ssl.create_default_context()

    def _open(self, req: Request, timeout: int):
        try:
            return urlopen(req, timeout=timeout, context=self._ssl)
        except Exception as e:
            m = str(e).lower()
            if ("certificate_verify_failed" in m or "certificate verify failed" in m) and not self._tls_unverified:
                self._ssl = ssl._create_unverified_context()
                self._tls_unverified = True
                # Quiet fallback: compatibility TLS is expected on some school/home setups.
                return urlopen(req, timeout=timeout, context=self._ssl)
            raise

    def reconnect(self, force: bool = False) -> bool:
        now = time.time()
        if self.connected and not force:
            return True
        if (not force) and now < self._next_reconnect:
            return False
        if not self.base_url:
            self.last_error = "Missing API base URL"
            self.connected = False
            return False
        req = Request(f"{self.base_url}/health", headers={"X-API-Token": self.token}, method="GET")
        try:
            with self._open(req, timeout=8) as resp:
                if resp.status == 200:
                    try:
                        body = json.loads(resp.read().decode("utf-8") or "{}")
                        self.db_connected = bool(body.get("db_connected", False))
                        self.db_error = str(body.get("db_error", "") or "")
                    except Exception:
                        self.db_connected = None
                        self.db_error = ""
                    self.connected = True
                    self.last_error = ""
                    self._backoff = 2.0
                    self._next_reconnect = 0.0
                    return True
        except Exception as e:
            self.last_error = str(e)
        self.connected = False
        self._next_reconnect = now + self._backoff
        self._backoff = min(40.0, self._backoff * 1.8)
        return False

    def _decode(self, obj):
        if isinstance(obj, dict):
            if "__player_state__" in obj:
                return self._decode(obj.get("__player_state__"))
            return {k: self._decode(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._decode(v) for v in obj]
        return obj

    def rpc(self, method: str, *args, **kwargs):
        if not self.connected and not self.reconnect():
            return None
        payload = json.dumps({"method": method, "args": list(args), "kwargs": kwargs}).encode("utf-8")
        req = Request(
            f"{self.base_url}/rpc",
            data=payload,
            headers={"Content-Type": "application/json", "X-API-Token": self.token},
            method="POST",
        )
        try:
            with self._open(req, timeout=14) as resp:
                body = json.loads(resp.read().decode("utf-8") or "{}")
                self.connected = True
                if not body.get("ok", False):
                    self.last_error = str(body.get("error", "rpc error"))
                    return None
                self.last_error = ""
                return self._decode(body.get("result"))
        except HTTPError as e:
            try:
                raw = e.read().decode("utf-8")
                parsed = json.loads(raw)
                msg = parsed.get("error") or parsed.get("detail") or raw
            except Exception:
                msg = str(e)
            self.last_error = f"HTTP {e.code}: {msg}"
            self.connected = True
            return None
        except (URLError, TimeoutError, ValueError) as e:
            self.last_error = str(e)
            self.connected = False
            return None
        except Exception as e:
            self.last_error = str(e)
            self.connected = False
            return None


# -----------------------------------------------------------------------------
# Async helper
# -----------------------------------------------------------------------------
class AsyncBus:
    def __init__(self):
        self.q = queue.Queue()

    def run(self, fn, on_done):
        def worker():
            ok = True
            res = None
            try:
                res = fn()
            except Exception as e:
                ok = False
                res = e
            self.q.put((on_done, ok, res))
        threading.Thread(target=worker, daemon=True).start()


# -----------------------------------------------------------------------------
# UI pieces
# -----------------------------------------------------------------------------
class LoginWindow(ctk.CTkToplevel):
    def __init__(self, master, api: CloudApi, done_cb):
        super().__init__(master)
        self.api = api
        self.done_cb = done_cb
        self.title("Login - LULS RNG 2")
        self.geometry("430x330")
        self.resizable(False, False)
        self.configure(fg_color=BG)

        card = ctk.CTkFrame(self, fg_color=CARD, corner_radius=16, border_width=1, border_color=BORDER)
        card.pack(fill="both", expand=True, padx=18, pady=18)
        ctk.CTkLabel(card, text="LULS RNG 2", text_color=TEXT, font=("Segoe UI", 30, "bold")).pack(pady=(18, 8))
        ctk.CTkLabel(card, text="Online-first with local fallback", text_color=MUTED, font=("Segoe UI", 12)).pack(pady=(0, 12))

        self.user = ctk.CTkEntry(card, width=300, placeholder_text="username", fg_color=WHITE, text_color=TEXT)
        self.user.pack(pady=6)
        self.pw = ctk.CTkEntry(card, width=300, placeholder_text="password", show="*", fg_color=WHITE, text_color=TEXT)
        self.pw.pack(pady=6)
        self.status = ctk.CTkLabel(card, text="", text_color=MUTED)
        self.status.pack(pady=5)

        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(pady=8)
        ctk.CTkButton(row, text="Login", width=120, fg_color=ACCENT, hover_color=ACCENT2, command=self._login).pack(side="left", padx=6)
        ctk.CTkButton(row, text="Register", width=120, fg_color=PINK, hover_color="#db2777", command=self._do_register).pack(side="left", padx=6)
        ctk.CTkButton(card, text="Play Offline", width=252, fg_color=RED, hover_color="#dc2626", command=self._offline).pack(pady=(4, 12))

        self.protocol("WM_DELETE_WINDOW", self._close_all)
        self.grab_set()

    def _close_all(self):
        self.master.destroy()

    def _login(self):
        u = self.user.get().strip()
        p = self.pw.get()
        if not u or not p:
            self.status.configure(text="Enter username/password", text_color=RED)
            return
        result = self.api.rpc("login", u, p)
        if result is None:
            self.status.configure(text=f"Cloud error, using offline login: {self.api.last_error}", text_color=RED)
            self.done_cb(u, None, False)
            self.destroy()
            return
        ok, payload = result
        if ok:
            cloud_state = payload if isinstance(payload, dict) else None
            self.done_cb(u, cloud_state, True)
            self.destroy()
        else:
            self.status.configure(text=str(payload), text_color=RED)

    def _do_register(self):
        u = self.user.get().strip()
        p = self.pw.get()
        if not u or not p:
            self.status.configure(text="Enter username/password", text_color=RED)
            return
        result = self.api.rpc("register", u, p)
        if result is None:
            self.status.configure(text=f"Cloud error: {self.api.last_error}", text_color=RED)
            return
        ok, msg = result
        self.status.configure(text=str(msg), text_color=GREEN if ok else RED)

    def _offline(self):
        self.done_cb("", None, False)
        self.destroy()


class LulsRNG2(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1320x860")
        self.minsize(1080, 740)
        self.configure(fg_color=BG)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.withdraw()

        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

        base, token = load_cloud_config()
        self.api = CloudApi(base, token)
        self.bus = AsyncBus()
        self._closing = False
        self.username = ""
        self.online_enabled = False
        self.engine = Engine(Engine.load_local())
        self._rolling = False
        self._result_text = tk.StringVar(value="Press ROLL")
        self._battle_send_inflight = False
        self._battle_action_busy = False
        self._next_battle_send_at = 0.0
        self._next_battle_action_at = 0.0

        self._build_shell()
        self.after(40, self._drain_async)
        self.after(SLOW_TICK_MS, self._slow_tick)
        self.after(LIVE_REFRESH_MS, self._live_refresh_tick)

        LoginWindow(self, self.api, self._on_auth_done)

    def _state_freshness(self, st: Optional[State], fallback_file_mtime: float = 0.0) -> float:
        if not st:
            return float(fallback_file_mtime or 0.0)
        try:
            return max(float(getattr(st, "updated_at_ts", 0.0) or 0.0), float(fallback_file_mtime or 0.0))
        except Exception:
            return float(fallback_file_mtime or 0.0)

    def _local_file_mtime(self) -> float:
        try:
            return float(os.path.getmtime(LOCAL_SAVE))
        except Exception:
            return 0.0

    def report_callback_exception(self, exc, val, tb):
        try:
            text = "".join(traceback.format_exception(exc, val, tb))
            with open(ERROR_LOG, "a", encoding="utf-8") as f:
                f.write(f"\n[TK CALLBACK] {val}\n{text}\n")
        except Exception:
            pass

    # -------------------------- UI build --------------------------
    def _build_shell(self):
        top = ctk.CTkFrame(self, fg_color=WHITE, corner_radius=0)
        top.pack(fill="x")

        brand = ctk.CTkFrame(top, fg_color="transparent")
        brand.pack(side="left", padx=14, pady=10)
        ctk.CTkLabel(brand, text=APP_NAME, text_color=TEXT, font=("Segoe UI", 28, "bold")).pack(anchor="w")
        self.lbl_live = ctk.CTkLabel(brand, text="Live: initializing systems...", text_color=MUTED, font=("Segoe UI", 12))
        self.lbl_live.pack(anchor="w")

        self.lbl_cloud = ctk.CTkLabel(top, text="Cloud: checking...", text_color=MUTED, font=("Segoe UI", 12, "bold"))
        self.lbl_cloud.pack(side="right", padx=16)

        stats = ctk.CTkFrame(self, fg_color=CARD, corner_radius=14, border_width=1, border_color=BORDER)
        stats.pack(fill="x", padx=12, pady=10)
        self.lbl_user = ctk.CTkLabel(stats, text="User: -", text_color=TEXT, font=("Segoe UI", 12, "bold"))
        self.lbl_user.pack(side="left", padx=12, pady=8)
        self.lbl_lv = ctk.CTkLabel(stats, text="Level 1", text_color=ACCENT, font=("Segoe UI", 12, "bold"))
        self.lbl_lv.pack(side="left", padx=8)
        self.lbl_xp = ctk.CTkLabel(stats, text="XP 0/0", text_color=MUTED)
        self.lbl_xp.pack(side="left", padx=8)
        self.lbl_coins = ctk.CTkLabel(stats, text="Coins 0", text_color=PINK, font=("Segoe UI", 12, "bold"))
        self.lbl_coins.pack(side="left", padx=8)
        self.lbl_best = ctk.CTkLabel(stats, text="Best Common", text_color=MUTED)
        self.lbl_best.pack(side="left", padx=8)
        self.lbl_pity = ctk.CTkLabel(stats, text="Pity 0/35", text_color=RED, font=("Segoe UI", 12, "bold"))
        self.lbl_pity.pack(side="left", padx=8)
        self.lbl_lucky = ctk.CTkLabel(stats, text="Lucky off", text_color=AMBER, font=("Segoe UI", 12, "bold"))
        self.lbl_lucky.pack(side="left", padx=8)

        self.tabs = ctk.CTkTabview(
            self,
            fg_color=BG,
            segmented_button_unselected_color=WHITE,
            segmented_button_unselected_hover_color="#e2e8f0",
            segmented_button_selected_color=ACCENT,
            segmented_button_selected_hover_color=ACCENT2,
            text_color=TEXT,
        )
        self.tabs.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        for name in ["🎲 Roll", "🎒 Inventory", "✨ Rarities", "🛒 Shop", "⚔ PvP", "🌍 Online", "🏆 Leaderboard", "♻ Rebirth", "📈 Stats"]:
            self.tabs.add(name)
        self.tabs.configure(command=self._tab_changed)

        self._build_roll()
        self._build_inventory()
        self._build_rarities()
        self._build_shop()
        self._build_pvp()
        self._build_online()
        self._build_leaderboard()
        self._build_rebirth()
        self._build_stats()

    def _build_roll(self):
        tab = self.tabs.tab("🎲 Roll")

        hero = ctk.CTkFrame(tab, fg_color=BG2, corner_radius=16, border_width=1, border_color=BORDER)
        hero.pack(fill="x", padx=20, pady=(18, 8))
        ctk.CTkLabel(hero, text="Roll Engine", text_color=TEXT, font=("Segoe UI", 24, "bold")).pack(anchor="w", padx=16, pady=(10, 0))
        ctk.CTkLabel(hero, text="Hard pity at 35 guarantees Legendary+ and Lucky aura boosts rates.", text_color=MUTED, font=("Segoe UI", 12)).pack(anchor="w", padx=16, pady=(0, 10))

        card = ctk.CTkFrame(tab, fg_color=WHITE, corner_radius=16, border_width=1, border_color=BORDER)
        card.pack(fill="both", expand=True, padx=20, pady=(8, 20))

        ctk.CTkLabel(card, text="Roll For Title", text_color=TEXT, font=("Segoe UI", 36, "bold")).pack(pady=(34, 10))
        self.lbl_roll_result = ctk.CTkLabel(card, textvariable=self._result_text, text_color=ACCENT, font=("Segoe UI", 30, "bold"))
        self.lbl_roll_result.pack(pady=8)
        self.lbl_roll_sub = ctk.CTkLabel(card, text="Ready", text_color=MUTED, font=("Segoe UI", 14))
        self.lbl_roll_sub.pack(pady=(0, 18))

        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack()
        self.btn_roll = ctk.CTkButton(row, text="ROLL", width=180, height=48, fg_color=PINK, hover_color="#db2777", command=self._roll_once)
        self.btn_roll.pack(side="left", padx=8)
        ctk.CTkButton(row, text="Lucky", width=130, height=48, fg_color=AMBER, hover_color="#d97706", text_color=WHITE, command=self._activate_lucky).pack(side="left", padx=8)
        ctk.CTkButton(row, text="Daily", width=120, height=48, fg_color="#0f766e", hover_color="#115e59", text_color=WHITE, command=self._claim_daily).pack(side="left", padx=8)
        ctk.CTkButton(row, text="Set Best 3", width=150, height=48, fg_color=ACCENT, hover_color=ACCENT2, command=self._set_best_three).pack(side="left", padx=8)
        ctk.CTkButton(row, text="Open PvP", width=130, height=48, fg_color=RED, hover_color="#dc2626", command=lambda: self.tabs.set("⚔ PvP")).pack(side="left", padx=8)

        self.recent_rolls = ctk.CTkScrollableFrame(card, fg_color=BG, corner_radius=10, border_width=1, border_color=BORDER, height=170)
        self.recent_rolls.pack(fill="x", padx=14, pady=14)

    def _build_inventory(self):
        tab = self.tabs.tab("🎒 Inventory")
        self.inv_list = ctk.CTkScrollableFrame(tab, fg_color=WHITE, corner_radius=12, border_width=1, border_color=BORDER)
        self.inv_list.pack(fill="both", expand=True, padx=16, pady=16)

    def _build_rarities(self):
        tab = self.tabs.tab("✨ Rarities")
        wrap = ctk.CTkFrame(tab, fg_color=WHITE, corner_radius=12, border_width=1, border_color=BORDER)
        wrap.pack(fill="both", expand=True, padx=16, pady=16)

        ctk.CTkLabel(wrap, text="Rarity Index", text_color=TEXT, font=("Segoe UI", 28, "bold")).pack(anchor="w", padx=14, pady=(12, 2))
        ctk.CTkLabel(
            wrap,
            text="Base odds, power, and coin values. Live odds below include pity/lucky modifiers.",
            text_color=MUTED,
            font=("Segoe UI", 12),
        ).pack(anchor="w", padx=14, pady=(0, 8))

        self.rarity_meta = ctk.CTkLabel(wrap, text="", text_color=MUTED, font=("Segoe UI", 12, "bold"))
        self.rarity_meta.pack(anchor="w", padx=14, pady=(0, 8))

        table = ctk.CTkScrollableFrame(wrap, fg_color=BG, corner_radius=10, border_width=1, border_color=BORDER)
        table.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.rarity_rows = {}
        total = sum(RARITY_WEIGHT.values()) or 1
        for r in RARITY_ORDER:
            base_pct = (RARITY_WEIGHT[r] / total) * 100.0
            row = ctk.CTkFrame(table, fg_color=WHITE, corner_radius=8, border_width=1, border_color=BORDER)
            row.pack(fill="x", padx=4, pady=4)
            ctk.CTkLabel(row, text=r, text_color=RARITY_COLOR.get(r, TEXT), width=130, font=("Segoe UI", 13, "bold")).pack(side="left", padx=8, pady=8)
            ctk.CTkLabel(row, text=f"Base: {base_pct:.2f}%", text_color=MUTED, width=120).pack(side="left", padx=8)
            ctk.CTkLabel(row, text=f"Power: {RARITY_POWER[r]}", text_color=ACCENT, width=100).pack(side="left", padx=8)
            ctk.CTkLabel(row, text=f"Coins: +{RARITY_COINS[r]}", text_color=PINK, width=110).pack(side="left", padx=8)
            live = ctk.CTkLabel(row, text="Live: -", text_color=TEXT, width=180)
            live.pack(side="right", padx=10)
            self.rarity_rows[r] = live

        self._render_rarities()

    def _render_rarities(self):
        if not hasattr(self, "rarity_rows"):
            return
        s = self.engine.s
        w = self.engine._weights()
        total = float(sum(w.values()) or 1.0)
        mods = []
        if s.pity >= PITY_HARD:
            mods.append("Hard Pity Active")
        elif s.pity >= PITY_SOFT:
            mods.append("Soft Pity Active")
        if s.lucky_rolls_remaining > 0:
            mods.append(f"Lucky Aura {s.lucky_rolls_remaining} left")
        self.rarity_meta.configure(text=f"Current modifiers: {', '.join(mods) if mods else 'None'}")
        for r in RARITY_ORDER:
            pct = (w.get(r, 0.0) / total) * 100.0
            self.rarity_rows[r].configure(text=f"Live: {pct:.2f}%")

    def _build_shop(self):
        tab = self.tabs.tab("🛒 Shop")
        wrap = ctk.CTkFrame(tab, fg_color=WHITE, corner_radius=12, border_width=1, border_color=BORDER)
        wrap.pack(fill="both", expand=True, padx=16, pady=16)
        ctk.CTkLabel(wrap, text="Shop", text_color=TEXT, font=("Segoe UI", 28, "bold")).pack(anchor="w", padx=14, pady=(12, 6))
        ctk.CTkLabel(wrap, text="Fast boosts and utility purchases.", text_color=MUTED).pack(anchor="w", padx=14, pady=(0, 10))

        self.shop_msg = ctk.CTkLabel(wrap, text="", text_color=MUTED)
        self.shop_msg.pack(anchor="w", padx=14, pady=(0, 10))

        card = ctk.CTkFrame(wrap, fg_color=BG, corner_radius=10, border_width=1, border_color=BORDER)
        card.pack(fill="x", padx=12, pady=6)
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=10)
        ctk.CTkLabel(row, text="🎲 Lucky Roll Charge", text_color=AMBER, font=("Segoe UI", 14, "bold")).pack(side="left")
        ctk.CTkLabel(row, text=f"{LUCKY_BUY_COST} coins", text_color=PINK, font=("Segoe UI", 13, "bold")).pack(side="left", padx=12)
        ctk.CTkButton(row, text="Buy", width=100, fg_color=ACCENT, hover_color=ACCENT2, command=self._buy_lucky_charge).pack(side="right")

        card2 = ctk.CTkFrame(wrap, fg_color=BG, corner_radius=10, border_width=1, border_color=BORDER)
        card2.pack(fill="x", padx=12, pady=6)
        row2 = ctk.CTkFrame(card2, fg_color="transparent")
        row2.pack(fill="x", padx=12, pady=10)
        ctk.CTkLabel(row2, text="💎 Shard Pack", text_color=ACCENT, font=("Segoe UI", 14, "bold")).pack(side="left")
        ctk.CTkLabel(row2, text="500 coins", text_color=PINK, font=("Segoe UI", 13, "bold")).pack(side="left", padx=12)
        ctk.CTkButton(row2, text="Buy +3 Shards", width=130, fg_color=ACCENT, hover_color=ACCENT2, command=self._buy_shard_pack).pack(side="right")

    def _buy_lucky_charge(self):
        if self.engine.s.coins < LUCKY_BUY_COST:
            self.shop_msg.configure(text=f"Need {LUCKY_BUY_COST} coins.", text_color=RED)
            return
        self.engine.s.coins -= LUCKY_BUY_COST
        self.engine.s.lucky_rolls += 1
        self.engine.save_local()
        self.shop_msg.configure(text=f"Purchased Lucky Roll charge for {LUCKY_BUY_COST} coins.", text_color=GREEN)
        self._refresh_all()
        if self.online_enabled:
            self._sync_state()

    def _buy_shard_pack(self):
        if self.engine.s.coins < 500:
            self.shop_msg.configure(text="Need 500 coins.", text_color=RED)
            return
        self.engine.s.coins -= 500
        self.engine.s.shards += 3
        self.engine.save_local()
        self.shop_msg.configure(text="Purchased shard pack (+3).", text_color=GREEN)
        self._refresh_all()
        if self.online_enabled:
            self._sync_state()

    def _build_pvp(self):
        tab = self.tabs.tab("⚔ PvP")
        wrap = ctk.CTkFrame(tab, fg_color=WHITE, corner_radius=12, border_width=1, border_color=BORDER)
        wrap.pack(fill="both", expand=True, padx=16, pady=16)
        ctk.CTkLabel(wrap, text="PvP Arena", text_color=TEXT, font=("Segoe UI", 26, "bold")).pack(anchor="w", padx=14, pady=(12, 6))
        self.lbl_bt = ctk.CTkLabel(wrap, text="Battle titles: none", text_color=MUTED)
        self.lbl_bt.pack(anchor="w", padx=14)

        row = ctk.CTkFrame(wrap, fg_color="transparent")
        row.pack(anchor="w", padx=14, pady=10)
        ctk.CTkLabel(row, text="Target:", text_color=TEXT).pack(side="left")
        self.pvp_target = ctk.CTkEntry(row, width=190, fg_color=WHITE, text_color=TEXT)
        self.pvp_target.pack(side="left", padx=8)
        ctk.CTkLabel(row, text="Wager coins:", text_color=TEXT).pack(side="left", padx=(8, 0))
        self.pvp_wager = ctk.CTkEntry(row, width=120, fg_color=WHITE, text_color=TEXT, placeholder_text="0")
        self.pvp_wager.pack(side="left", padx=8)
        self.btn_send_battle = ctk.CTkButton(row, text="Send Battle", fg_color=ACCENT, hover_color=ACCENT2, command=self._send_battle)
        self.btn_send_battle.pack(side="left", padx=6)
        ctk.CTkButton(row, text="Refresh", fg_color=PINK, hover_color="#db2777", command=self._refresh_pvp).pack(side="left", padx=6)
        ctk.CTkButton(row, text="Set Best 3", fg_color=RED, hover_color="#dc2626", command=self._set_best_three).pack(side="left", padx=6)

        pane = ctk.CTkFrame(wrap, fg_color="transparent")
        pane.pack(fill="both", expand=True, padx=12, pady=(4, 8))

        left = ctk.CTkFrame(pane, fg_color=BG, corner_radius=10, border_width=1, border_color=BORDER)
        left.pack(side="left", fill="both", expand=True, padx=(0, 6), pady=4)
        ctk.CTkLabel(left, text="Incoming Requests", text_color=TEXT, font=("Segoe UI", 15, "bold")).pack(anchor="w", padx=10, pady=(8, 4))
        self.pvp_inbox = ctk.CTkScrollableFrame(left, fg_color=BG, corner_radius=8)
        self.pvp_inbox.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        right = ctk.CTkFrame(pane, fg_color=BG, corner_radius=10, border_width=1, border_color=BORDER)
        right.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=4)
        ctk.CTkLabel(right, text="Sent Requests", text_color=TEXT, font=("Segoe UI", 15, "bold")).pack(anchor="w", padx=10, pady=(8, 4))
        self.pvp_sent = ctk.CTkScrollableFrame(right, fg_color=BG, corner_radius=8)
        self.pvp_sent.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        social = ctk.CTkFrame(wrap, fg_color=BG, corner_radius=10, border_width=1, border_color=BORDER)
        social.pack(fill="x", padx=12, pady=(4, 8))
        srow = ctk.CTkFrame(social, fg_color="transparent")
        srow.pack(fill="x", padx=10, pady=(8, 4))
        ctk.CTkLabel(srow, text="Friend:", text_color=TEXT).pack(side="left")
        self.friend_target = ctk.CTkEntry(srow, width=180, fg_color=WHITE, text_color=TEXT)
        self.friend_target.pack(side="left", padx=6)
        ctk.CTkButton(srow, text="Add Friend", width=100, fg_color=ACCENT, hover_color=ACCENT2, command=self._send_friend_request).pack(side="left", padx=6)
        ctk.CTkLabel(srow, text="Trade To:", text_color=TEXT).pack(side="left", padx=(14, 0))
        self.trade_target = ctk.CTkEntry(srow, width=150, fg_color=WHITE, text_color=TEXT)
        self.trade_target.pack(side="left", padx=6)

        trow = ctk.CTkFrame(social, fg_color="transparent")
        trow.pack(fill="x", padx=10, pady=(0, 8))
        self.trade_offer_title = ctk.CTkEntry(trow, width=170, fg_color=WHITE, text_color=TEXT, placeholder_text="Offer title")
        self.trade_offer_title.pack(side="left", padx=4)
        self.trade_offer_count = ctk.CTkEntry(trow, width=70, fg_color=WHITE, text_color=TEXT, placeholder_text="x")
        self.trade_offer_count.pack(side="left", padx=4)
        self.trade_want_title = ctk.CTkEntry(trow, width=170, fg_color=WHITE, text_color=TEXT, placeholder_text="Want title")
        self.trade_want_title.pack(side="left", padx=4)
        self.trade_want_count = ctk.CTkEntry(trow, width=70, fg_color=WHITE, text_color=TEXT, placeholder_text="x")
        self.trade_want_count.pack(side="left", padx=4)
        ctk.CTkButton(trow, text="Send Trade", width=100, fg_color=ACCENT, hover_color=ACCENT2, command=self._send_trade_request).pack(side="left", padx=6)

        socials = ctk.CTkFrame(wrap, fg_color="transparent")
        socials.pack(fill="both", expand=True, padx=12, pady=(0, 6))
        fcol = ctk.CTkFrame(socials, fg_color=BG, corner_radius=10, border_width=1, border_color=BORDER)
        fcol.pack(side="left", fill="both", expand=True, padx=(0, 6))
        ctk.CTkLabel(fcol, text="Friends + Requests", text_color=TEXT, font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=8, pady=(6, 2))
        self.friends_scroll = ctk.CTkScrollableFrame(fcol, fg_color=BG, corner_radius=8, height=120)
        self.friends_scroll.pack(fill="both", expand=True, padx=8, pady=6)

        tcol = ctk.CTkFrame(socials, fg_color=BG, corner_radius=10, border_width=1, border_color=BORDER)
        tcol.pack(side="left", fill="both", expand=True, padx=(6, 0))
        ctk.CTkLabel(tcol, text="Trades", text_color=TEXT, font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=8, pady=(6, 2))
        self.trade_scroll = ctk.CTkScrollableFrame(tcol, fg_color=BG, corner_radius=8, height=120)
        self.trade_scroll.pack(fill="both", expand=True, padx=8, pady=6)

        self.pvp_result = ctk.CTkLabel(wrap, text="", text_color=MUTED, justify="left", font=("Consolas", 12))
        self.pvp_result.pack(anchor="w", padx=14, pady=(0, 6))

        self.pvp_msg = ctk.CTkLabel(wrap, text="PvP ready.", text_color=MUTED)
        self.pvp_msg.pack(anchor="w", padx=14, pady=(0, 10))

    def _build_online(self):
        tab = self.tabs.tab("🌍 Online")
        wrap = ctk.CTkFrame(tab, fg_color=WHITE, corner_radius=12, border_width=1, border_color=BORDER)
        wrap.pack(fill="both", expand=True, padx=16, pady=16)

        hdr = ctk.CTkFrame(wrap, fg_color="transparent")
        hdr.pack(fill="x", padx=12, pady=(12, 6))
        ctk.CTkLabel(hdr, text="Online Players", text_color=TEXT, font=("Segoe UI", 26, "bold")).pack(side="left")
        ctk.CTkButton(hdr, text="Refresh", fg_color=ACCENT, hover_color=ACCENT2, command=self._refresh_online).pack(side="right")
        ctk.CTkButton(hdr, text="Go PvP", fg_color=RED, hover_color="#dc2626", command=lambda: self.tabs.set("⚔ PvP")).pack(side="right", padx=8)

        self.online_state = ctk.CTkLabel(wrap, text="Cloud idle", text_color=MUTED)
        self.online_state.pack(anchor="w", padx=14)

        boss = ctk.CTkFrame(wrap, fg_color=BG, corner_radius=10, border_width=1, border_color=BORDER)
        boss.pack(fill="x", padx=12, pady=(6, 6))
        brow = ctk.CTkFrame(boss, fg_color="transparent")
        brow.pack(fill="x", padx=10, pady=8)
        ctk.CTkLabel(brow, text="Boss Race Event", text_color=TEXT, font=("Segoe UI", 14, "bold")).pack(side="left")
        ctk.CTkButton(brow, text="Refresh Event", width=110, fg_color=ACCENT, hover_color=ACCENT2, command=self._refresh_boss_race).pack(side="right", padx=4)
        self.boss_state = ctk.CTkLabel(boss, text="No active event fetched yet.", text_color=MUTED)
        self.boss_state.pack(anchor="w", padx=12, pady=(0, 8))
        self.btn_claim_boss = ctk.CTkButton(boss, text="Claim Boss Win", width=140, fg_color=RED, hover_color="#dc2626", command=self._claim_boss_race)
        self.btn_claim_boss.pack(anchor="w", padx=12, pady=(0, 10))
        self.btn_claim_boss.configure(state="disabled")
        self._boss_event_id = None

        self.online_list = ctk.CTkScrollableFrame(wrap, fg_color=BG, corner_radius=10)
        self.online_list.pack(fill="both", expand=True, padx=12, pady=12)

    def _build_leaderboard(self):
        tab = self.tabs.tab("🏆 Leaderboard")
        self.lb_list = ctk.CTkScrollableFrame(tab, fg_color=WHITE, corner_radius=12, border_width=1, border_color=BORDER)
        self.lb_list.pack(fill="both", expand=True, padx=16, pady=16)

    def _build_rebirth(self):
        tab = self.tabs.tab("♻ Rebirth")
        wrap = ctk.CTkFrame(tab, fg_color=WHITE, corner_radius=12, border_width=1, border_color=BORDER)
        wrap.pack(fill="both", expand=True, padx=16, pady=16)
        ctk.CTkLabel(wrap, text="Rebirth", text_color=TEXT, font=("Segoe UI", 28, "bold")).pack(pady=(20, 8))
        self.rb_cost = ctk.CTkLabel(wrap, text="", text_color=MUTED, font=("Segoe UI", 14))
        self.rb_cost.pack()
        ctk.CTkButton(wrap, text="Rebirth Now", width=220, height=46, fg_color=RED, hover_color="#dc2626", command=self._rebirth).pack(pady=16)
        self.rb_msg = ctk.CTkLabel(wrap, text="", text_color=MUTED)
        self.rb_msg.pack()

    def _build_stats(self):
        tab = self.tabs.tab("📈 Stats")
        wrap = ctk.CTkFrame(tab, fg_color=WHITE, corner_radius=12, border_width=1, border_color=BORDER)
        wrap.pack(fill="both", expand=True, padx=16, pady=16)
        self.stats_lbl = ctk.CTkLabel(wrap, text="", text_color=TEXT, justify="left", font=("Consolas", 14))
        self.stats_lbl.pack(anchor="nw", padx=16, pady=16)

    # -------------------------- auth/bootstrap --------------------------
    def _on_auth_done(self, username: str, cloud_state: Optional[dict], cloud_login_ok: bool):
        self.username = username
        self.online_enabled = bool(username and cloud_login_ok)
        local_state = self.engine.s
        local_fresh = self._state_freshness(local_state, self._local_file_mtime())
        cloud_parsed = None
        cloud_fresh = 0.0
        if cloud_state:
            try:
                cloud_parsed = State.from_dict(cloud_state)
                cloud_fresh = self._state_freshness(cloud_parsed, 0.0)
            except Exception as e:
                log_exc("cloud state parse failed", e)

        # Newest state wins on login/bootstrap.
        if cloud_parsed and cloud_fresh > local_fresh:
            self.engine = Engine(cloud_parsed)
            self.engine.save_local(touch=False)
            log_line("Bootstrap selected cloud state (newer).")
        else:
            self.engine = Engine(local_state)
            if self.online_enabled and self.username:
                # Local is newer (or equal): push local to cloud once after login.
                self._save_cloud_state(self.username, self.engine.s.to_dict())
            log_line("Bootstrap selected local state (newer/equal).")
        self.deiconify()
        self._refresh_all()
        if self.online_enabled:
            self.after(1200, self._refresh_recent_rolls)
            self.after(2500, self._heartbeat_tick)

    # -------------------------- async dispatch --------------------------
    def _drain_async(self):
        if self._closing:
            return
        try:
            while True:
                on_done, ok, res = self.bus.q.get_nowait()
                try:
                    on_done(ok, res)
                except Exception as e:
                    log_exc("async callback failed", e)
        except queue.Empty:
            pass
        if not self._closing and self.winfo_exists():
            self.after(40, self._drain_async)

    # -------------------------- gameplay actions --------------------------
    def _roll_once(self):
        if self._rolling:
            return
        self._rolling = True
        self.btn_roll.configure(state="disabled")

        sequence = ["Common", "Uncommon", "Rare", "Common", "Epic", "Rare", "Legendary", "Common"]

        def anim(i=0):
            if i < len(sequence):
                r = sequence[i]
                self._result_text.set(random.choice(TITLES[r]))
                self.lbl_roll_result.configure(text_color=RARITY_COLOR[r])
                self.after(65, lambda: anim(i + 1))
                return

            title, rarity, gain, pity_proc, chest_msg = self.engine.roll()
            self._result_text.set(title)
            self.lbl_roll_result.configure(text_color=RARITY_COLOR[rarity])
            bonus = "  •  HARD PITY!" if pity_proc else ""
            chest = f"  •  {chest_msg}" if chest_msg else ""
            self.lbl_roll_sub.configure(text=f"{rarity}  •  +{gain} coins{bonus}{chest}")
            self._rolling = False
            self.btn_roll.configure(state="normal")
            self._refresh_all()
            if self.online_enabled:
                self._sync_state()
                if RARITY_ORDER.index(rarity) >= RARITY_ORDER.index("Epic"):
                    self._post_roll(title, rarity)
        anim()

    def _activate_lucky(self):
        ok, msg = self.engine.activate_lucky()
        self.lbl_roll_sub.configure(text=msg)
        self._refresh_all()
        if ok and self.online_enabled:
            self._sync_state()

    def _claim_daily(self):
        ok, msg = self.engine.claim_daily()
        self.lbl_roll_sub.configure(text=msg)
        self._refresh_all()
        if ok and self.online_enabled:
            self._sync_state()

    def _set_best_three(self):
        self.engine.set_best_three()
        bt = self.engine.s.battle_titles or []
        self.lbl_bt.configure(text=f"Battle titles: {'  •  '.join(bt) if bt else 'none'}")
        self._refresh_all()
        if self.online_enabled:
            self._sync_state()

    def _rebirth(self):
        ok, msg = self.engine.rebirth()
        self.rb_msg.configure(text=msg, text_color=GREEN if ok else RED)
        self._refresh_all()
        if ok and self.online_enabled:
            self._sync_state()

    # -------------------------- cloud ops --------------------------
    def _cloud_state_payload(self, state_dict: dict) -> dict:
        # Backward-compatible with older API builds that expect decoded PlayerState objects.
        return {"__player_state__": state_dict}

    def _save_cloud_state(self, username: str, state_dict: dict) -> bool:
        if not self.online_enabled or not username:
            return False
        res = self.api.rpc("save_player", username, self._cloud_state_payload(state_dict))
        return bool(res)

    def _sync_state(self):
        if not self.online_enabled or not self.username:
            return
        st = self.engine.s.to_dict()
        self.bus.run(lambda: self._save_cloud_state(self.username, st), lambda ok, res: self._set_cloud_label())

    def _post_roll(self, title: str, rarity: str):
        self.bus.run(lambda: self.api.rpc("post_roll", self.username, title, rarity), lambda ok, res: None)

    def _refresh_recent_rolls(self):
        if not self.online_enabled:
            return
        self.bus.run(lambda: self.api.rpc("get_recent_rolls"), self._render_recent_rolls)

    def _render_recent_rolls(self, ok: bool, rows):
        for w in self.recent_rolls.winfo_children():
            w.destroy()
        if not rows:
            ctk.CTkLabel(self.recent_rolls, text="No recent global rolls yet.", text_color=MUTED).pack(pady=8)
            return
        for r in rows[:20]:
            u = str(r.get("username", "?"))
            t = str(r.get("title", "Unknown"))
            rr = str(r.get("rarity", "Common"))
            rolled_at = str(r.get("rolled_at", "") or "")
            row = ctk.CTkFrame(self.recent_rolls, fg_color=WHITE, corner_radius=8, border_width=1, border_color=BORDER)
            row.pack(fill="x", padx=2, pady=2)
            ctk.CTkLabel(row, text=u, text_color=TEXT, width=140, anchor="w").pack(side="left", padx=8, pady=6)
            ctk.CTkLabel(row, text=t, text_color=TEXT, anchor="w").pack(side="left", padx=8)
            ctk.CTkLabel(row, text=rolled_at[:19].replace("T", " "), text_color=MUTED, width=150).pack(side="right", padx=4)
            ctk.CTkLabel(row, text=rr, text_color=RARITY_COLOR.get(rr, MUTED), width=100).pack(side="right", padx=8)

    def _refresh_online(self):
        if not self.online_enabled:
            self.online_state.configure(text="Offline mode (no cloud login).", text_color=RED)
            return
        self.online_state.configure(text="Loading online players...", text_color=MUTED)
        self.bus.run(lambda: (self.api.rpc("get_online_players"), self.api.last_error), self._render_online_done)
        self._refresh_boss_race()

    def _render_online_done(self, ok: bool, result):
        rows, err = (result if isinstance(result, tuple) else (None, "Unknown error"))
        for w in self.online_list.winfo_children():
            w.destroy()
        if rows is None:
            self.online_state.configure(text=f"Cloud issue: {err or self.api.last_error}", text_color=RED)
            return
        self.online_state.configure(text="Cloud connected", text_color=GREEN)
        if not rows:
            ctk.CTkLabel(self.online_list, text="No players online right now.", text_color=MUTED).pack(pady=12)
            return
        for r in rows:
            u = str(r.get("username", "Unknown"))
            lv = r.get("level", "?")
            rr = str(r.get("rarity", "Common"))
            eq = str(r.get("equipped_title", ""))
            seen = str(r.get("last_seen", "") or "")
            row = ctk.CTkFrame(self.online_list, fg_color=WHITE, corner_radius=8, border_width=1, border_color=BORDER)
            row.pack(fill="x", padx=4, pady=4)
            left = ctk.CTkFrame(row, fg_color="transparent")
            left.pack(side="left", fill="x", expand=True, padx=10, pady=8)
            ctk.CTkLabel(left, text=u, text_color=TEXT, font=("Segoe UI", 14, "bold")).pack(anchor="w")
            sub = f"Lv {lv}  •  {rr}" + (f"  •  {eq}" if eq and eq != "None" else "") + (f"  •  seen {seen[:19].replace('T',' ')}" if seen else "")
            ctk.CTkLabel(left, text=sub, text_color=RARITY_COLOR.get(rr, MUTED), font=("Segoe UI", 12)).pack(anchor="w")
            ctk.CTkButton(row, text="Battle", width=90, fg_color=RED, hover_color="#dc2626", command=lambda x=u: self._prefill_battle(x)).pack(side="right", padx=8)

    def _refresh_leaderboard(self):
        if not self.online_enabled:
            return
        self.bus.run(lambda: self.api.rpc("get_leaderboard"), self._render_leaderboard_done)

    def _refresh_boss_race(self):
        if not self.online_enabled:
            if hasattr(self, "boss_state"):
                self.boss_state.configure(text="Offline mode: no boss race.", text_color=RED)
            return
        if hasattr(self, "boss_state"):
            self.boss_state.configure(text="Loading boss race...", text_color=MUTED)
        self.bus.run(lambda: self.api.rpc("get_active_boss_race"), self._render_boss_race_done)

    def _render_boss_race_done(self, ok: bool, row):
        if not hasattr(self, "boss_state"):
            return
        if not row:
            self._boss_event_id = None
            self.boss_state.configure(text="No active boss race event.", text_color=MUTED)
            self.btn_claim_boss.configure(state="disabled")
            return
        self._boss_event_id = int(row.get("id", 0) or 0)
        boss_id = str(row.get("boss_id", "unknown"))
        ends = str(row.get("ends_at", "unknown"))
        winner = row.get("winner")
        if winner:
            txt = f"{boss_id} • Ends {ends} • Winner: {winner}"
            col = GREEN
            self.btn_claim_boss.configure(state="disabled")
        else:
            txt = f"{boss_id} • Ends {ends} • Winner: unclaimed"
            col = AMBER
            self.btn_claim_boss.configure(state="normal")
        self.boss_state.configure(text=txt, text_color=col)

    def _claim_boss_race(self):
        if not self.online_enabled or not self.username:
            return
        if not self._boss_event_id:
            self.boss_state.configure(text="No active boss event to claim.", text_color=RED)
            return
        eid = int(self._boss_event_id)
        self.bus.run(lambda: self.api.rpc("claim_boss_race", eid, self.username), self._after_claim_boss)

    def _after_claim_boss(self, ok: bool, res):
        if res:
            self.engine.s.total_boss_wins += 1
            self.engine.s.coins += 500
            self.engine.s.shards += 3
            self.engine.save_local()
            self._sync_state()
            self.boss_state.configure(text="Boss race claimed: +500c +3 shards.", text_color=GREEN)
        else:
            self.boss_state.configure(text=f"Claim failed: {self.api.last_error}", text_color=RED)
        self._refresh_boss_race()

    def _render_leaderboard_done(self, ok: bool, rows):
        for w in self.lb_list.winfo_children():
            w.destroy()
        if rows is None:
            ctk.CTkLabel(self.lb_list, text=f"Cloud issue: {self.api.last_error}", text_color=RED).pack(pady=10)
            return
        if not rows:
            ctk.CTkLabel(self.lb_list, text="No leaderboard rows yet.", text_color=MUTED).pack(pady=10)
            return
        for i, r in enumerate(rows[:50], start=1):
            u = str(r.get("username", "Unknown"))
            score = int(r.get("score", 0) or 0)
            rr = str(r.get("rarity", "Common"))
            lv = int(r.get("level", 0) or 0)
            reb = int(r.get("rebirths", 0) or 0)
            pw = int(r.get("pvp_wins", 0) or 0)
            row = ctk.CTkFrame(self.lb_list, fg_color=WHITE, corner_radius=8, border_width=1, border_color=BORDER)
            row.pack(fill="x", padx=4, pady=3)
            ctk.CTkLabel(row, text=f"#{i}", text_color=PINK, width=60).pack(side="left", padx=6, pady=6)
            ctk.CTkLabel(row, text=u, text_color=TEXT, width=220, anchor="w").pack(side="left")
            ctk.CTkLabel(row, text=rr, text_color=RARITY_COLOR.get(rr, MUTED), width=120).pack(side="left")
            ctk.CTkLabel(row, text=f"Lv{lv} R{reb} PvP{pw}", text_color=MUTED, width=140).pack(side="left")
            ctk.CTkLabel(row, text=f"{score:,}", text_color=ACCENT, width=130).pack(side="right", padx=10)

    def _refresh_pvp(self):
        if not self.online_enabled:
            self.pvp_msg.configure(text="Offline mode: PvP inbox requires cloud login.", text_color=RED)
            return
        self.pvp_msg.configure(text="Loading PvP/social/trade data...", text_color=MUTED)

        def job():
            return {
                "incoming": self.api.rpc("get_pending_requests", self.username) or [],
                "sent": self.api.rpc("get_sent_requests", self.username) or [],
                "friends": self.api.rpc("get_friends", self.username) or [],
                "friend_in": self.api.rpc("get_incoming_friend_requests", self.username) or [],
                "friend_out": self.api.rpc("get_outgoing_friend_requests", self.username) or [],
                "trade_in": self.api.rpc("get_incoming_trades", self.username) or [],
                "trade_out": self.api.rpc("get_outgoing_trades", self.username) or [],
            }

        self.bus.run(job, self._render_pvp_lists_done)

    def _render_pvp_lists_done(self, ok: bool, payload):
        for w in self.pvp_inbox.winfo_children():
            w.destroy()
        for w in self.pvp_sent.winfo_children():
            w.destroy()
        if hasattr(self, "friends_scroll"):
            for w in self.friends_scroll.winfo_children():
                w.destroy()
        if hasattr(self, "trade_scroll"):
            for w in self.trade_scroll.winfo_children():
                w.destroy()

        if not ok or not isinstance(payload, dict):
            self.pvp_msg.configure(text=f"Cloud issue: {self.api.last_error}", text_color=RED)
            return

        incoming = payload.get("incoming", [])
        sent = payload.get("sent", [])
        friends = payload.get("friends", [])
        friend_in = payload.get("friend_in", [])
        friend_out = payload.get("friend_out", [])
        trade_in = payload.get("trade_in", [])
        trade_out = payload.get("trade_out", [])

        if not incoming:
            ctk.CTkLabel(self.pvp_inbox, text="No pending battle requests.", text_color=MUTED).pack(pady=12)
        else:
            for req in incoming[:25]:
                rid = int(req.get("id", 0) or 0)
                challenger = str(req.get("challenger", "Unknown"))
                wager = int(req.get("wager_coins", 0) or 0)
                row = ctk.CTkFrame(self.pvp_inbox, fg_color=WHITE, corner_radius=8, border_width=1, border_color=BORDER)
                row.pack(fill="x", padx=4, pady=4)
                ctk.CTkLabel(row, text=f"{challenger} challenged you", text_color=TEXT, font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=10, pady=(8, 0))
                ctk.CTkLabel(row, text=f"Wager: {wager:,} coins", text_color=AMBER).pack(anchor="w", padx=10, pady=(0, 6))
                btns = ctk.CTkFrame(row, fg_color="transparent")
                btns.pack(anchor="w", padx=8, pady=(0, 8))
                ctk.CTkButton(btns, text="Accept", width=90, fg_color=ACCENT, hover_color=ACCENT2, command=lambda i=rid, c=challenger, w=wager: self._accept_battle(i, c, w)).pack(side="left", padx=4)
                ctk.CTkButton(btns, text="Decline", width=90, fg_color=RED, hover_color="#dc2626", command=lambda i=rid: self._decline_battle(i)).pack(side="left", padx=4)

        if not sent:
            ctk.CTkLabel(self.pvp_sent, text="No sent requests.", text_color=MUTED).pack(pady=12)
        else:
            for req in sent[:25]:
                defender = str(req.get("defender", "Unknown"))
                status = str(req.get("status", "pending")).lower()
                wager = int(req.get("wager_coins", 0) or 0)
                col = GREEN if status == "resolved" else (RED if status == "declined" else MUTED)
                row = ctk.CTkFrame(self.pvp_sent, fg_color=WHITE, corner_radius=8, border_width=1, border_color=BORDER)
                row.pack(fill="x", padx=4, pady=4)
                ctk.CTkLabel(row, text=f"→ {defender}", text_color=TEXT, font=("Segoe UI", 12, "bold")).pack(side="left", padx=10, pady=8)
                ctk.CTkLabel(row, text=f"{wager:,}c", text_color=AMBER).pack(side="left", padx=6)
                ctk.CTkLabel(row, text=status.upper(), text_color=col).pack(side="right", padx=10)

        if hasattr(self, "friends_scroll"):
            if not friends and not friend_in and not friend_out:
                ctk.CTkLabel(self.friends_scroll, text="No friends/requests yet.", text_color=MUTED).pack(pady=8)
            for fr in friends[:20]:
                row = ctk.CTkFrame(self.friends_scroll, fg_color=WHITE, corner_radius=8, border_width=1, border_color=BORDER)
                row.pack(fill="x", padx=2, pady=2)
                ctk.CTkLabel(row, text=f"🤝 {fr}", text_color=TEXT).pack(side="left", padx=8, pady=6)
                ctk.CTkButton(row, text="Battle", width=70, fg_color=RED, hover_color="#dc2626", command=lambda u=fr: self._prefill_battle(u)).pack(side="right", padx=6)
            for req in friend_in[:10]:
                rid = int(req.get("id", 0) or 0)
                sender = str(req.get("sender", "Unknown"))
                row = ctk.CTkFrame(self.friends_scroll, fg_color=WHITE, corner_radius=8, border_width=1, border_color=BORDER)
                row.pack(fill="x", padx=2, pady=2)
                ctk.CTkLabel(row, text=f"📩 {sender} wants to friend", text_color=TEXT).pack(side="left", padx=8, pady=6)
                ctk.CTkButton(row, text="Accept", width=70, fg_color=ACCENT, hover_color=ACCENT2, command=lambda i=rid: self._accept_friend_request(i)).pack(side="right", padx=4)
                ctk.CTkButton(row, text="Decline", width=70, fg_color=RED, hover_color="#dc2626", command=lambda i=rid: self._decline_friend_request(i)).pack(side="right", padx=4)
            for req in friend_out[:10]:
                receiver = str(req.get("receiver", "Unknown"))
                row = ctk.CTkFrame(self.friends_scroll, fg_color=WHITE, corner_radius=8, border_width=1, border_color=BORDER)
                row.pack(fill="x", padx=2, pady=2)
                ctk.CTkLabel(row, text=f"🕓 Pending to {receiver}", text_color=MUTED).pack(side="left", padx=8, pady=6)

        if hasattr(self, "trade_scroll"):
            if not trade_in and not trade_out:
                ctk.CTkLabel(self.trade_scroll, text="No trades yet.", text_color=MUTED).pack(pady=8)
            for tr in trade_in[:10]:
                tid = int(tr.get("id", 0) or 0)
                sender = str(tr.get("sender", "Unknown"))
                offer_t = str(tr.get("offered_title", ""))
                offer_c = int(tr.get("offered_count", 1) or 1)
                want_t = str(tr.get("requested_title", ""))
                want_c = int(tr.get("requested_count", 1) or 1)
                row = ctk.CTkFrame(self.trade_scroll, fg_color=WHITE, corner_radius=8, border_width=1, border_color=BORDER)
                row.pack(fill="x", padx=2, pady=2)
                ctk.CTkLabel(row, text=f"⬇ {sender}: {offer_c}x {offer_t} ↔ {want_c}x {want_t}", text_color=TEXT).pack(anchor="w", padx=8, pady=(6, 2))
                b = ctk.CTkFrame(row, fg_color="transparent")
                b.pack(anchor="w", padx=6, pady=(0, 6))
                ctk.CTkButton(b, text="Accept", width=70, fg_color=ACCENT, hover_color=ACCENT2, command=lambda t=tr: self._accept_trade(t)).pack(side="left", padx=4)
                ctk.CTkButton(b, text="Decline", width=70, fg_color=RED, hover_color="#dc2626", command=lambda i=tid: self._decline_trade(i)).pack(side="left", padx=4)
            for tr in trade_out[:10]:
                receiver = str(tr.get("receiver", "Unknown"))
                status = str(tr.get("status", "pending")).upper()
                offer_t = str(tr.get("offered_title", ""))
                offer_c = int(tr.get("offered_count", 1) or 1)
                want_t = str(tr.get("requested_title", ""))
                want_c = int(tr.get("requested_count", 1) or 1)
                col = GREEN if status == "RESOLVED" else (RED if status == "DECLINED" else MUTED)
                row = ctk.CTkFrame(self.trade_scroll, fg_color=WHITE, corner_radius=8, border_width=1, border_color=BORDER)
                row.pack(fill="x", padx=2, pady=2)
                ctk.CTkLabel(row, text=f"⬆ To {receiver}: {offer_c}x {offer_t} ↔ {want_c}x {want_t}", text_color=TEXT).pack(side="left", padx=8, pady=6)
                ctk.CTkLabel(row, text=status, text_color=col).pack(side="right", padx=8)

        self.pvp_msg.configure(text="PvP/social/trade updated.", text_color=GREEN)

    def _send_battle(self):
        now = time.time()
        if self._battle_send_inflight:
            self.pvp_msg.configure(text="Battle request already sending...", text_color=MUTED)
            return
        if now < self._next_battle_send_at:
            wait = max(1, int(self._next_battle_send_at - now))
            self.pvp_msg.configure(text=f"Slow down. Try again in {wait}s.", text_color=RED)
            return
        if not self.online_enabled:
            self.pvp_msg.configure(text="Offline mode: cannot send battle.", text_color=RED)
            return
        target = self.pvp_target.get().strip()
        if not target:
            self.pvp_msg.configure(text="Enter a target username.", text_color=RED)
            return
        if target == self.username:
            self.pvp_msg.configure(text="You cannot battle yourself.", text_color=RED)
            return

        try:
            wager = max(0, int((self.pvp_wager.get() or "0").strip()))
        except Exception:
            self.pvp_msg.configure(text="Wager must be a whole number.", text_color=RED)
            return

        if wager > self.engine.s.coins:
            self.pvp_msg.configure(text=f"Not enough coins for {wager:,} wager.", text_color=RED)
            return
        wager_cap = max(200, int(self.engine.s.coins * MAX_WAGER_FACTOR))
        if wager > wager_cap:
            self.pvp_msg.configure(text=f"Wager cap is {wager_cap:,} coins for balance.", text_color=RED)
            return

        if not self.engine.get_battle_titles_for_pvp():
            self.engine.set_best_three()
        self._battle_send_inflight = True
        self.btn_send_battle.configure(state="disabled")
        self.bus.run(
            lambda: self.api.rpc("send_battle_request", self.username, target, wager, 0),
            lambda ok, res: self._after_send_battle(res),
        )

    def _after_send_battle(self, res):
        self._battle_send_inflight = False
        self._next_battle_send_at = time.time() + BATTLE_SEND_COOLDOWN_SEC
        self.btn_send_battle.configure(state="normal")
        if not res:
            self.pvp_msg.configure(text=f"Cloud issue: {self.api.last_error}", text_color=RED)
            return
        ok, msg = res
        self.pvp_msg.configure(text=str(msg), text_color=GREEN if ok else RED)
        if ok:
            self._refresh_pvp()

    def _send_friend_request(self):
        if not self.online_enabled:
            self.pvp_msg.configure(text="Offline mode: cannot send friend request.", text_color=RED)
            return
        target = self.friend_target.get().strip()
        if not target:
            self.pvp_msg.configure(text="Enter a friend username.", text_color=RED)
            return
        if target == self.username:
            self.pvp_msg.configure(text="You cannot friend yourself.", text_color=RED)
            return
        self.bus.run(
            lambda: self.api.rpc("send_friend_request", self.username, target),
            lambda ok, res: self._after_simple_pvp_action(res),
        )

    def _accept_friend_request(self, req_id: int):
        self.bus.run(lambda: self.api.rpc("accept_friend_request", req_id, self.username), lambda ok, res: self._refresh_pvp())

    def _decline_friend_request(self, req_id: int):
        self.bus.run(lambda: self.api.rpc("decline_friend_request", req_id), lambda ok, res: self._refresh_pvp())

    def _send_trade_request(self):
        if not self.online_enabled:
            self.pvp_msg.configure(text="Offline mode: cannot send trade.", text_color=RED)
            return
        target = self.trade_target.get().strip()
        offer_t = self.trade_offer_title.get().strip()
        want_t = self.trade_want_title.get().strip()
        if not target or not offer_t or not want_t:
            self.pvp_msg.configure(text="Trade needs target, offer title, and want title.", text_color=RED)
            return
        try:
            offer_c = max(1, int((self.trade_offer_count.get() or "1").strip()))
            want_c = max(1, int((self.trade_want_count.get() or "1").strip()))
        except Exception:
            self.pvp_msg.configure(text="Trade counts must be whole numbers.", text_color=RED)
            return
        if self.engine.s.inventory.get(offer_t, 0) < offer_c:
            self.pvp_msg.configure(text=f"You only have {self.engine.s.inventory.get(offer_t, 0)}x {offer_t}.", text_color=RED)
            return
        self.bus.run(
            lambda: self.api.rpc("send_trade_request", self.username, target, offer_t, offer_c, want_t, want_c),
            lambda ok, res: self._after_simple_pvp_action(res),
        )

    def _accept_trade(self, trade: dict):
        if not self.online_enabled:
            return
        tid = int(trade.get("id", 0) or 0)
        if tid <= 0:
            self.pvp_msg.configure(text="Invalid trade request.", text_color=RED)
            return

        def do_trade():
            res = self.api.rpc("accept_trade", tid, self.username)
            if not res:
                return False, f"Trade resolve failed: {self.api.last_error}"
            ok2, payload = res
            if not ok2:
                return False, str(payload)
            receiver_state = (payload or {}).get("receiver_state", {})
            self.engine.s = State.from_dict(receiver_state)
            self.engine.save_local()
            return True, "Trade accepted and synced."

        self.bus.run(do_trade, self._after_trade_done)

    def _after_trade_done(self, ok: bool, res):
        if not ok:
            self.pvp_msg.configure(text=f"Trade failed: {res}", text_color=RED)
            return
        ok2, msg = res
        self.pvp_msg.configure(text=str(msg), text_color=GREEN if ok2 else RED)
        self._refresh_all()
        self._refresh_pvp()
        if ok2 and self.online_enabled:
            self._sync_state()

    def _decline_trade(self, trade_id: int):
        self.bus.run(lambda: self.api.rpc("decline_trade", trade_id), lambda ok, res: self._refresh_pvp())

    def _after_simple_pvp_action(self, res):
        if not res:
            self.pvp_msg.configure(text=f"Cloud issue: {self.api.last_error}", text_color=RED)
            return
        if isinstance(res, (list, tuple)) and len(res) >= 2:
            ok, msg = res[0], res[1]
            self.pvp_msg.configure(text=str(msg), text_color=GREEN if ok else RED)
        elif isinstance(res, bool):
            self.pvp_msg.configure(text="Action complete." if res else "Action failed.", text_color=GREEN if res else RED)
        else:
            self.pvp_msg.configure(text=str(res), text_color=GREEN)
        self._refresh_pvp()

    def _accept_battle(self, req_id: int, challenger: str, wager_coins: int):
        now = time.time()
        if self._battle_action_busy:
            self.pvp_msg.configure(text="Battle action in progress...", text_color=MUTED)
            return
        if now < self._next_battle_action_at:
            wait = max(1, int(self._next_battle_action_at - now))
            self.pvp_msg.configure(text=f"Wait {wait}s before next battle action.", text_color=RED)
            return
        if not self.online_enabled:
            return

        my_titles = self.engine.get_battle_titles_for_pvp()
        if not my_titles:
            self.pvp_msg.configure(text="Set at least one owned battle title first.", text_color=RED)
            return

        if wager_coins > self.engine.s.coins:
            self.pvp_msg.configure(text=f"Need {wager_coins:,} coins to accept this wager.", text_color=RED)
            return

        def do_work():
            res = self.api.rpc("accept_battle", req_id, self.username)
            if not res:
                return False, f"Battle resolve failed: {self.api.last_error}"
            ok2, payload = res
            if not ok2:
                return False, str(payload)
            defender_state = payload.get("defender_state", {})
            self.engine.s = State.from_dict(defender_state)
            self.engine.save_local()
            return True, (bool(payload.get("won", False)), payload.get("result", {}))

        self._battle_action_busy = True
        self.bus.run(do_work, self._accept_battle_done)

    def _accept_battle_done(self, ok: bool, res):
        self._battle_action_busy = False
        self._next_battle_action_at = time.time() + BATTLE_ACTION_COOLDOWN_SEC
        if not ok:
            self.pvp_msg.configure(text=f"Battle failed: {res}", text_color=RED)
            return
        done_ok, payload = res
        if not done_ok:
            self.pvp_msg.configure(text=str(payload), text_color=RED)
            return

        won, result = payload
        outcome = "VICTORY" if won else "DEFEAT"
        def_score = int(result.get("def_score", result.get("my_score", 0)) or 0)
        chal_score = int(result.get("chal_score", result.get("opp_score", 0)) or 0)
        score_txt = f"{def_score} - {chal_score}"
        lines = [f"{outcome} ({score_txt})"]
        for i, rnd in enumerate(result.get("rounds", []), start=1):
            mark = "W" if rnd.get("winner") == "defender" else "L"
            lines.append(
                f"R{i} {mark}: {rnd.get('def_title')} [{rnd.get('def_power')}] "
                f"vs {rnd.get('chal_title')} [{rnd.get('chal_power')}]"
            )
        self.pvp_result.configure(text="\n".join(lines), text_color=GREEN if won else RED)

        self.pvp_msg.configure(text="Battle resolved on cloud and synced.", text_color=GREEN)
        self.engine.save_local()
        self._refresh_all()
        self._refresh_pvp()
        self._sync_state()

    def _decline_battle(self, req_id: int):
        if self._battle_action_busy:
            return
        if not self.online_enabled:
            return
        self._battle_action_busy = True
        def done(ok, res):
            self._battle_action_busy = False
            self._next_battle_action_at = time.time() + BATTLE_ACTION_COOLDOWN_SEC
            self._refresh_pvp()
        self.bus.run(lambda: self.api.rpc("decline_request", req_id), done)

    def _prefill_battle(self, username: str):
        self.tabs.set("⚔ PvP")
        self.pvp_target.delete(0, "end")
        self.pvp_target.insert(0, username)

    def _heartbeat_tick(self):
        if self._closing or not self.winfo_exists():
            return
        if self.online_enabled and self.username:
            self._sync_state()
        self.after(HEARTBEAT_MS, self._heartbeat_tick)

    # -------------------------- periodic / refresh --------------------------
    def _set_cloud_label(self):
        if not self.online_enabled:
            self.lbl_cloud.configure(text="Cloud: offline mode", text_color=RED)
            return
        if self.api.connected:
            mode = "compat TLS" if self.api._tls_unverified else "secure TLS"
            db_part = ""
            if self.api.db_connected is not None:
                db_part = " • DB ok" if self.api.db_connected else f" • DB issue: {self.api.db_error or 'unknown'}"
            if self.api.last_error:
                self.lbl_cloud.configure(text=f"Cloud: reachable ({mode}){db_part} • API issue: {self.api.last_error}", text_color=AMBER)
            else:
                self.lbl_cloud.configure(text=f"Cloud: connected ({mode}){db_part}", text_color=GREEN)
        else:
            self.lbl_cloud.configure(text=f"Cloud: disconnected ({self.api.last_error})", text_color=RED)

    def _slow_tick(self):
        if self._closing:
            return
        try:
            self._set_cloud_label()
            self._refresh_basic_labels()
        except Exception as e:
            log_exc("slow_tick", e)
        if not self._closing and self.winfo_exists():
            self.after(SLOW_TICK_MS, self._slow_tick)

    def _live_refresh_tick(self):
        if self._closing or not self.winfo_exists():
            return
        try:
            if self.online_enabled:
                tab = self.tabs.get()
                if tab == "⚔ PvP":
                    self._refresh_pvp()
                elif tab == "🌍 Online":
                    self._refresh_online()
                    self._refresh_boss_race()
                elif tab == "🏆 Leaderboard":
                    self._refresh_leaderboard()
                elif tab == "🎲 Roll":
                    self._refresh_recent_rolls()
        except Exception as e:
            log_exc("live_refresh_tick", e)
        if not self._closing and self.winfo_exists():
            self.after(LIVE_REFRESH_MS, self._live_refresh_tick)

    def _tab_changed(self):
        tab = self.tabs.get()
        if tab == "🌍 Online":
            self._refresh_online()
            self._refresh_boss_race()
        elif tab == "🏆 Leaderboard":
            self._refresh_leaderboard()
        elif tab == "⚔ PvP":
            self._refresh_pvp()
        elif tab == "✨ Rarities":
            self._render_rarities()
        elif tab == "🎲 Roll":
            self._refresh_recent_rolls()

    def _refresh_basic_labels(self):
        s = self.engine.s
        self.lbl_user.configure(text=f"User: {self.username or 'offline'}")
        self.lbl_lv.configure(text=f"Level {s.level}")
        self.lbl_xp.configure(text=f"XP {s.xp}/{xp_needed(s.level)}")
        self.lbl_coins.configure(text=f"Coins {s.coins:,}")
        self.lbl_best.configure(text=f"Best {s.best_rarity}")
        self.lbl_pity.configure(text=f"Pity {s.pity}/{PITY_HARD}")

        if s.lucky_rolls_remaining > 0:
            self.lbl_lucky.configure(text=f"Lucky active: {s.lucky_rolls_remaining}")
        elif s.lucky_rolls > 0:
            self.lbl_lucky.configure(text=f"Lucky bank: {s.lucky_rolls}")
        else:
            self.lbl_lucky.configure(text=f"Lucky off (buy {LUCKY_BUY_COST:,})")

        self.lbl_live.configure(
            text=(
                f"Live: Lv.{s.level} • Rebirths {s.rebirths} • Rolls {s.total_rolls:,} "
                f"• PvP {s.pvp_wins}/{s.pvp_losses}"
            )
        )
        if hasattr(self, "rarity_rows"):
            self._render_rarities()
        self.rb_cost.configure(text=f"Cost: {self.engine.rebirth_cost():,} coins  •  Need Lv 25 + Legendary+")
        self.lbl_bt.configure(text=f"Battle titles: {'  •  '.join(s.battle_titles) if s.battle_titles else 'none'}")

        self.stats_lbl.configure(
            text=(
                f"Level:          {s.level}\n"
                f"XP:             {s.xp}/{xp_needed(s.level)}\n"
                f"Coins:          {s.coins:,}\n"
                f"Shards:         {s.shards:,}\n"
                f"Rolls:          {s.total_rolls:,}\n"
                f"Pity:           {s.pity}\n"
                f"Lucky bank:     {s.lucky_rolls}\n"
                f"Lucky active:   {s.lucky_rolls_remaining}\n"
                f"Rebirths:       {s.rebirths}\n"
                f"Daily streak:   {s.daily_streak}\n"
                f"Roll chests:    {s.roll_chests_claimed}\n"
                f"Best rarity:    {s.best_rarity}\n"
                f"PvP wins:       {s.pvp_wins}\n"
                f"PvP losses:     {s.pvp_losses}\n"
                f"PvP streak:     {s.pvp_streak}\n"
                f"Arena wins:     {s.total_wins}\n"
                f"Arena losses:   {s.total_losses}\n"
                f"Boss wins:      {s.total_boss_wins}\n"
                f"Rift wins:      {s.total_rift_wins}\n"
                f"Collection:     {len(s.collection)} / {sum(len(v) for v in TITLES.values())}\n"
            )
        )

    def _refresh_inventory(self):
        for w in self.inv_list.winfo_children():
            w.destroy()
        inv = [(t, c, title_rarity(t)) for t, c in self.engine.s.inventory.items() if c > 0]
        inv.sort(key=lambda x: (RARITY_ORDER.index(x[2]), x[1], x[0]), reverse=True)
        if not inv:
            ctk.CTkLabel(self.inv_list, text="No titles yet. Roll to start.", text_color=MUTED).pack(pady=20)
            return
        for t, c, r in inv:
            row = ctk.CTkFrame(self.inv_list, fg_color=WHITE, corner_radius=8, border_width=1, border_color=BORDER)
            row.pack(fill="x", padx=4, pady=3)
            ctk.CTkLabel(row, text=r, text_color=RARITY_COLOR[r], width=120, font=("Segoe UI", 12, "bold")).pack(side="left", padx=8, pady=7)
            ctk.CTkLabel(row, text=t, text_color=TEXT, anchor="w").pack(side="left", padx=8)
            ctk.CTkLabel(row, text=f"x{c}", text_color=ACCENT, font=("Segoe UI", 12, "bold")).pack(side="right", padx=10)

    def _refresh_all(self):
        self._refresh_basic_labels()
        self._refresh_inventory()

    # -------------------------- close --------------------------
    def _on_close(self):
        self._closing = True
        try:
            self.engine.save_local()
            if self.online_enabled and self.username:
                self._save_cloud_state(self.username, self.engine.s.to_dict())
        except Exception as e:
            log_exc("on_close save", e)
        self.destroy()


if __name__ == "__main__":
    try:
        log_line("Starting LULS RNG 2...")
        app = LulsRNG2()
        app.mainloop()
    except Exception as e:
        log_exc("fatal startup", e)
        try:
            messagebox.showerror("Fatal Error", f"Startup failed.\nSee:\n{ERROR_LOG}")
        except Exception:
            print(f"[FATAL] Startup failed. See {ERROR_LOG}")
