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
LUCKY_BUY_COST = 2500
BATTLE_SEND_COOLDOWN_SEC = 6
BATTLE_ACTION_COOLDOWN_SEC = 2
MAX_WAGER_FACTOR = 0.25
ROLL_CHEST_INTERVAL = 25


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
RARITY_ORDER = ["Common", "Uncommon", "Rare", "Epic", "Legendary", "Mythic"]
RARITY_COLOR = {
    "Common": "#94a3b8",
    "Uncommon": "#22c55e",
    "Rare": "#3b82f6",
    "Epic": "#a855f7",
    "Legendary": "#f59e0b",
    "Mythic": "#ef4444",
}
RARITY_WEIGHT = {
    "Common": 6200,
    "Uncommon": 2500,
    "Rare": 1000,
    "Epic": 240,
    "Legendary": 55,
    "Mythic": 5,
}
RARITY_POWER = {
    "Common": 1,
    "Uncommon": 3,
    "Rare": 8,
    "Epic": 20,
    "Legendary": 55,
    "Mythic": 140,
}
RARITY_COINS = {
    "Common": 1,
    "Uncommon": 2,
    "Rare": 5,
    "Epic": 13,
    "Legendary": 40,
    "Mythic": 130,
}
TITLES = {
    "Common": ["Gatekeeper", "Dust Walker", "Stone Foot", "Plain Blade", "Drift Soul", "Mild Hero"],
    "Uncommon": ["Bog Walker", "Night Stalker", "Cursed Coin", "Green Fang", "Echo Scout", "Iron Skin"],
    "Rare": ["Void Seeker", "Frost Herald", "Thunder Step", "Stormcaller", "Ash Hunter", "Moon Razor"],
    "Epic": ["Soulreaper", "Aether Weave", "Ruinbringer", "Chaos Bloom", "Phantom King", "Flux Guard"],
    "Legendary": ["Dragon Sovereign", "Eternal Flame", "Starshatter", "The Undying", "Doomforged", "Skybreaker"],
    "Mythic": ["Abyssal God", "Null Sovereign", "Heavenbreaker", "Cosmos Ender", "Singularity", "First Light"],
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

    def save_local(self):
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
        for r in ["Rare", "Epic", "Legendary", "Mythic"]:
            w[r] *= shift

        if self.s.pity >= PITY_SOFT:
            w["Epic"] *= 4.0
            w["Legendary"] *= 3.5
            w["Mythic"] *= 2.2
        if self.s.pity >= PITY_HARD:
            w["Legendary"] *= 9.0
            w["Mythic"] *= 7.0

        if self.s.lucky_rolls_remaining > 0:
            w["Common"] *= 0.38
            w["Uncommon"] *= 0.55
            w["Rare"] *= 1.75
            w["Epic"] *= 2.8
            w["Legendary"] *= 3.0
            w["Mythic"] *= 2.8
        return w

    def roll(self) -> Tuple[str, str, int, bool, str]:
        pity_proc = self.s.pity >= PITY_HARD
        if pity_proc:
            rarity = random.choices(["Legendary", "Mythic"], weights=[90, 10], k=1)[0]
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
        if self.s.coins < LUCKY_BUY_COST:
            return False, f"Need {LUCKY_BUY_COST:,} coins or 1 lucky charge."
        self.s.coins -= LUCKY_BUY_COST
        self.s.lucky_rolls_remaining = max(8, LUCKY_SPAN - 2)
        self.save_local()
        return True, f"Lucky aura bought for {LUCKY_BUY_COST:,} coins."

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
                log_line("TLS verify failed. Switched to compatibility TLS mode.")
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
        self.after(1000, self._slow_tick)

        LoginWindow(self, self.api, self._on_auth_done)

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
        for name in ["🎲 Roll", "🎒 Inventory", "⚔ PvP", "🌍 Online", "🏆 Leaderboard", "♻ Rebirth", "📈 Stats"]:
            self.tabs.add(name)
        self.tabs.configure(command=self._tab_changed)

        self._build_roll()
        self._build_inventory()
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
        if cloud_state:
            try:
                self.engine = Engine(State.from_dict(cloud_state))
            except Exception as e:
                log_exc("cloud state parse failed", e)
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
    def _sync_state(self):
        if not self.online_enabled or not self.username:
            return
        st = self.engine.s.to_dict()
        self.bus.run(lambda: self.api.rpc("save_player", self.username, st), lambda ok, res: self._set_cloud_label())

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
            row = ctk.CTkFrame(self.recent_rolls, fg_color=WHITE, corner_radius=8, border_width=1, border_color=BORDER)
            row.pack(fill="x", padx=2, pady=2)
            ctk.CTkLabel(row, text=u, text_color=TEXT, width=140, anchor="w").pack(side="left", padx=8, pady=6)
            ctk.CTkLabel(row, text=t, text_color=TEXT, anchor="w").pack(side="left", padx=8)
            ctk.CTkLabel(row, text=rr, text_color=RARITY_COLOR.get(rr, MUTED), width=100).pack(side="right", padx=8)

    def _refresh_online(self):
        if not self.online_enabled:
            self.online_state.configure(text="Offline mode (no cloud login).", text_color=RED)
            return
        self.online_state.configure(text="Loading online players...", text_color=MUTED)
        self.bus.run(lambda: (self.api.rpc("get_online_players"), self.api.last_error), self._render_online_done)

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
            row = ctk.CTkFrame(self.online_list, fg_color=WHITE, corner_radius=8, border_width=1, border_color=BORDER)
            row.pack(fill="x", padx=4, pady=4)
            left = ctk.CTkFrame(row, fg_color="transparent")
            left.pack(side="left", fill="x", expand=True, padx=10, pady=8)
            ctk.CTkLabel(left, text=u, text_color=TEXT, font=("Segoe UI", 14, "bold")).pack(anchor="w")
            sub = f"Lv {lv}  •  {rr}" + (f"  •  {eq}" if eq and eq != "None" else "")
            ctk.CTkLabel(left, text=sub, text_color=RARITY_COLOR.get(rr, MUTED), font=("Segoe UI", 12)).pack(anchor="w")
            ctk.CTkButton(row, text="Battle", width=90, fg_color=RED, hover_color="#dc2626", command=lambda x=u: self._prefill_battle(x)).pack(side="right", padx=8)

    def _refresh_leaderboard(self):
        if not self.online_enabled:
            return
        self.bus.run(lambda: self.api.rpc("get_leaderboard"), self._render_leaderboard_done)

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
            row = ctk.CTkFrame(self.lb_list, fg_color=WHITE, corner_radius=8, border_width=1, border_color=BORDER)
            row.pack(fill="x", padx=4, pady=3)
            ctk.CTkLabel(row, text=f"#{i}", text_color=PINK, width=60).pack(side="left", padx=6, pady=6)
            ctk.CTkLabel(row, text=u, text_color=TEXT, width=220, anchor="w").pack(side="left")
            ctk.CTkLabel(row, text=rr, text_color=RARITY_COLOR.get(rr, MUTED), width=120).pack(side="left")
            ctk.CTkLabel(row, text=f"{score:,}", text_color=ACCENT, width=130).pack(side="right", padx=10)

    def _refresh_pvp(self):
        if not self.online_enabled:
            self.pvp_msg.configure(text="Offline mode: PvP inbox requires cloud login.", text_color=RED)
            return
        self.pvp_msg.configure(text="Loading PvP data...", text_color=MUTED)

        def job():
            incoming = self.api.rpc("get_pending_requests", self.username)
            sent = self.api.rpc("get_sent_requests", self.username)
            return incoming, sent

        self.bus.run(job, self._render_pvp_lists_done)

    def _render_pvp_lists_done(self, ok: bool, payload):
        for w in self.pvp_inbox.winfo_children():
            w.destroy()
        for w in self.pvp_sent.winfo_children():
            w.destroy()

        if not ok or not isinstance(payload, tuple):
            self.pvp_msg.configure(text=f"Cloud issue: {self.api.last_error}", text_color=RED)
            return

        incoming, sent = payload
        incoming = incoming or []
        sent = sent or []

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

        self.pvp_msg.configure(text="PvP inbox updated.", text_color=GREEN)

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
            profile = self.api.rpc("get_player_profile", challenger)
            if not profile:
                return False, f"Could not load challenger profile: {self.api.last_error}"

            opp_state = State.from_dict(profile.get("data", {}) or {})
            opp_titles = Engine(opp_state).get_battle_titles_for_pvp()
            if not opp_titles:
                return False, "Challenger has no usable battle titles."
            if wager_coins > opp_state.coins:
                return False, "Challenger can no longer cover wager."

            result = pvp_simulate(my_titles, opp_titles)
            won = result.get("winner") == "me"

            if won:
                self.engine.s.pvp_wins += 1
                self.engine.s.coins += wager_coins
                opp_state.pvp_losses += 1
                opp_state.coins = max(0, opp_state.coins - wager_coins)
            else:
                self.engine.s.pvp_losses += 1
                self.engine.s.coins = max(0, self.engine.s.coins - wager_coins)
                opp_state.pvp_wins += 1
                opp_state.coins += wager_coins

            self.engine.save_local()
            ok_self = bool(self.api.rpc("save_player", self.username, self.engine.s.to_dict()))
            ok_opp = bool(self.api.rpc("save_player", challenger, opp_state.to_dict()))
            ok_resolve = bool(self.api.rpc("resolve_battle", req_id, result, self.username if won else challenger))
            if not (ok_self and ok_opp and ok_resolve):
                return False, f"Cloud save/resolve failed: {self.api.last_error}"
            return True, (won, result)

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
        score_txt = f"{result.get('my_score', 0)} - {result.get('opp_score', 0)}"
        lines = [f"{outcome} ({score_txt})"]
        for i, rnd in enumerate(result.get("rounds", []), start=1):
            mark = "W" if rnd.get("winner") == "me" else "L"
            lines.append(f"R{i} {mark}: {rnd.get('my_title')} [{rnd.get('my_power')}] vs {rnd.get('opp_title')} [{rnd.get('opp_power')}]")
        self.pvp_result.configure(text="\n".join(lines), text_color=GREEN if won else RED)

        if won:
            self.engine.s.pvp_streak += 1
            streak_bonus = min(120, self.engine.s.pvp_streak * 10)
            self.engine.s.coins += streak_bonus
            self.pvp_msg.configure(text=f"Battle resolved and synced. Win streak {self.engine.s.pvp_streak} (+{streak_bonus}c).", text_color=GREEN)
        else:
            self.engine.s.pvp_streak = 0
            self.pvp_msg.configure(text="Battle resolved and synced. Streak reset.", text_color=GREEN)
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
        self.after(8000, self._heartbeat_tick)

    # -------------------------- periodic / refresh --------------------------
    def _set_cloud_label(self):
        if not self.online_enabled:
            self.lbl_cloud.configure(text="Cloud: offline mode", text_color=RED)
            return
        if self.api.connected:
            mode = "compat TLS" if self.api._tls_unverified else "secure TLS"
            if self.api.last_error:
                self.lbl_cloud.configure(text=f"Cloud: reachable ({mode}) • API issue: {self.api.last_error}", text_color=AMBER)
            else:
                self.lbl_cloud.configure(text=f"Cloud: connected ({mode})", text_color=GREEN)
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
            self.after(1000, self._slow_tick)

    def _tab_changed(self):
        tab = self.tabs.get()
        if tab == "🌍 Online":
            self._refresh_online()
        elif tab == "🏆 Leaderboard":
            self._refresh_leaderboard()
        elif tab == "⚔ PvP":
            self._refresh_pvp()
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
                self.api.rpc("save_player", self.username, self.engine.s.to_dict())
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
