"""
╔══════════════════════════════════════════════════════════╗
║             LUL'S RNG  ⚡  — MULTIPLAYER EDITION        ║
║   Neon Postgres · PvP Battles · Leaderboard · Live Feed ║
╚══════════════════════════════════════════════════════════╝
Run:  python game.py
Auto-installs dependencies on first run.
"""

# ── auto-install ──────────────────────────────────────────────────────────────
import subprocess, sys

def _ensure(pkg, import_name=None):
    try:
        __import__(import_name or pkg)
    except ImportError:
        print(f"Installing {pkg}…")
        subprocess.check_call([sys.executable, "-m", "pip", "install", pkg],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

_ensure("customtkinter")
_ensure("psycopg2-binary", "psycopg2")

# ── imports ───────────────────────────────────────────────────────────────────
import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
import random, json, os, time, math, hashlib, threading
import atexit
from datetime import date, datetime
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict
from collections import deque
from urllib.parse import urlparse, urlunparse
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

try:
    import psycopg2
    import psycopg2.extras
    DB_AVAILABLE = True
except Exception:
    DB_AVAILABLE = False

try:
    import pygame
except Exception:
    pygame = None

# ══════════════════════════════════════════════════════════════════════════════
#  NEON DATABASE CONFIG
# ══════════════════════════════════════════════════════════════════════════════
NEON_URL = os.getenv("LULSRNG_DB_URL", (
    "postgresql://neondb_owner:npg_9hUmKVk0abDl"
    "@ep-hidden-poetry-a4gejlcj-pooler.us-east-1.aws.neon.tech"
    "/neondb?sslmode=require&channel_binding=require"
))
SAVE_FILE  = os.path.join(os.path.dirname(__file__), "luls_rng_save.json")  # local fallback
GAME_TITLE = "LUL'S RNG"
ONLINE_CFG_FILE = os.path.join(os.path.dirname(__file__), "online_client_config.json")
DEFAULT_API_BASE = "https://render-47ff.onrender.com"
DEFAULT_API_TOKEN = "04ea193ec0537156f012b0f3a82f86a8"


def load_online_api_config():
    """Resolve API mode config from env, then local file, then built-in defaults."""
    base = os.getenv("LULSRNG_API_BASE", "").strip()
    token = os.getenv("LULSRNG_API_TOKEN", "").strip()
    if base:
        return base, token
    try:
        if os.path.exists(ONLINE_CFG_FILE):
            with open(ONLINE_CFG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f) or {}
            base = str(cfg.get("api_base", "")).strip()
            token = str(cfg.get("api_token", "")).strip()
            if base:
                return base, token
    except Exception:
        pass
    return DEFAULT_API_BASE, DEFAULT_API_TOKEN

# ══════════════════════════════════════════════════════════════════════════════
#  GAME DATA
# ══════════════════════════════════════════════════════════════════════════════
RARITIES = {
    "Common":       {"weight":6000,"power":1,   "color":"#9ca3af","shard":0, "glow":"#374151"},
    "Uncommon":     {"weight":2500,"power":3,   "color":"#34d399","shard":0, "glow":"#065f46"},
    "Rare":         {"weight":1000,"power":8,   "color":"#60a5fa","shard":0, "glow":"#1e3a8a"},
    "Epic":         {"weight":300, "power":20,  "color":"#c084fc","shard":1, "glow":"#581c87"},
    "Legendary":    {"weight":100, "power":60,  "color":"#fbbf24","shard":3, "glow":"#78350f"},
    "Mythic":       {"weight":20,  "power":150, "color":"#f472b6","shard":8, "glow":"#831843"},
    "Divine":       {"weight":3,   "power":400, "color":"#22d3ee","shard":20,"glow":"#164e63"},
    "Transcendent": {"weight":1,   "power":1000,"color":"#f8fafc","shard":50,"glow":"#475569"},
}
RARITY_ORDER = list(RARITIES.keys())

TITLES = {
    "Common":       ["The Wanderer","Gatekeeper","Dust Collector","The Nobody","Plain Blade","Stone Foot"],
    "Uncommon":     ["The Sly Fox","Iron Will","Night Stalker","Thorn Bearer","Bog Walker","Cursed Coin"],
    "Rare":         ["Stormcaller","Shadow Dancer","Void Seeker","Crimson Tide","Frost Herald","Thunder Step"],
    "Epic":         ["Soulreaper","Aether Weave","Phantom King","Eclipse Lord","Ruinbringer","Chaos Bloom"],
    "Legendary":    ["Dragon Sovereign","Celestial Warden","Doomforged","Eternal Flame","Starshatter","The Undying"],
    "Mythic":       ["Abyssal God","Heavenbreaker","Null Sovereign","Voidborn Prime","Cosmos Ender","Singularity"],
    "Divine":       ["Reality Weaver","The Infinite","Dawn of All","Omnipotent Gaze","Origin Pulse","Fate's Edge"],
    "Transcendent": ["LUL's Chosen","The Absolute","Beyond Legend","Null and Void","The Final Form","Apex Eternal"],
}

BOSSES = [
    {"id":"boss_1","name":"Shadow Grunt",   "emoji":"👹","power":40,  "req_level":20,"req_rarity":"Rare",
     "token_cost":1,"cooldown":120, "coins":300, "shards":5,  "xp":200, "guarantee":"Epic",   "desc":"A weakened creature of the void.","color":"#f97316"},
    {"id":"boss_2","name":"Iron Colossus",  "emoji":"🤖","power":100, "req_level":25,"req_rarity":"Epic",
     "token_cost":2,"cooldown":300, "coins":700, "shards":12, "xp":450, "guarantee":"Legendary","desc":"A mechanical titan of immense power.","color":"#818cf8"},
    {"id":"boss_3","name":"Void Titan",     "emoji":"💀","power":250, "req_level":30,"req_rarity":"Legendary",
     "token_cost":3,"cooldown":600, "coins":1500,"shards":30, "xp":900, "guarantee":"Mythic",  "desc":"The embodiment of the abyss.","color":"#c084fc"},
    {"id":"boss_4","name":"Celestial Drake","emoji":"🐉","power":600, "req_level":40,"req_rarity":"Mythic",
     "token_cost":5,"cooldown":1200,"coins":3500,"shards":75, "xp":2000,"guarantee":"Divine",  "desc":"A godlike dragon from beyond the stars.","color":"#fbbf24"},
    {"id":"boss_5","name":"The Absolute",   "emoji":"⚡","power":1500,"req_level":55,"req_rarity":"Divine",
     "token_cost":8,"cooldown":3600,"coins":8000,"shards":200,"xp":5000,"guarantee":"Transcendent","desc":"The final boss. Only the chosen may challenge it.","color":"#f8fafc"},
]

ENDGAME_RIFTS = [
    {"id":"rift_1","name":"Astral Breach","emoji":"🌌","req_level":45,"req_rebirths":3,
     "base_power":900,"token_cost":2,"shard_cost":30,"cooldown":600,
     "reward_essence":20,"reward_coins":4000,"reward_shards":60,"guarantee":"Legendary",
     "desc":"Cracks reality and floods the arena with unstable starfire."},
    {"id":"rift_2","name":"Mythcore Singularity","emoji":"🕳️","req_level":60,"req_rebirths":6,
     "base_power":2200,"token_cost":4,"shard_cost":80,"cooldown":1200,
     "reward_essence":55,"reward_coins":12000,"reward_shards":160,"guarantee":"Mythic",
     "desc":"A collapsing core where only heavily reborn players survive."},
    {"id":"rift_3","name":"Apex Paradox","emoji":"🜂","req_level":80,"req_rebirths":10,
     "base_power":5200,"token_cost":7,"shard_cost":200,"cooldown":2400,
     "reward_essence":140,"reward_coins":30000,"reward_shards":420,"guarantee":"Divine",
     "desc":"The true endgame gauntlet built for overpowered rebirth runs."},
]

UPDATES_LOG = [
    {
        "version": "1.1.1",
        "date": "March 16, 2026",
        "title": "HTTPS API Mode (Render Ready)",
        "highlights": [
            "Added optional HTTPS API transport for school Wi-Fi compatibility",
            "Client can now use LULSRNG_API_BASE + LULSRNG_API_TOKEN instead of direct Postgres",
            "Included Render-ready backend file: lulsrng_api.py",
            "Keeps local fallback behavior if API is unavailable"
        ]
    },
    {
        "version": "1.1.0",
        "date": "March 16, 2026",
        "title": "Network Recovery + Online Stability",
        "highlights": [
            "Added resilient Neon reconnect loop with backoff",
            "Added multi-endpoint connect attempts, including port 443 fallback",
            "Improved school-network timeout handling and clearer offline messaging",
            "Cloud sync now retries on close before falling back to local save",
            "Live status strip now shows Cloud Online/Offline state"
        ]
    },
    {
        "version": "1.0.0",
        "date": "March 14, 2026",
        "title": "Launch Build",
        "highlights": [
            "Online profiles + cloud synced progression",
            "Global leaderboard + live Epic+ roll feed",
            "PvP battles, title trading, and inventory peek",
            "Rebirth upgrades (Auto Roll, Roll Haste, Drop Shift)",
            "Endgame Rifts + Void Essence progression",
            "Polished UI, animated rarity reveals, glow effects"
        ]
    },
    {
        "version": "0.9.x",
        "date": "Pre-Launch",
        "title": "Foundations",
        "highlights": [
            "Core RNG title system and rarity ladder",
            "Arena, boss battles, crafting, merging",
            "Collection tracking, achievements, rebirth system"
        ]
    }
]

LIVE_TIPS = [
    "Tip: Save boss tokens for Rifts after Rebirth 3+.",
    "Tip: Set battle titles often; your inventory power changes fast.",
    "Tip: Lucky rolls are best stacked before big roll sessions.",
    "Tip: Crafting is a strong bridge when pity is low.",
    "Tip: Rebirth points snowball when spent on Drop Shift early."
]

ARENA_OPPONENTS = [
    {"name":"The Intern",     "emoji":"🧑‍💼","power":5,  "coins":40,  "shards":0,"xp":15, "cooldown":15},
    {"name":"Connor Fettig",  "emoji":"😤",  "power":15, "coins":80,  "shards":1,"xp":30, "cooldown":30},
    {"name":"Mr. G",          "emoji":"🧑‍🏫", "power":35, "coins":150, "shards":2,"xp":60, "cooldown":60},
    {"name":"Sara Fettermen", "emoji":"💪",  "power":70, "coins":280, "shards":4,"xp":120,"cooldown":90},
    {"name":"Chad McBro",     "emoji":"😎",  "power":50, "coins":200, "shards":2,"xp":80, "cooldown":60},
    {"name":"The Algorithm",  "emoji":"🤖",  "power":55, "coins":220, "shards":3,"xp":90, "cooldown":75},
    {"name":"Professor Void", "emoji":"🧪",  "power":85, "coins":320, "shards":5,"xp":150,"cooldown":120},
    {"name":"Iron Mike",      "emoji":"🥊",  "power":120,"coins":450, "shards":7,"xp":200,"cooldown":180},
    {"name":"The Grandmaster","emoji":"♟️",  "power":200,"coins":700, "shards":12,"xp":350,"cooldown":300},
    {"name":"Nightmare Mode", "emoji":"👻",  "power":500,"coins":1500,"shards":30,"xp":800,"cooldown":600},
]

SHOP_ITEMS = [
    {"id":"lucky_roll",   "name":"Lucky Roll",   "emoji":"🌟","desc":"Boost high-rarity odds for 10 rolls","cost":200},
    {"id":"free_merge",   "name":"Free Merge",   "emoji":"⚗️","desc":"Next merge costs 0 titles",         "cost":500},
    {"id":"shard_bundle", "name":"Shard Bundle", "emoji":"💎","desc":"+15 shards instantly",              "cost":300},
    {"id":"boss_token",   "name":"Boss Token",   "emoji":"🔑","desc":"Required to fight bosses",          "cost":600},
    {"id":"xp_boost",     "name":"XP Potion",    "emoji":"✨","desc":"+250 XP instantly",                "cost":150},
    {"id":"coin_shard",   "name":"Coin → Shard", "emoji":"🪙","desc":"+5 shards for 50 coins",           "cost":50},
]

CRAFT_RECIPES = [
    {"id":"craft_basic","name":"Mystic Roll",  "emoji":"🌀","desc":"Lucky roll (boosted odds)",  "cost_shards":10, "type":"roll",      "guarantee":None},
    {"id":"craft_epic", "name":"Epic Forge",   "emoji":"💜","desc":"Guaranteed Epic title",      "cost_shards":25, "type":"guarantee","guarantee":"Epic"},
    {"id":"craft_leg",  "name":"Legend Forge", "emoji":"🟠","desc":"Guaranteed Legendary title", "cost_shards":50, "type":"guarantee","guarantee":"Legendary"},
    {"id":"craft_myth", "name":"Mythic Forge", "emoji":"🩷","desc":"Guaranteed Mythic title",    "cost_shards":120,"type":"guarantee","guarantee":"Mythic"},
]

MERGE_MAP = {
    "Common":"Uncommon","Uncommon":"Rare","Rare":"Epic",
    "Epic":"Legendary","Legendary":"Mythic","Mythic":"Divine","Divine":"Transcendent",
}

ACHIEVEMENTS = [
    {"id":"first_roll",   "name":"First Blood",     "desc":"Complete your first roll",      "rc":50,   "rs":0},
    {"id":"roll_100",     "name":"Centurion",        "desc":"100 rolls",                     "rc":200,  "rs":5},
    {"id":"roll_1000",    "name":"Roll God",         "desc":"1000 rolls",                    "rc":1000, "rs":20},
    {"id":"first_epic",   "name":"Epic Awakening",   "desc":"Pull first Epic",               "rc":100,  "rs":2},
    {"id":"first_leg",    "name":"Legend Rises",     "desc":"Pull first Legendary",          "rc":500,  "rs":10},
    {"id":"first_myth",   "name":"Mythic Ascension", "desc":"Pull first Mythic",             "rc":2000, "rs":30},
    {"id":"first_div",    "name":"Divine Touch",     "desc":"Pull first Divine",             "rc":5000, "rs":75},
    {"id":"first_trans",  "name":"Transcended",      "desc":"Pull first Transcendent",       "rc":15000,"rs":200},
    {"id":"first_arena",  "name":"Gladiator",        "desc":"Win first Arena battle",        "rc":150,  "rs":2},
    {"id":"first_boss",   "name":"Boss Slayer",      "desc":"Defeat any boss",               "rc":500,  "rs":15},
    {"id":"beat_titan",   "name":"Titan Slayer",     "desc":"Defeat Void Titan",             "rc":2000, "rs":50},
    {"id":"beat_abs",     "name":"The Finisher",     "desc":"Defeat The Absolute",           "rc":20000,"rs":500},
    {"id":"first_merge",  "name":"Merger",           "desc":"Complete first merge",          "rc":100,  "rs":3},
    {"id":"first_rebirth","name":"Reborn",           "desc":"First rebirth",                 "rc":0,    "rs":100},
    {"id":"collect_20",   "name":"Collector",        "desc":"Collect 20 unique titles",      "rc":300,  "rs":10},
    {"id":"collect_all",  "name":"Completionist",    "desc":"Collect all 48 titles",         "rc":10000,"rs":500},
    {"id":"first_pvp_win","name":"PvP Victor",       "desc":"Win first PvP battle",          "rc":500,  "rs":10},
    {"id":"pvp_10",       "name":"Warrior",          "desc":"Win 10 PvP battles",            "rc":2000, "rs":30},
]

UNLOCKS = {"arena":5,"merge":10,"craft":15,"boss":20,"rebirth":25,"pvp":8}
TAB_UNLOCK_LEVELS = {
    "🎲 Roll": 1,
    "🎒 Inventory": 1,
    "🛒 Shop": 1,
    "📖 Collection": 1,
    "📊 Stats": 1,
    "📰 Updates": 1,
    "⚔️ Arena": UNLOCKS["arena"],
    "⚔ PvP": UNLOCKS["pvp"],
    "🌍 Online": UNLOCKS["pvp"],
    "🏆 Leaderboard": UNLOCKS["pvp"],
    "⚗️ Craft": UNLOCKS["craft"],
    "💀 Boss": UNLOCKS["boss"],
    "♻️ Rebirth": UNLOCKS["rebirth"],
    "🌌 Endgame": 45,
}
PITY_EPIC = 20
PITY_LEG  = 40
REBIRTH_UPGRADES = [
    {"id":"auto_roll","name":"Auto Roll","max":1,"costs":[1],
     "desc":"Automatically roll on the Roll tab until your target rarity appears."},
    {"id":"roll_speed","name":"Roll Haste","max":4,"costs":[1,2,3,4],
     "desc":"Roll animation and auto-roll loop become faster each level."},
    {"id":"drop_shift","name":"Drop Shift","max":5,"costs":[1,2,3,4,5],
     "desc":"Rebalance drop tables: less Common/Uncommon, more Epic+."},
]

def xp_for_level(lvl): return int(100*(lvl**1.6))
def fmt_cd(s):
    s=int(s)
    return f"{s}s" if s<60 else f"{s//60}m {s%60:02d}s"

def hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()

# ══════════════════════════════════════════════════════════════════════════════
#  DATA MODEL
# ══════════════════════════════════════════════════════════════════════════════
@dataclass
class PlayerState:
    level:int=1; xp:int=0; coins:int=100; shards:int=0
    boss_tokens:int=0; rebirths:int=0; luck_multiplier:float=1.0
    total_rolls:int=0; pity_counter:int=0; lucky_rolls:int=0
    lucky_rolls_remaining:int=0
    inventory:dict=field(default_factory=dict)
    equipped_title:Optional[str]=None; equipped_rarity:Optional[str]=None
    # battle_titles: list of up to 3 title names the player uses for PvP
    battle_titles:list=field(default_factory=list)
    achievements:list=field(default_factory=list)
    collection:list=field(default_factory=list)
    free_merge:bool=False; last_daily:str=""
    total_wins:int=0; total_losses:int=0; total_boss_wins:int=0
    total_merges:int=0; total_crafts:int=0
    highest_rarity_pulled:str="Common"
    cooldowns:dict=field(default_factory=dict)
    pvp_wins:int=0; pvp_losses:int=0
    rebirth_points:int=0
    rebirth_upgrades:dict=field(default_factory=dict)
    auto_roll_enabled:bool=False
    auto_roll_target:str="Legendary"
    title_trades_completed:int=0
    void_essence:int=0
    total_rift_wins:int=0

    def to_dict(self): return asdict(self)
    @classmethod
    def from_dict(cls,d): return cls(**{k:v for k,v in d.items() if k in cls.__dataclass_fields__})

# ══════════════════════════════════════════════════════════════════════════════
#  DATABASE LAYER
# ══════════════════════════════════════════════════════════════════════════════
class Database:
    """Handles all Neon Postgres interaction. Thread-safe via lock."""

    def __init__(self):
        self.conn = None
        self.lock = threading.Lock()
        self.last_error = ""
        self._next_reconnect_at = 0.0
        self._reconnect_backoff = 3.0
        self._connect()
        if self.conn:
            self._create_tables()

    def _candidate_dsns(self) -> list:
        seen = set()
        raw = [
            os.getenv("LULSRNG_DB_URL", "").strip(),
            NEON_URL.strip(),
            os.getenv("LULSRNG_DB_URL_FALLBACK", "").strip(),
        ]
        out = []
        for dsn in raw:
            if not dsn or dsn in seen:
                continue
            seen.add(dsn)
            out.append(dsn)
            # School and enterprise networks often block 5432; try 443 fallback.
            try:
                p = urlparse(dsn)
                host = p.hostname or ""
                if host:
                    auth = ""
                    if p.username:
                        auth += p.username
                        if p.password:
                            auth += f":{p.password}"
                        auth += "@"
                    port443 = urlunparse((
                        p.scheme,
                        f"{auth}{host}:443",
                        p.path,
                        p.params,
                        p.query,
                        p.fragment,
                    ))
                    if port443 not in seen:
                        seen.add(port443)
                        out.append(port443)
            except Exception:
                pass
        return out

    def _connect(self):
        if not DB_AVAILABLE:
            self.last_error = "psycopg2 unavailable"
            return False
        errs = []
        for dsn in self._candidate_dsns():
            try:
                self.conn = psycopg2.connect(
                    dsn,
                    connect_timeout=6,
                    keepalives=1,
                    keepalives_idle=30,
                    keepalives_interval=10,
                    keepalives_count=3,
                    application_name="luls_rng_client",
                )
                self.conn.autocommit = False
                self.last_error = ""
                self._reconnect_backoff = 3.0
                self._next_reconnect_at = 0.0
                print("[DB] Connected to Neon")
                return True
            except Exception as e:
                errs.append(str(e))
        self.conn = None
        self.last_error = errs[0] if errs else "Unknown DB connection error"
        print(f"[DB] Connection failed (offline mode): {self.last_error}")
        return False

    def reconnect_if_needed(self, force=False):
        if self.conn:
            return True
        if not DB_AVAILABLE:
            return False
        now = time.time()
        if (not force) and now < self._next_reconnect_at:
            return False
        ok = self._connect()
        if ok:
            self._create_tables()
            return True
        self._next_reconnect_at = now + self._reconnect_backoff
        self._reconnect_backoff = min(45.0, self._reconnect_backoff * 1.8)
        return False

    def _exec(self, sql, params=(), fetch=None):
        """Execute SQL safely. Returns rows or None."""
        if not self.conn:
            self.reconnect_if_needed()
        if not self.conn:
            return None
        with self.lock:
            try:
                cur = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                cur.execute(sql, params)
                self.conn.commit()
                if fetch == "one":
                    return cur.fetchone()
                if fetch == "all":
                    return cur.fetchall()
                return True
            except Exception as e:
                print(f"[DB] Query error: {e}")
                if "closed" in str(e).lower() or "connection" in str(e).lower():
                    self.conn = None
                try:
                    self.conn.rollback()
                except:
                    pass
                return None

    def _create_tables(self):
        self._exec("""
            CREATE TABLE IF NOT EXISTS players (
                username    TEXT PRIMARY KEY,
                password_h  TEXT NOT NULL,
                data        JSONB NOT NULL DEFAULT '{}',
                last_seen   TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        self._exec("""
            CREATE TABLE IF NOT EXISTS global_rolls (
                id          SERIAL PRIMARY KEY,
                username    TEXT NOT NULL,
                title       TEXT NOT NULL,
                rarity      TEXT NOT NULL,
                rolled_at   TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        self._exec("""
            CREATE TABLE IF NOT EXISTS battle_requests (
                id              SERIAL PRIMARY KEY,
                challenger      TEXT NOT NULL,
                defender        TEXT NOT NULL,
                wager_coins     INT  DEFAULT 0,
                wager_shards    INT  DEFAULT 0,
                status          TEXT DEFAULT 'pending',
                result          JSONB,
                created_at      TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        self._exec("""
            CREATE TABLE IF NOT EXISTS boss_race_events (
                id          SERIAL PRIMARY KEY,
                boss_id     TEXT NOT NULL,
                started_at  TIMESTAMPTZ DEFAULT NOW(),
                ends_at     TIMESTAMPTZ,
                winner      TEXT,
                active      BOOLEAN DEFAULT TRUE
            )
        """)
        self._exec("""
            CREATE TABLE IF NOT EXISTS title_trades (
                id              SERIAL PRIMARY KEY,
                sender          TEXT NOT NULL,
                receiver        TEXT NOT NULL,
                offered_title   TEXT NOT NULL,
                offered_count   INT NOT NULL DEFAULT 1,
                requested_title TEXT NOT NULL,
                requested_count INT NOT NULL DEFAULT 1,
                status          TEXT NOT NULL DEFAULT 'pending',
                created_at      TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        self._exec("""
            CREATE TABLE IF NOT EXISTS friend_requests (
                id          SERIAL PRIMARY KEY,
                sender      TEXT NOT NULL,
                receiver    TEXT NOT NULL,
                status      TEXT NOT NULL DEFAULT 'pending',
                created_at  TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        self._exec("""
            CREATE TABLE IF NOT EXISTS friends (
                user_a      TEXT NOT NULL,
                user_b      TEXT NOT NULL,
                created_at  TIMESTAMPTZ DEFAULT NOW(),
                PRIMARY KEY(user_a, user_b)
            )
        """)

    # ── auth ─────────────────────────────────────────────────────────────────

    def register(self, username: str, password: str) -> tuple:
        """Returns (ok, message)."""
        if not self.conn:
            self.reconnect_if_needed(force=True)
        if not self.conn:
            return True, "offline"
        existing = self._exec(
            "SELECT username FROM players WHERE username=%s", (username,), fetch="one")
        if existing:
            return False, "Username already taken"
        ph = hash_password(password)
        ok = self._exec(
            "INSERT INTO players(username,password_h,data) VALUES(%s,%s,%s)",
            (username, ph, json.dumps(PlayerState().to_dict())))
        return (True, "ok") if ok else (False, "DB error")

    def login(self, username: str, password: str) -> tuple:
        """Returns (ok, PlayerState or message)."""
        if not self.conn:
            self.reconnect_if_needed(force=True)
        if not self.conn:
            return True, None   # offline — use local save
        ph = hash_password(password)
        row = self._exec(
            "SELECT data,password_h FROM players WHERE username=%s", (username,), fetch="one")
        if not row:
            return False, "Username not found"
        if row["password_h"] != ph:
            return False, "Wrong password"
        try:
            state = PlayerState.from_dict(row["data"])
        except:
            state = PlayerState()
        return True, state

    # ── save ─────────────────────────────────────────────────────────────────

    def save_player(self, username: str, state: PlayerState):
        if not self.conn or not username:
            return False
        ok = self._exec(
            "UPDATE players SET data=%s, last_seen=NOW() WHERE username=%s",
            (json.dumps(state.to_dict()), username))
        return bool(ok)

    # ── leaderboard ──────────────────────────────────────────────────────────

    def get_leaderboard(self) -> list:
        rows = self._exec("""
            SELECT username,
                   data->>'highest_rarity_pulled' AS rarity,
                   (data->>'total_rolls')::int     AS rolls,
                   (data->>'level')::int           AS level,
                   (data->>'rebirths')::int        AS rebirths,
                   (data->>'pvp_wins')::int        AS pvp_wins,
                   (data->>'total_boss_wins')::int AS boss_wins,
                   (data->>'total_rift_wins')::int AS rift_wins,
                   (
                        (data->>'total_rolls')::int
                      + (data->>'level')::int * 200
                      + (data->>'rebirths')::int * 1250
                      + (data->>'pvp_wins')::int * 160
                      + (data->>'total_boss_wins')::int * 180
                      + (data->>'total_rift_wins')::int * 600
                      + CASE data->>'highest_rarity_pulled'
                            WHEN 'Transcendent' THEN 6000
                            WHEN 'Divine' THEN 4200
                            WHEN 'Mythic' THEN 2800
                            WHEN 'Legendary' THEN 1700
                            WHEN 'Epic' THEN 900
                            WHEN 'Rare' THEN 350
                            WHEN 'Uncommon' THEN 120
                            ELSE 20
                        END
                   ) AS score,
                   last_seen
            FROM players
            ORDER BY
                score DESC,
                (data->>'total_rolls')::int DESC
            LIMIT 50
        """, fetch="all")
        return rows or []

    # ── global roll feed ─────────────────────────────────────────────────────

    def post_roll(self, username: str, title: str, rarity: str):
        if not self.conn or RARITY_ORDER.index(rarity) < RARITY_ORDER.index("Epic"):
            return
        self._exec(
            "INSERT INTO global_rolls(username,title,rarity) VALUES(%s,%s,%s)",
            (username, title, rarity))
        # Keep only last 200
        self._exec(
            "DELETE FROM global_rolls WHERE id NOT IN "
            "(SELECT id FROM global_rolls ORDER BY rolled_at DESC LIMIT 200)")

    def get_recent_rolls(self) -> list:
        rows = self._exec(
            "SELECT username,title,rarity,rolled_at FROM global_rolls "
            "ORDER BY rolled_at DESC LIMIT 30", fetch="all")
        return rows or []

    # ── online players ───────────────────────────────────────────────────────

    def get_online_players(self) -> list:
        rows = self._exec("""
            SELECT username,
                   data->>'highest_rarity_pulled' AS rarity,
                   data->>'level' AS level,
                   data->>'equipped_title' AS equipped_title,
                   last_seen
            FROM players
            WHERE last_seen > NOW() - INTERVAL '10 minutes'
            ORDER BY last_seen DESC
        """, fetch="all")
        return rows or []

    # ── player peek ──────────────────────────────────────────────────────────

    def get_player_profile(self, username: str) -> Optional[dict]:
        row = self._exec(
            "SELECT username, data FROM players WHERE username=%s",
            (username,), fetch="one")
        if not row:
            return None
        return {"username": row["username"], "data": row["data"]}

    # ── battle requests ──────────────────────────────────────────────────────

    def send_battle_request(self, challenger: str, defender: str,
                            wager_coins: int, wager_shards: int) -> tuple:
        # Check not already pending
        existing = self._exec(
            "SELECT id FROM battle_requests WHERE challenger=%s AND defender=%s AND status='pending'",
            (challenger, defender), fetch="one")
        if existing:
            return False, "Already sent a request to this player"
        ok = self._exec(
            "INSERT INTO battle_requests(challenger,defender,wager_coins,wager_shards) "
            "VALUES(%s,%s,%s,%s)",
            (challenger, defender, wager_coins, wager_shards))
        return (True, "Battle request sent!") if ok else (False, "DB error")

    def get_pending_requests(self, username: str) -> list:
        rows = self._exec(
            "SELECT id,challenger,defender,wager_coins,wager_shards,created_at "
            "FROM battle_requests WHERE defender=%s AND status='pending' "
            "ORDER BY created_at DESC",
            (username,), fetch="all")
        return rows or []

    def get_sent_requests(self, username: str) -> list:
        rows = self._exec(
            "SELECT id,challenger,defender,wager_coins,wager_shards,status,result,created_at "
            "FROM battle_requests WHERE challenger=%s "
            "ORDER BY created_at DESC LIMIT 20",
            (username,), fetch="all")
        return rows or []

    def decline_request(self, request_id: int):
        self._exec("UPDATE battle_requests SET status='declined' WHERE id=%s", (request_id,))

    def resolve_battle(self, request_id: int, result: dict, winner: str):
        self._exec(
            "UPDATE battle_requests SET status='resolved', result=%s WHERE id=%s",
            (json.dumps(result), request_id))

    # ── boss race events ─────────────────────────────────────────────────────

    def get_active_boss_race(self) -> Optional[dict]:
        row = self._exec(
            "SELECT * FROM boss_race_events WHERE active=TRUE AND ends_at > NOW() "
            "ORDER BY started_at DESC LIMIT 1",
            fetch="one")
        return dict(row) if row else None

    def claim_boss_race(self, event_id: int, username: str):
        self._exec(
            "UPDATE boss_race_events SET winner=%s, active=FALSE WHERE id=%s AND winner IS NULL",
            (username, event_id))

    # ── title trading ────────────────────────────────────────────────────────

    def send_trade_request(self, sender: str, receiver: str,
                           offered_title: str, offered_count: int,
                           requested_title: str, requested_count: int) -> tuple:
        if not self.conn:
            return False, "Trading requires online mode"
        if sender == receiver:
            return False, "Can't trade with yourself"
        if not self.are_friends(sender, receiver):
            return False, "Trading is friends-only. Add each other first."
        existing = self._exec(
            "SELECT id FROM title_trades WHERE sender=%s AND receiver=%s AND status='pending' "
            "AND offered_title=%s AND requested_title=%s",
            (sender, receiver, offered_title, requested_title), fetch="one")
        if existing:
            return False, "Similar pending trade already exists"
        ok = self._exec(
            "INSERT INTO title_trades(sender,receiver,offered_title,offered_count,requested_title,requested_count) "
            "VALUES(%s,%s,%s,%s,%s,%s)",
            (sender, receiver, offered_title, offered_count, requested_title, requested_count))
        return (True, "Trade request sent!") if ok else (False, "DB error")

    def get_incoming_trades(self, username: str) -> list:
        rows = self._exec(
            "SELECT * FROM title_trades WHERE receiver=%s AND status='pending' ORDER BY created_at DESC LIMIT 25",
            (username,), fetch="all")
        return rows or []

    def get_outgoing_trades(self, username: str) -> list:
        rows = self._exec(
            "SELECT * FROM title_trades WHERE sender=%s ORDER BY created_at DESC LIMIT 25",
            (username,), fetch="all")
        return rows or []

    def decline_trade(self, trade_id: int):
        self._exec("UPDATE title_trades SET status='declined' WHERE id=%s AND status='pending'", (trade_id,))

    def resolve_trade(self, trade_id: int):
        self._exec("UPDATE title_trades SET status='resolved' WHERE id=%s AND status='pending'", (trade_id,))

    # ── friends ──────────────────────────────────────────────────────────────

    def _norm_pair(self, a: str, b: str):
        return (a, b) if a < b else (b, a)

    def are_friends(self, user1: str, user2: str) -> bool:
        if not self.conn:
            return False
        a, b = self._norm_pair(user1, user2)
        row = self._exec(
            "SELECT 1 FROM friends WHERE user_a=%s AND user_b=%s",
            (a, b), fetch="one")
        return bool(row)

    def send_friend_request(self, sender: str, receiver: str) -> tuple:
        if not self.conn:
            return False, "Friends requires online mode"
        if sender == receiver:
            return False, "Can't add yourself"
        if self.are_friends(sender, receiver):
            return False, "Already friends"
        existing = self._exec(
            "SELECT id FROM friend_requests WHERE sender=%s AND receiver=%s AND status='pending'",
            (sender, receiver), fetch="one")
        if existing:
            return False, "Friend request already sent"
        reverse = self._exec(
            "SELECT id FROM friend_requests WHERE sender=%s AND receiver=%s AND status='pending'",
            (receiver, sender), fetch="one")
        if reverse:
            a, b = self._norm_pair(sender, receiver)
            self._exec("INSERT INTO friends(user_a,user_b) VALUES(%s,%s) ON CONFLICT DO NOTHING", (a, b))
            self._exec("UPDATE friend_requests SET status='accepted' WHERE id=%s", (reverse["id"],))
            return True, "Friend request auto-accepted!"
        ok = self._exec(
            "INSERT INTO friend_requests(sender,receiver) VALUES(%s,%s)",
            (sender, receiver))
        return (True, "Friend request sent!") if ok else (False, "DB error")

    def get_incoming_friend_requests(self, username: str) -> list:
        rows = self._exec(
            "SELECT * FROM friend_requests WHERE receiver=%s AND status='pending' ORDER BY created_at DESC LIMIT 25",
            (username,), fetch="all")
        return rows or []

    def get_outgoing_friend_requests(self, username: str) -> list:
        rows = self._exec(
            "SELECT * FROM friend_requests WHERE sender=%s AND status='pending' ORDER BY created_at DESC LIMIT 25",
            (username,), fetch="all")
        return rows or []

    def accept_friend_request(self, req_id: int):
        row = self._exec(
            "SELECT sender,receiver FROM friend_requests WHERE id=%s AND status='pending'",
            (req_id,), fetch="one")
        if not row:
            return False
        a, b = self._norm_pair(row["sender"], row["receiver"])
        ok1 = self._exec("INSERT INTO friends(user_a,user_b) VALUES(%s,%s) ON CONFLICT DO NOTHING", (a, b))
        ok2 = self._exec("UPDATE friend_requests SET status='accepted' WHERE id=%s", (req_id,))
        return bool(ok1 and ok2)

    def decline_friend_request(self, req_id: int):
        self._exec("UPDATE friend_requests SET status='declined' WHERE id=%s AND status='pending'", (req_id,))

    def get_friends(self, username: str) -> list:
        rows = self._exec(
            "SELECT CASE WHEN user_a=%s THEN user_b ELSE user_a END AS friend "
            "FROM friends WHERE user_a=%s OR user_b=%s ORDER BY friend ASC",
            (username, username, username), fetch="all")
        return [r["friend"] for r in (rows or [])]


class HttpDatabase:
    """HTTPS RPC transport for school networks that block direct DB sockets."""

    def __init__(self, base_url: str, token: str = ""):
        self.base_url = (base_url or "").rstrip("/")
        self.token = token or ""
        self.conn = None
        self.last_error = ""
        self._next_reconnect_at = 0.0
        self._reconnect_backoff = 3.0
        self.reconnect_if_needed(force=True)

    def _encode(self, value):
        if isinstance(value, PlayerState):
            return {"__player_state__": value.to_dict()}
        if isinstance(value, dict):
            return {k: self._encode(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._encode(v) for v in value]
        return value

    def _decode(self, value):
        if isinstance(value, dict):
            if "__player_state__" in value:
                return PlayerState.from_dict(value["__player_state__"])
            return {k: self._decode(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._decode(v) for v in value]
        return value

    def _rpc(self, method: str, *args, **kwargs):
        if not self.conn:
            self.reconnect_if_needed()
        if not self.conn:
            return None
        payload = json.dumps({
            "method": method,
            "args": self._encode(list(args)),
            "kwargs": self._encode(kwargs),
        }).encode("utf-8")
        req = Request(
            f"{self.base_url}/rpc",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "X-API-Token": self.token,
            },
            method="POST",
        )
        try:
            with urlopen(req, timeout=12) as resp:
                raw = resp.read().decode("utf-8")
                body = json.loads(raw or "{}")
                if not body.get("ok"):
                    self.last_error = str(body.get("error", "rpc error"))
                    return None
                return self._decode(body.get("result"))
        except (HTTPError, URLError, TimeoutError, ValueError) as e:
            self.last_error = str(e)
            self.conn = None
            return None
        except Exception as e:
            self.last_error = str(e)
            self.conn = None
            return None

    def reconnect_if_needed(self, force=False):
        now = time.time()
        if self.conn and not force:
            return True
        if (not force) and now < self._next_reconnect_at:
            return False
        if not self.base_url:
            self.last_error = "LULSRNG_API_BASE not set"
            self.conn = None
            return False
        req = Request(
            f"{self.base_url}/health",
            headers={"X-API-Token": self.token},
            method="GET",
        )
        try:
            with urlopen(req, timeout=8) as resp:
                if resp.status == 200:
                    self.conn = True
                    self.last_error = ""
                    self._reconnect_backoff = 3.0
                    self._next_reconnect_at = 0.0
                    return True
        except Exception as e:
            self.last_error = str(e)
        self.conn = None
        self._next_reconnect_at = now + self._reconnect_backoff
        self._reconnect_backoff = min(45.0, self._reconnect_backoff * 1.8)
        return False

    def __getattr__(self, name):
        def _call(*args, **kwargs):
            return self._rpc(name, *args, **kwargs)
        return _call

    # Keep behavior compatible with local Database callers.
    def register(self, username: str, password: str) -> tuple:
        r = self._rpc("register", username, password)
        if isinstance(r, (list, tuple)) and len(r) == 2:
            return bool(r[0]), r[1]
        return True, "offline"

    def login(self, username: str, password: str) -> tuple:
        r = self._rpc("login", username, password)
        if isinstance(r, (list, tuple)) and len(r) == 2:
            return bool(r[0]), r[1]
        return True, None

    def save_player(self, username: str, state: PlayerState):
        r = self._rpc("save_player", username, state)
        return bool(r)


# ══════════════════════════════════════════════════════════════════════════════
#  PVP ENGINE
# ══════════════════════════════════════════════════════════════════════════════
def pvp_simulate(my_titles: list, opp_titles: list) -> dict:
    """
    Simulate a best-of-3 PvP battle.
    Each title pair fights: win probability weighted by power ratio + 30% variance.
    Returns {"rounds": [...], "my_score": int, "opp_score": int, "winner": "me"|"opp"}
    """
    # Normalise to 3 slots; empty slots are allowed and intentionally weak.
    def pad(titles, n=3):
        while len(titles) < n:
            titles = titles + ["[Empty Slot]"]
        return titles[:n]

    mine = pad(my_titles)
    theirs = pad(opp_titles)

    rounds = []
    my_score = 0
    opp_score = 0

    for i in range(3):
        mt = mine[i];   mr = _title_rarity(mt) if mt != "[Empty Slot]" else "Common"
        ot = theirs[i]; orr = _title_rarity(ot) if ot != "[Empty Slot]" else "Common"
        base_mp = RARITIES.get(mr, {}).get("power", 1)
        base_op = RARITIES.get(orr, {}).get("power", 1)
        if mt == "[Empty Slot]":
            base_mp = 0.35
        if ot == "[Empty Slot]":
            base_op = 0.35
        # Smooth odds: stronger titles win more often, but never guaranteed.
        p = base_mp / max(1.0, (base_mp + base_op))
        p = 0.12 + 0.76 * p  # hard floor/ceiling keeps PvP exciting
        my_win = random.random() < p
        mp = base_mp * random.uniform(0.85, 1.15)
        op = base_op * random.uniform(0.85, 1.15)
        if my_win:
            my_score += 1
        else:
            opp_score += 1
        rounds.append({
            "my_title": mt, "my_rarity": mr, "my_power": round(mp, 1),
            "opp_title": ot, "opp_rarity": orr, "opp_power": round(op, 1),
            "winner": "me" if my_win else "opp"
        })

    return {
        "rounds": rounds,
        "my_score": my_score,
        "opp_score": opp_score,
        "winner": "me" if my_score >= 2 else "opp"
    }

def _title_rarity(title: str) -> str:
    for r, ts in TITLES.items():
        if title in ts:
            return r
    return "Common"

def get_best_titles(state: PlayerState, n=3) -> list:
    """Return the player's top N titles by power, or battle_titles if set."""
    owned = {t for t, c in (state.inventory or {}).items() if c and c > 0}
    if state.battle_titles:
        valid = [t for t in state.battle_titles if t in owned]
        if valid:
            return valid[:n]
    items = [(t, RARITIES.get(_title_rarity(t), {}).get("power", 1))
             for t in owned]
    items.sort(key=lambda x: -x[1])
    return [t for t, _ in items[:n]]


# ══════════════════════════════════════════════════════════════════════════════
#  GAME ENGINE
# ══════════════════════════════════════════════════════════════════════════════
class GameEngine:
    def __init__(self, db: Database, username: str = ""):
        self.db = db
        self.username = username
        self.state = PlayerState()
        self._load()

    def _load(self):
        # Try cloud first, fall back to local
        if self.db.conn and self.username:
            profile = self.db.get_player_profile(self.username)
            if profile:
                try:
                    self.state = PlayerState.from_dict(profile["data"])
                    return
                except:
                    pass
        # Local fallback
        if os.path.exists(SAVE_FILE):
            try:
                with open(SAVE_FILE) as f:
                    self.state = PlayerState.from_dict(json.load(f))
            except:
                self.state = PlayerState()

    def save_game(self):
        # Local fallback always
        try:
            with open(SAVE_FILE, "w") as f:
                json.dump(self.state.to_dict(), f, indent=2)
        except Exception as e:
            print(f"[WARN] local save: {e}")
        # Cloud sync (level/titles/inventory/etc.) if online
        if self.username and self.db.conn:
            try:
                self.db.save_player(self.username, self.state)
            except Exception as e:
                print(f"[WARN] cloud save: {e}")

    def cooldown_remaining(self, key, dur):
        return max(0.0, dur - (time.time() - self.state.cooldowns.get(key, 0)))
    def set_cooldown(self, key): self.state.cooldowns[key] = time.time()
    def _upg(self, upg_id: str) -> int:
        return int((self.state.rebirth_upgrades or {}).get(upg_id, 0) or 0)
    def get_roll_speed_multiplier(self) -> float:
        return 1.0 + self._upg("roll_speed") * 0.12
    def get_drop_shift_multiplier(self) -> float:
        return 1.0 + self._upg("drop_shift") * 0.08

    def compute_weights(self, guaranteed=None, mystic=False):
        if guaranteed:
            idx = RARITY_ORDER.index(guaranteed)
            return {r: RARITIES[r]["weight"] for r in RARITY_ORDER[idx:]}
        w = {r: RARITIES[r]["weight"] for r in RARITY_ORDER}
        # Rebirth remains intentionally strong, but with soft caps for stability.
        lm = max(1.0, float(self.state.luck_multiplier or 1.0))
        high_boost = 1.0 + (lm - 1.0) * 1.05
        low_reduce = max(0.48, 1.0 - (lm - 1.0) * 0.52)
        w["Common"] *= low_reduce
        w["Uncommon"] *= low_reduce
        for r in ["Rare","Epic","Legendary","Mythic","Divine","Transcendent"]:
            w[r] *= high_boost
        # Rebirth perk: shifts odds upward while preserving overall game pacing.
        shift = self.get_drop_shift_multiplier()
        w["Common"] *= max(0.30, 1.0 - 0.14 * self._upg("drop_shift"))
        w["Uncommon"] *= max(0.36, 1.0 - 0.10 * self._upg("drop_shift"))
        for r in ["Epic","Legendary","Mythic","Divine","Transcendent"]:
            w[r] *= shift
        if self.state.pity_counter >= PITY_EPIC: w["Epic"] *= 5; w["Legendary"] *= 3
        if self.state.pity_counter >= PITY_LEG:  w["Legendary"] *= 8; w["Mythic"] *= 4
        if self.state.lucky_rolls_remaining > 0:
            for r in ["Epic","Legendary","Mythic","Divine","Transcendent"]: w[r] *= 3
        if mystic:
            for r in ["Epic","Legendary","Mythic","Divine","Transcendent"]: w[r] *= 5
        boost = 1 + self.state.rebirths * 0.10
        for r in ["Rare","Epic","Legendary","Mythic","Divine","Transcendent"]: w[r] *= boost
        # Softcap runaway top tiers so progression still has room late game.
        caps = {"Epic":16, "Legendary":20, "Mythic":25, "Divine":30, "Transcendent":36}
        for r, cap in caps.items():
            w[r] = min(w[r], RARITIES[r]["weight"] * (cap + self.state.rebirths * 0.7))
        return w

    def perform_roll(self, guaranteed=None, mystic=False):
        w = self.compute_weights(guaranteed, mystic)
        rarity = random.choices(list(w), weights=list(w.values()), k=1)[0]
        title = random.choice(TITLES[rarity])
        if RARITY_ORDER.index(rarity) >= RARITY_ORDER.index("Rare"):
            self.state.pity_counter = 0
        else:
            self.state.pity_counter += 1
        if self.state.lucky_rolls_remaining > 0:
            self.state.lucky_rolls_remaining -= 1
        shards = RARITIES[rarity]["shard"]
        coins = max(1, RARITIES[rarity]["power"] // 5)
        self.state.inventory[title] = self.state.inventory.get(title, 0) + 1
        self.state.coins += coins; self.state.shards += shards
        if title not in self.state.collection:
            self.state.collection.append(title)
        self.gain_xp(RARITIES[rarity]["power"] * 2)
        self.state.total_rolls += 1
        if RARITY_ORDER.index(rarity) > RARITY_ORDER.index(self.state.highest_rarity_pulled):
            self.state.highest_rarity_pulled = rarity
        achs = self.check_achievements(rarity)
        self.save_game()
        # Post to global feed (Epic+)
        if self.username and RARITY_ORDER.index(rarity) >= RARITY_ORDER.index("Epic"):
            threading.Thread(target=self.db.post_roll,
                             args=(self.username, title, rarity), daemon=True).start()
        return title, rarity, shards, coins, achs

    def gain_xp(self, amt):
        self.state.xp += amt
        leveled = False
        while self.state.xp >= xp_for_level(self.state.level):
            self.state.xp -= xp_for_level(self.state.level)
            self.state.level += 1; leveled = True
        return leveled

    def check_achievements(self, last_rarity=None):
        s = self.state; newly = []; amap = {a["id"]: a for a in ACHIEVEMENTS}
        def unlock(aid):
            if aid not in s.achievements and aid in amap:
                s.achievements.append(aid); a = amap[aid]
                s.coins += a["rc"]; s.shards += a["rs"]; newly.append(a)
        if s.total_rolls >= 1:     unlock("first_roll")
        if s.total_rolls >= 100:   unlock("roll_100")
        if s.total_rolls >= 1000:  unlock("roll_1000")
        if s.total_wins >= 1:      unlock("first_arena")
        if s.total_merges >= 1:    unlock("first_merge")
        if s.rebirths >= 1:        unlock("first_rebirth")
        if s.total_boss_wins >= 1: unlock("first_boss")
        if len(s.collection) >= 20: unlock("collect_20")
        if len(s.collection) >= 48: unlock("collect_all")
        if s.pvp_wins >= 1:        unlock("first_pvp_win")
        if s.pvp_wins >= 10:       unlock("pvp_10")
        if last_rarity:
            ri = RARITY_ORDER.index
            if ri(last_rarity) >= ri("Epic"):         unlock("first_epic")
            if ri(last_rarity) >= ri("Legendary"):    unlock("first_leg")
            if ri(last_rarity) >= ri("Mythic"):       unlock("first_myth")
            if ri(last_rarity) >= ri("Divine"):       unlock("first_div")
            if ri(last_rarity) >= ri("Transcendent"): unlock("first_trans")
        return newly

    def can_merge(self, title):
        count = self.state.inventory.get(title, 0)
        rarity = self.get_title_rarity(title)
        if not rarity: return False, "Unknown title"
        if rarity == "Transcendent": return False, "Already max rarity"
        need = 1 if self.state.free_merge else 10
        if count < need: return False, f"Need {need} copies (have {count})"
        return True, ""

    def perform_merge(self, title):
        ok, reason = self.can_merge(title)
        if not ok: return None, None, reason
        rarity = self.get_title_rarity(title)
        cost = 1 if self.state.free_merge else 10
        self.state.inventory[title] -= cost
        if self.state.inventory[title] <= 0: del self.state.inventory[title]
        if self.state.free_merge: self.state.free_merge = False
        t, r, sh, co, achs = self.perform_roll(guaranteed=MERGE_MAP[rarity])
        self.state.total_merges += 1; achs += self.check_achievements(); self.save_game()
        return t, r, achs

    def perform_craft(self, recipe_id):
        recipe = next((r for r in CRAFT_RECIPES if r["id"] == recipe_id), None)
        if not recipe: return None, None, "Unknown recipe"
        if self.state.shards < recipe["cost_shards"]:
            return None, None, f"Need {recipe['cost_shards']} shards"
        if not self.is_unlocked("craft"):
            return None, None, f"Craft unlocks at level {UNLOCKS['craft']}"
        self.state.shards -= recipe["cost_shards"]
        if recipe["type"] == "guarantee":
            t, r, sh, co, achs = self.perform_roll(guaranteed=recipe["guarantee"])
        else:
            t, r, sh, co, achs = self.perform_roll(mystic=True)
        self.state.total_crafts += 1; achs += self.check_achievements(r); self.save_game()
        return t, r, achs

    def perform_arena_battle(self, idx):
        if not self.is_unlocked("arena"):
            return False, f"Arena unlocks at level {UNLOCKS['arena']}", None
        opp = ARENA_OPPONENTS[idx]; cd_key = f"arena_{idx}"
        rem = self.cooldown_remaining(cd_key, opp["cooldown"])
        if rem > 0: return False, f"Cooldown: {fmt_cd(rem)}", None
        win = (self.get_equipped_power() * random.uniform(0.65, 1.35)) >= opp["power"]
        if win:
            self.state.coins += opp["coins"]; self.state.shards += opp["shards"]
            self.gain_xp(opp["xp"]); self.state.total_wins += 1
        else:
            self.state.coins += opp["coins"] // 6; self.state.total_losses += 1
        self.set_cooldown(cd_key); achs = self.check_achievements(); self.save_game()
        return win, opp["name"], achs

    def perform_boss_battle(self, boss_id):
        boss = next((b for b in BOSSES if b["id"] == boss_id), None)
        if not boss: return False, "Unknown boss", None, None, []
        s = self.state
        if not self.is_unlocked("boss"):
            return False, f"Boss unlocks at level {UNLOCKS['boss']}", None, None, []
        if s.level < boss["req_level"]:
            return False, f"Need level {boss['req_level']}", None, None, []
        if RARITY_ORDER.index(s.highest_rarity_pulled) < RARITY_ORDER.index(boss["req_rarity"]):
            return False, f"Need {boss['req_rarity']}+ pulled", None, None, []
        rem = self.cooldown_remaining(f"boss_{boss_id}", boss["cooldown"])
        if rem > 0: return False, f"Cooldown: {fmt_cd(rem)}", None, None, []
        if s.boss_tokens < boss["token_cost"]:
            return False, f"Need {boss['token_cost']} tokens", None, None, []
        s.boss_tokens -= boss["token_cost"]
        win = (self.get_equipped_power() * random.uniform(0.6, 1.4)) >= boss["power"]
        title = rarity = None; achs = []
        if win:
            s.coins += boss["coins"]; s.shards += boss["shards"]
            self.gain_xp(boss["xp"]); s.total_boss_wins += 1
            title, rarity, _, _, a2 = self.perform_roll(guaranteed=boss["guarantee"]); achs += a2
            if boss_id == "boss_3" and "beat_titan" not in s.achievements:
                s.achievements.append("beat_titan"); s.coins += 2000; s.shards += 50
                achs.append(next(a for a in ACHIEVEMENTS if a["id"] == "beat_titan"))
            if boss_id == "boss_5" and "beat_abs" not in s.achievements:
                s.achievements.append("beat_abs"); s.coins += 20000; s.shards += 500
                achs.append(next(a for a in ACHIEVEMENTS if a["id"] == "beat_abs"))
            # Boss race check
            race = self.db.get_active_boss_race()
            if race and race["boss_id"] == boss_id:
                threading.Thread(target=self.db.claim_boss_race,
                                 args=(race["id"], self.username), daemon=True).start()
        else:
            s.coins += boss["coins"] // 8
        self.set_cooldown(f"boss_{boss_id}"); achs += self.check_achievements(); self.save_game()
        return win, boss["name"], title, rarity, achs

    def perform_purchase(self, item_id):
        item = next((i for i in SHOP_ITEMS if i["id"] == item_id), None)
        if not item: return False, "Unknown item"
        if self.state.coins < item["cost"]: return False, f"Need {item['cost']} coins"
        self.state.coins -= item["cost"]
        if item_id == "lucky_roll":
            self.state.lucky_rolls += 1; self.state.lucky_rolls_remaining += 10
        elif item_id == "free_merge": self.state.free_merge = True
        elif item_id == "shard_bundle": self.state.shards += 15
        elif item_id == "boss_token": self.state.boss_tokens += 1
        elif item_id == "xp_boost": self.gain_xp(250)
        elif item_id == "coin_shard": self.state.shards += 5
        self.save_game(); return True, f"Purchased {item['name']}!"

    def claim_daily(self):
        today = str(date.today())
        if self.state.last_daily == today: return False, "Already claimed today!"
        self.state.last_daily = today
        coins = 200 + self.state.rebirths * 50; shards = 5 + self.state.rebirths * 2
        self.state.coins += coins; self.state.shards += shards
        self.state.lucky_rolls_remaining += 1
        self.save_game(); return True, (coins, shards, 1)

    def equip_title(self, title):
        rarity = self.get_title_rarity(title)
        if rarity and title in self.state.inventory:
            self.state.equipped_title = title; self.state.equipped_rarity = rarity
            self.save_game(); return True
        return False

    def set_battle_titles(self, titles: list):
        owned = {t for t, c in (self.state.inventory or {}).items() if c and c > 0}
        self.state.battle_titles = [t for t in titles if t in owned][:3]
        self.save_game()

    def get_battle_titles_for_pvp(self):
        """Return up to 3 guaranteed-owned titles for PvP, no fake titles."""
        return get_best_titles(self.state, 3)

    def owns_title(self, title: str, count: int = 1) -> bool:
        return int((self.state.inventory or {}).get(title, 0) or 0) >= count

    def get_owned_titles(self):
        return [t for t, c in (self.state.inventory or {}).items() if c and c > 0]

    def _sanitize_battle_titles(self):
        owned = set(self.get_owned_titles())
        before = list(self.state.battle_titles or [])
        self.state.battle_titles = [t for t in before if t in owned][:3]
        if before != self.state.battle_titles:
            self.save_game()

    def can_rebirth(self):
        s = self.state; cost = 5000 + s.rebirths * 2000; reasons = []
        if s.level < UNLOCKS["rebirth"]: reasons.append(f"Level {UNLOCKS['rebirth']}+ required")
        if s.coins < cost: reasons.append(f"{cost:,} coins required")
        if RARITY_ORDER.index(s.highest_rarity_pulled) < RARITY_ORDER.index("Legendary"):
            reasons.append("Need Legendary+ pull")
        return len(reasons) == 0, reasons, cost

    def perform_rebirth(self):
        ok, reasons, cost = self.can_rebirth()
        if not ok: return False, reasons
        s = self.state; s.coins -= cost; s.rebirths += 1; new_luck = 1.0 + s.rebirths * 0.20
        gained_points = 1
        self.state = PlayerState(
            rebirths=s.rebirths, achievements=s.achievements, collection=s.collection,
            luck_multiplier=new_luck, lucky_rolls=s.lucky_rolls,
            coins=500 * s.rebirths, shards=50 * s.rebirths,
            pvp_wins=s.pvp_wins, pvp_losses=s.pvp_losses,
            rebirth_points=s.rebirth_points + gained_points,
            rebirth_upgrades=s.rebirth_upgrades,
            auto_roll_enabled=s.auto_roll_enabled,
            auto_roll_target=s.auto_roll_target,
            title_trades_completed=s.title_trades_completed,
            void_essence=s.void_essence,
            total_rift_wins=s.total_rift_wins)
        achs = self.check_achievements(); self.save_game(); return True, achs

    def can_buy_rebirth_upgrade(self, upg_id: str):
        upg = next((u for u in REBIRTH_UPGRADES if u["id"] == upg_id), None)
        if not upg:
            return False, "Unknown upgrade", 0, 0
        lvl = self._upg(upg_id)
        if lvl >= upg["max"]:
            return False, "Upgrade is maxed", lvl, 0
        cost = upg["costs"][lvl]
        if self.state.rebirth_points < cost:
            return False, f"Need {cost} rebirth points", lvl, cost
        return True, "", lvl, cost

    def buy_rebirth_upgrade(self, upg_id: str):
        ok, msg, lvl, cost = self.can_buy_rebirth_upgrade(upg_id)
        if not ok:
            return False, msg
        self.state.rebirth_points -= cost
        self.state.rebirth_upgrades[upg_id] = lvl + 1
        if upg_id == "auto_roll" and not self.state.auto_roll_target:
            self.state.auto_roll_target = "Legendary"
        self.save_game()
        return True, f"Upgraded {upg_id.replace('_', ' ').title()} to Lv.{lvl+1}"

    def can_send_trade(self, offered_title: str, offered_count: int):
        if offered_count <= 0:
            return False, "Offered count must be at least 1"
        have = self.state.inventory.get(offered_title, 0)
        if have < offered_count:
            return False, f"Not enough copies of {offered_title} (have {have})"
        return True, ""

    def can_enter_rift(self, rift_id: str):
        rift = next((r for r in ENDGAME_RIFTS if r["id"] == rift_id), None)
        if not rift:
            return False, "Unknown rift", None
        s = self.state
        if s.level < rift["req_level"]:
            return False, f"Need level {rift['req_level']}", rift
        if s.rebirths < rift["req_rebirths"]:
            return False, f"Need {rift['req_rebirths']} rebirths", rift
        if s.boss_tokens < rift["token_cost"]:
            return False, f"Need {rift['token_cost']} boss tokens", rift
        if s.shards < rift["shard_cost"]:
            return False, f"Need {rift['shard_cost']} shards", rift
        rem = self.cooldown_remaining(f"rift_{rift_id}", rift["cooldown"])
        if rem > 0:
            return False, f"Cooldown: {fmt_cd(rem)}", rift
        return True, "", rift

    def perform_rift_run(self, rift_id: str):
        ok, reason, rift = self.can_enter_rift(rift_id)
        if not ok:
            return False, reason, None, None, []
        s = self.state
        s.boss_tokens -= rift["token_cost"]
        s.shards -= rift["shard_cost"]
        player_power = max(1.0, self.get_equipped_power())
        player_power *= (1.0 + s.rebirths * 0.18)
        player_power *= random.uniform(0.80, 1.20)
        enemy_power = rift["base_power"] * (1.0 + s.rebirths * 0.10)
        enemy_power *= random.uniform(0.85, 1.18)
        win = player_power >= enemy_power
        title = rarity = None
        achs = []
        if win:
            s.coins += rift["reward_coins"]
            s.shards += rift["reward_shards"]
            s.void_essence += rift["reward_essence"]
            s.total_rift_wins += 1
            self.gain_xp(int(700 + s.rebirths * 120))
            title, rarity, _, _, a2 = self.perform_roll(guaranteed=rift["guarantee"])
            achs += a2
        else:
            s.coins += rift["reward_coins"] // 8
            s.void_essence += max(2, rift["reward_essence"] // 8)
        self.set_cooldown(f"rift_{rift_id}")
        self.save_game()
        return win, rift["name"], title, rarity, achs

    def get_title_rarity(self, title):
        for r, ts in TITLES.items():
            if title in ts: return r
        return None
    def get_equipped_power(self):
        return RARITIES.get(self.state.equipped_rarity or "", {}).get("power", 1)
    def is_unlocked(self, sys_):
        return self.state.level >= UNLOCKS.get(sys_, 999)
    def get_collection_count(self):
        return len(self.state.collection), sum(len(v) for v in TITLES.values())
    def get_inventory_sorted(self):
        result = [(t, c, self.get_title_rarity(t) or "Common")
                  for t, c in self.state.inventory.items()]
        result.sort(key=lambda x: (-RARITY_ORDER.index(x[2]), x[0]))
        return result


# ══════════════════════════════════════════════════════════════════════════════
#  DESIGN TOKENS
# ══════════════════════════════════════════════════════════════════════════════
BG      = "#070b14"; CARD    = "#0d1325"; CARD2   = "#111a30"
SURFACE = "#0b1020"; BORDER  = "#243252"; BORDER2 = "#2e3f67"
FG      = "#f1f5ff"; FG2     = "#9ba8c7"; GOLD    = "#ffb347"
GOLD2   = "#f59e0b"; RED     = "#fb7185"; GREEN   = "#4ade80"
BLUE    = "#60a5fa"; PURPLE  = "#8f46ff"; ACCENT  = "#6c7cff"
ACCENT2 = "#5c6ef7"; TOP_BTN = "#121d34"

_FONT = "Orbitron" if sys.platform != "darwin" else "Orbitron"
_BODY = "Inter" if sys.platform != "darwin" else "Inter"
_MONO = "JetBrains Mono" if sys.platform != "darwin" else "JetBrains Mono"
F_HERO  = (_FONT, 36, "bold"); F_TITLE = (_FONT, 22, "bold")
F_HEAD  = (_BODY, 15, "bold"); F_BODY  = (_BODY, 13)
F_SMALL = (_FONT, 11);         F_LABEL = (_FONT, 10)
F_MONO  = (_MONO, 12);         F_MONOS = (_MONO, 10)
MYTHIC_GRADIENT = ["#ff5b99", "#ff934d", "#ffd84d", "#68f0ff", "#7d7dff", "#bd6dff"]

def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def blend_colors(c1, c2, t):
    r1,g1,b1 = hex_to_rgb(c1); r2,g2,b2 = hex_to_rgb(c2)
    return f"#{int(r1+(r2-r1)*t):02x}{int(g1+(g2-g1)*t):02x}{int(b1+(b2-b1)*t):02x}"

def rarity_ui_color(rarity: str, phase: int = 0) -> str:
    if rarity == "Mythic":
        return MYTHIC_GRADIENT[phase % len(MYTHIC_GRADIENT)]
    if rarity == "Legendary":
        return GOLD
    if rarity == "Epic":
        return PURPLE
    if rarity == "Rare":
        return BLUE
    if rarity == "Uncommon":
        return GREEN
    return "#9ca3af"

def card_frame(parent, **kw):
    d = dict(fg_color=CARD, corner_radius=16, border_width=1, border_color=BORDER2)
    d.update(kw); return ctk.CTkFrame(parent, **d)

def card2_frame(parent, **kw):
    d = dict(fg_color=CARD2, corner_radius=12, border_width=1, border_color=BORDER)
    d.update(kw); return ctk.CTkFrame(parent, **d)

def lbl(parent, text, font=None, color=FG, **kw):
    return ctk.CTkLabel(parent, text=text, font=font or F_BODY, text_color=color, **kw)

def pill_btn(parent, text, cmd, fg=ACCENT, hover=ACCENT2, font=None, w=160, h=42, **kw):
    b = ctk.CTkButton(parent, text=text, command=cmd, fg_color=fg,
                         hover_color=hover, font=font or F_BODY,
                         width=w, height=h, corner_radius=21,
                         border_width=1, border_color=BORDER2,
                         text_color=FG, **kw)
    b.bind("<ButtonPress-1>", lambda e: b.configure(width=max(70, w - 6), height=max(28, h - 3)))
    b.bind("<ButtonRelease-1>", lambda e: b.configure(width=w, height=h))
    return b

def ghost_btn(parent, text, cmd, color=FG2, w=130, h=36, **kw):
    b = ctk.CTkButton(parent, text=text, command=cmd, fg_color="transparent",
                         hover_color=TOP_BTN, text_color=color, font=F_SMALL,
                         width=w, height=h, corner_radius=18,
                         border_width=1, border_color=BORDER2, **kw)
    b.bind("<Enter>", lambda e: b.configure(border_color=blend_colors(color if color.startswith("#") else ACCENT, "#ffffff", 0.3)))
    b.bind("<Leave>", lambda e: b.configure(border_color=BORDER2))
    return b

# ══════════════════════════════════════════════════════════════════════════════
#  VISUAL SYSTEMS
# ══════════════════════════════════════════════════════════════════════════════
class StarfieldBackground:
    """Parallax starfield + shooting stars."""
    def __init__(self, cv, w, h):
        self.cv = cv
        self.w = max(1, w)
        self.h = max(1, h)
        self.layers = [
            {"n": 42, "size": (1, 2), "speed": (0.15, 0.35), "twinkle": 0.08, "color": "#7f8cab"},
            {"n": 34, "size": (2, 3), "speed": (0.35, 0.75), "twinkle": 0.12, "color": "#a8b4d1"},
            {"n": 18, "size": (3, 4), "speed": (0.75, 1.2), "twinkle": 0.16, "color": "#d4e4ff"},
        ]
        self.stars = []
        self.shooters = deque(maxlen=8)
        for lid, layer in enumerate(self.layers):
            for _ in range(layer["n"]):
                self.stars.append(self._make_star(lid, initial=True))

    def _make_star(self, layer_id, initial=False):
        layer = self.layers[layer_id]
        x = random.uniform(0, self.w)
        y = random.uniform(0, self.h) if initial else random.uniform(-20, 0)
        size = random.randint(*layer["size"])
        speed = random.uniform(*layer["speed"])
        phase = random.uniform(0, math.tau)
        return [layer_id, x, y, size, speed, phase]

    def resize(self, w, h):
        self.w = max(1, w)
        self.h = max(1, h)

    def _spawn_shooter(self):
        if random.random() > 0.012:
            return
        sx = random.uniform(0, self.w * 0.9)
        sy = random.uniform(0, self.h * 0.25)
        self.shooters.append({
            "x": sx, "y": sy, "vx": random.uniform(6.0, 10.0),
            "vy": random.uniform(2.5, 4.2), "life": 1.0, "len": random.uniform(20, 38)
        })

    def tick(self):
        self.cv.delete("star")
        t = time.time()
        for idx, s in enumerate(self.stars):
            lid, x, y, size, speed, phase = s
            y += speed
            if y > self.h + 6:
                self.stars[idx] = self._make_star(lid)
                lid, x, y, size, speed, phase = self.stars[idx]
            else:
                self.stars[idx][2] = y
            tw = (math.sin(t * (1.5 + lid * 0.45) + phase) * self.layers[lid]["twinkle"]) + 0.7
            base = hex_to_rgb(self.layers[lid]["color"])
            col = f"#{min(255, int(base[0]*tw)):02x}{min(255, int(base[1]*tw)):02x}{min(255, int(base[2]*tw)):02x}"
            self.cv.create_oval(x-size, y-size, x+size, y+size, fill=col, outline="", tags="star")
        self._spawn_shooter()
        kept = deque(maxlen=8)
        for s in self.shooters:
            s["x"] += s["vx"]; s["y"] += s["vy"]; s["life"] -= 0.04
            if s["life"] <= 0 or s["x"] > self.w + 40 or s["y"] > self.h + 40:
                continue
            lx = s["x"] - s["len"]; ly = s["y"] - s["len"] * 0.35
            a = max(0.25, s["life"])
            c = blend_colors("#d6e4ff", "#6c7cff", 1 - a)
            self.cv.create_line(lx, ly, s["x"], s["y"], fill=c, width=2, tags="star")
            kept.append(s)
        self.shooters = kept

class ParticleSystem:
    """Lightweight particles for sparkles, bursts, and spirals."""
    def __init__(self):
        self._items = []

    def emit_burst(self, cv, cx, cy, color, n=26, speed=(1.8, 6.2)):
        for _ in range(n):
            ang = random.uniform(0, math.tau)
            spd = random.uniform(speed[0], speed[1])
            self._items.append({
                "cv": cv, "x": cx, "y": cy,
                "vx": math.cos(ang) * spd, "vy": math.sin(ang) * spd,
                "life": 1.0, "decay": random.uniform(0.025, 0.06),
                "size": random.uniform(2.0, 6.5), "color": color, "tag": "particle"
            })

    def emit_spiral(self, cv, cx, cy, n=42):
        for i in range(n):
            ang = (i / max(1, n)) * math.tau
            spd = random.uniform(1.6, 3.8)
            self._items.append({
                "cv": cv, "x": cx, "y": cy, "ang": ang, "spin": random.uniform(0.18, 0.35),
                "vx": math.cos(ang) * spd, "vy": math.sin(ang) * spd,
                "life": 1.0, "decay": random.uniform(0.02, 0.045),
                "size": random.uniform(2.0, 5.0), "color": MYTHIC_GRADIENT[i % len(MYTHIC_GRADIENT)],
                "tag": "particle"
            })

    def tick(self):
        alive = []
        canvases = {p["cv"] for p in self._items}
        for cv in canvases:
            try:
                cv.delete("particle")
            except Exception:
                pass
        for p in self._items:
            p["life"] -= p["decay"]
            if p["life"] <= 0:
                continue
            if "ang" in p:
                p["ang"] += p["spin"]
                p["vx"] = (p["vx"] * 0.92) + math.cos(p["ang"]) * 0.6
                p["vy"] = (p["vy"] * 0.92) + math.sin(p["ang"]) * 0.6
            p["x"] += p["vx"]
            p["y"] += p["vy"]
            p["vy"] += 0.05
            sz = max(1, int(p["size"] * p["life"]))
            col = blend_colors(p["color"], BG, 1 - p["life"])
            try:
                p["cv"].create_oval(p["x"] - sz, p["y"] - sz, p["x"] + sz, p["y"] + sz,
                                    fill=col, outline="", tags=p["tag"])
                alive.append(p)
            except Exception:
                pass
        self._items = alive

class GlowFrame(ctk.CTkFrame):
    """Frame with rarity-reactive glow border."""
    def __init__(self, parent, rarity="Common", **kw):
        super().__init__(parent, fg_color=CARD, corner_radius=18, border_width=2, border_color=BORDER2, **kw)
        self._phase = 0
        self._rarity = rarity
        self._pulse = False
        self.set_rarity(rarity)

    def set_rarity(self, rarity: str):
        self._rarity = rarity
        c = rarity_ui_color(rarity, self._phase)
        bw = 1 if rarity == "Common" else 2
        self.configure(border_color=c if rarity != "Common" else "#6b7280", border_width=bw)
        self._pulse = rarity in {"Legendary", "Mythic"}

    def tick(self):
        if not self.winfo_exists():
            return
        self._phase += 1
        c = rarity_ui_color(self._rarity, self._phase)
        if self._pulse:
            t = 0.5 + 0.5 * math.sin(self._phase * 0.25)
            self.configure(border_color=blend_colors(c, "#ffffff", 0.2 * t))
        elif self._rarity in {"Epic", "Rare", "Uncommon"}:
            self.configure(border_color=blend_colors(c, CARD, 0.25))

class LootCard(ctk.CTkFrame):
    """Inventory tile card."""
    def __init__(self, parent, title, rarity, count, chance_txt, on_click):
        col = rarity_ui_color(rarity)
        super().__init__(parent, fg_color=CARD, corner_radius=14, border_width=1, border_color=blend_colors(col, CARD, 0.25))
        self._base = blend_colors(col, CARD, 0.25)
        self._hover = blend_colors(col, "#ffffff", 0.2)
        self._on_click = on_click
        bar = ctk.CTkFrame(self, fg_color=col, width=6, corner_radius=6)
        bar.pack(side="left", fill="y", padx=(0, 8), pady=8)
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(side="left", fill="both", expand=True, padx=(2, 10), pady=8)
        lbl(body, rarity.upper(), color=col, font=F_LABEL).pack(anchor="w")
        lbl(body, title, color=FG, font=F_BODY, wraplength=220, justify="left").pack(anchor="w", pady=(2, 1))
        lbl(body, chance_txt, color=FG2, font=F_MONOS).pack(anchor="w")
        lbl(self, f"×{count}", color=FG2, font=F_MONO).pack(side="right", padx=10)
        self.bind("<Enter>", lambda e: self.configure(border_color=self._hover, fg_color=blend_colors(CARD, col, 0.08)))
        self.bind("<Leave>", lambda e: self.configure(border_color=self._base, fg_color=CARD))
        self.bind("<Button-1>", lambda e: self._on_click())
        for child in self.winfo_children():
            child.bind("<Button-1>", lambda e: self._on_click())

class RollAnimation:
    """Encapsulates roll sequence and reveal animation timing."""
    def __init__(self, app):
        self.app = app
        self.seq = []
        self.idx = 0
        self.mode = "cascade"

    def run(self):
        self.mode = random.choice(["cascade", "stutter", "surge"])
        pre = random.randint(8, 12)
        seq = []
        for i in range(pre):
            if self.mode == "surge":
                pool = RARITY_ORDER[:min(6, 3 + (i // 2))]
            elif self.mode == "stutter":
                pool = RARITY_ORDER[:4] if i % 2 == 0 else RARITY_ORDER[:6]
            else:
                pool = RARITY_ORDER[:5]
            seq.append(random.choice(pool))
        self.seq = seq
        self.idx = 0
        self._step()

    def _step(self):
        if self.idx < len(self.seq):
            rarity = self.seq[self.idx]
            c = rarity_ui_color(rarity, self.idx)
            pick = random.choice(TITLES[rarity])
            if self.mode == "stutter" and self.idx % 3 == 0:
                pick = f"…{pick.split(' ')[0]}…"
            if self.mode == "surge" and self.idx > len(self.seq) // 2:
                pick = pick.upper()
            self.app._set_roll_preview(
                pick,
                rarity,
                c,
                reward_text=""
            )
            ring_step = 16 if self.mode == "stutter" else (28 if self.mode == "surge" else 22)
            self.app._draw_ring((self.app._ring_angle + ring_step + self.idx * (6 if self.mode == "surge" else 4)) % 360)
            self.app.play_roll_sound()
            self.idx += 1
            speed = self.app.engine.get_roll_speed_multiplier()
            if self.mode == "stutter":
                base = 28 + (6 if self.idx % 2 else 24) + self.idx * 10
            elif self.mode == "surge":
                base = 26 + self.idx * 11
            else:
                base = 36 + self.idx * 14
            delay = max(18, int(base / speed))
            self.app.after(delay, self._step)
            return
        self.app._finish_roll_reveal()


# ══════════════════════════════════════════════════════════════════════════════
#  LOGIN SCREEN
# ══════════════════════════════════════════════════════════════════════════════
class LoginScreen(ctk.CTkToplevel):
    def __init__(self, db: Database, on_success):
        super().__init__()
        self.db = db; self.on_success = on_success
        self.title("LUL'S RNG — Login"); self.geometry("460x520")
        self.resizable(False, False); self.configure(fg_color=BG)
        self.grab_set()
        self._build()

    def _build(self):
        lbl(self, "⚡  LUL'S RNG",
            font=(_FONT, 28, "bold"), color=GOLD).pack(pady=(40, 4))
        lbl(self, "Enter your username & password to play.",
            color=FG2, font=F_SMALL).pack(pady=(0, 30))

        box = card_frame(self, width=360, height=280)
        box.pack(padx=50); box.pack_propagate(False)

        lbl(box, "Username", color=FG2, font=F_LABEL).pack(anchor="w", padx=20, pady=(20,2))
        self.user_entry = ctk.CTkEntry(box, width=320, height=40, corner_radius=12,
                                       fg_color=CARD2, border_color=BORDER2,
                                       text_color=FG, font=F_BODY)
        self.user_entry.pack(padx=20)

        lbl(box, "Password", color=FG2, font=F_LABEL).pack(anchor="w", padx=20, pady=(12,2))
        self.pass_entry = ctk.CTkEntry(box, width=320, height=40, corner_radius=12,
                                       fg_color=CARD2, border_color=BORDER2,
                                       text_color=FG, font=F_BODY, show="•")
        self.pass_entry.pack(padx=20)

        self.err_lbl = lbl(box, "", color=RED, font=F_SMALL)
        self.err_lbl.pack(pady=(8,0))

        brow = ctk.CTkFrame(box, fg_color="transparent"); brow.pack(pady=12)
        pill_btn(brow, "Login",    self._login,    fg=ACCENT, hover=ACCENT2, w=130, h=40).pack(side="left", padx=6)
        pill_btn(brow, "Register", self._do_register, fg="#166534", hover="#14532d", w=130, h=40).pack(side="left", padx=6)

        if not self.db.conn:
            warn = "⚠ Offline mode — data saves locally only"
            if "timeout expired" in (self.db.last_error or "").lower():
                warn = "⚠ Network blocked DB port (common on school Wi-Fi). Use hotspot/VPN for online."
            lbl(self, warn, color="#f59e0b", font=F_LABEL, wraplength=420, justify="center").pack(pady=(12,0))

        pill_btn(self, "Play Offline", self._offline,
                 fg=CARD2, hover=CARD, w=200, h=36).pack(pady=(12,0))

    def _get_creds(self):
        return self.user_entry.get().strip(), self.pass_entry.get()

    def _login(self):
        u, p = self._get_creds()
        if not u or not p: self.err_lbl.configure(text="Enter username and password"); return
        ok, result = self.db.login(u, p)
        if ok:
            self.on_success(u, result)
            self.destroy()
        else:
            self.err_lbl.configure(text=str(result))

    def _do_register(self):
        u, p = self._get_creds()
        if not u or not p: self.err_lbl.configure(text="Enter username and password"); return
        ok, msg = self.db.register(u, p)
        if ok:
            self.err_lbl.configure(text="Account created! Logging in…", text_color=GREEN)
            self.after(800, self._login)
        else:
            self.err_lbl.configure(text=msg)

    def _offline(self):
        self.on_success("", None)
        self.destroy()


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN APP
# ══════════════════════════════════════════════════════════════════════════════
class LulsRNG(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.withdraw()   # hide until login done
        api_base, api_token = load_online_api_config()
        if api_base:
            self.db = HttpDatabase(api_base, api_token)
            print(f"[NET] API mode enabled: {api_base}")
        else:
            self.db = Database()
        self.engine: Optional[GameEngine] = None
        self.username = ""
        self._rolling = False
        self._boss_fighting: set = set()
        self._recent_rolls: list = []
        self._particle_system = ParticleSystem()
        self._roll_anim = RollAnimation(self)
        self._starfield = None
        self._mythic_glow_running = False
        self._live_tip_idx = 0
        self._live_tick_n = 0
        self._last_open_tab = "🎲 Roll"
        self._last_unlock_level_checked = 1
        self._sound_ready = False
        self._sounds = {}
        self._is_closing = False

        self.title(f"⚡  {GAME_TITLE}")
        self.geometry("1340x880"); self.minsize(1100, 740)
        self.configure(fg_color=BG)
        ctk.set_appearance_mode("dark")

        # Show login
        login = LoginScreen(self.db, self._on_login)
        login.protocol("WM_DELETE_WINDOW", self.destroy)
        self.wait_window(login)

    def _on_login(self, username: str, state: Optional[PlayerState]):
        self.username = username
        self.engine = GameEngine(self.db, username)
        if state:
            self.engine.state = state
        self._init_sound()
        self.deiconify()
        self._build_ui()
        self._refresh_all()
        atexit.register(self._final_sync)
        self.after(800,  self._check_daily_launch)
        self.after(16,   self._anim_tick)
        self.after(1000, self._slow_tick)
        self.after(5000, self._online_tick)  # poll online every 5s

    def _ui_after(self, delay_ms: int, fn):
        """Thread-safe UI scheduling; ignores callbacks when app is closing/destroyed."""
        if self._is_closing:
            return
        try:
            if self.winfo_exists():
                self.after(delay_ms, fn)
        except (RuntimeError, tk.TclError):
            pass

    # ── animation loops ───────────────────────────────────────────────────────

    def _anim_tick(self):
        if self._starfield:
            self._starfield.tick()
        self._particle_system.tick()
        if hasattr(self, "_ring_angle") and self._rolling:
            self._ring_angle = (self._ring_angle + 6) % 360
            self._draw_ring(self._ring_angle)
        if hasattr(self, "roll_glow"):
            self.roll_glow.tick()
        self.after(16, self._anim_tick)

    def _slow_tick(self):
        self._refresh_arena_cds()
        self._refresh_boss_cds()
        self._refresh_endgame_cds()
        self._tick_live_status()
        self.after(1000, self._slow_tick)

    def _online_tick(self):
        """Poll DB for online players, pending requests, global feed."""
        def _bg():
            try:
                self.db.reconnect_if_needed()
                if self.engine and self.username:
                    # heartbeat + cloud sync for online level/title presence
                    self.db.save_player(self.username, self.engine.state)
                self._cached_online = self.db.get_online_players()
                self._cached_feed   = self.db.get_recent_rolls()
                self._cached_inbox  = self.db.get_pending_requests(self.username) if self.username else []
                self._ui_after(0, self._render_online)
            except:
                pass
        threading.Thread(target=_bg, daemon=True).start()
        self.after(5000, self._online_tick)

    # ── sound hooks ───────────────────────────────────────────────────────────

    def _init_sound(self):
        if not pygame:
            return
        try:
            pygame.mixer.init()
            base = os.path.join(os.path.dirname(__file__), "assets", "sounds")
            for key, fn in {
                "roll": "roll.wav",
                "rare": "rare.wav",
                "legendary": "legendary.wav",
            }.items():
                p = os.path.join(base, fn)
                if os.path.exists(p):
                    self._sounds[key] = pygame.mixer.Sound(p)
            self._sound_ready = True
        except Exception:
            self._sound_ready = False

    def _play_sound(self, key: str):
        if not self._sound_ready:
            return
        try:
            snd = self._sounds.get(key)
            if snd:
                snd.play()
        except Exception:
            pass

    def play_roll_sound(self):
        self._play_sound("roll")

    def play_rare_sound(self):
        self._play_sound("rare")

    def play_legendary_sound(self):
        self._play_sound("legendary")

    # Compatibility wrapper for existing battle/boss VFX calls.
    def _spawn_particles(self, cv, cx, cy, color, n=30):
        self._particle_system.emit_burst(cv, cx, cy, color, n=n)

    # ── level-up flash ────────────────────────────────────────────────────────

    def _show_levelup(self, new_level):
        try:
            flash = tk.Frame(self, bg="#6366f1")
            flash.place(x=0, y=0, relwidth=1, relheight=1)
            cv = tk.Canvas(flash, bg="#6366f1", highlightthickness=0)
            cv.place(x=0, y=0, relwidth=1, relheight=1)
            W, H = self.winfo_width(), self.winfo_height()
            cv.create_text(W//2, H//2, text="LEVEL UP!",
                font=(_FONT, 52, "bold"), fill="white", anchor="center")
            cv.create_text(W//2, H//2+70, text=f"Level {new_level}",
                font=(_FONT, 24), fill="#c7d2fe", anchor="center")
            def fade(step):
                if not flash.winfo_exists(): return
                if step > 12: flash.destroy(); return
                c = blend_colors("#6366f1", BG, step/12)
                try: flash.configure(bg=c); cv.configure(bg=c)
                except: pass
                self.after(60, lambda: fade(step+1))
            self.after(600, lambda: fade(0))
        except: pass

    # ══════════════════════════════════════════════════════════════════════════
    #  BUILD UI
    # ══════════════════════════════════════════════════════════════════════════
    def _build_ui(self):
        # Top bar
        top = ctk.CTkFrame(self, fg_color=CARD, height=68, corner_radius=0, border_width=1, border_color=BORDER2)
        top.pack(fill="x"); top.pack_propagate(False)

        logo = ctk.CTkFrame(top, fg_color="transparent"); logo.pack(side="left", padx=20)
        lbl(logo, "⚡", font=(_FONT, 19), color=GOLD).pack(side="left")
        lbl(logo, f" {GAME_TITLE}", font=(_FONT, 16, "bold"), color=FG).pack(side="left")
        if self.username:
            lbl(logo, f"  ·  {self.username}", font=F_SMALL, color=FG2).pack(side="left")

        sf = ctk.CTkFrame(top, fg_color="transparent"); sf.pack(side="right", padx=16)
        quick = ctk.CTkFrame(top, fg_color="transparent")
        quick.pack(side="right", padx=(0, 8))
        pill_btn(quick, "🎁 Daily", self._quick_daily_claim, fg="#4f3a12", hover="#6b4e18", w=102, h=34).pack(side="left", padx=4)
        pill_btn(quick, "↻ Sync", self._quick_sync, fg="#1f3f7b", hover="#2552a6", w=88, h=34).pack(side="left", padx=4)

        def stat_pill(color):
            p = ctk.CTkFrame(sf, fg_color=CARD2, corner_radius=18, border_width=1, border_color=blend_colors(color, BORDER2, 0.45))
            p.pack(side="left", padx=4)
            l = lbl(p, "", color=color, font=F_SMALL); l.pack(padx=12, pady=5)
            return l
        self.lbl_level  = stat_pill(GREEN)
        self.lbl_coins  = stat_pill(GOLD)
        self.lbl_shards = stat_pill(BLUE)
        self.lbl_tokens = stat_pill(RED)
        self.lbl_lucky  = stat_pill(PURPLE)

        self.xp_bar = ctk.CTkProgressBar(self, height=3, corner_radius=0,
                                          fg_color=SURFACE, progress_color=ACCENT)
        self.xp_bar.pack(fill="x"); self.xp_bar.set(0)

        # Live status strip (makes the app feel active and informative)
        live = ctk.CTkFrame(self, fg_color="#0b1220", corner_radius=0, height=26)
        live.pack(fill="x")
        live.pack_propagate(False)
        self.live_status_lbl = lbl(live, "Live: Initializing systems...", color=FG2, font=F_LABEL)
        self.live_status_lbl.pack(side="left", padx=12)

        # Tabs
        self.tabs = ctk.CTkTabview(
            self, fg_color=SURFACE,
            segmented_button_fg_color="#0b1220",
            segmented_button_unselected_color="#101827",
            segmented_button_unselected_hover_color="#162032",
            segmented_button_selected_color="#1d4ed8",
            segmented_button_selected_hover_color="#1e40af",
            text_color=FG2, corner_radius=0, command=self._on_tab_selected)
        self.tabs.pack(fill="both", expand=True)
        try:
            self.tabs._segmented_button.configure(font=(_FONT, 11, "bold"))
        except Exception:
            pass

        tabs = ["🎲 Roll","🎒 Inventory","⚔️ Arena","💀 Boss",
                "🛒 Shop","⚗️ Craft","📖 Collection",
                "🌍 Online","🏆 Leaderboard","⚔ PvP","📊 Stats","♻️ Rebirth","🌌 Endgame","📰 Updates"]
        for t in tabs: self.tabs.add(t)

        self._build_roll_tab()
        self._build_inv_tab()
        self._build_arena_tab()
        self._build_boss_tab()
        self._build_shop_tab()
        self._build_craft_tab()
        self._build_collection_tab()
        self._build_online_tab()
        self._build_leaderboard_tab()
        self._build_pvp_tab()
        self._build_stats_tab()
        self._build_rebirth_tab()
        self._build_endgame_tab()
        self._build_updates_tab()
        self._last_unlock_level_checked = self.engine.state.level if self.engine else 1
        self._update_tab_access()

    # ══════════════════════════════════════════════════════════════════════════
    #  ROLL TAB
    # ══════════════════════════════════════════════════════════════════════════
    def _build_roll_tab(self):
        tab = self.tabs.tab("🎲 Roll"); tab.configure(fg_color=BG)
        self._sf_cv = tk.Canvas(tab, bg=BG, highlightthickness=0)
        self._sf_cv.place(x=0, y=0, relwidth=1, relheight=1)

        center = ctk.CTkFrame(tab, fg_color="transparent")
        center.place(relx=0.5, rely=0.5, anchor="center")

        lbl(center, "ROLL FOR YOUR TITLE", font=(_FONT, 13, "bold"), color=FG2).pack(pady=(0, 10))

        CW, CH = 560, 240
        self.roll_glow = GlowFrame(center, rarity="Common", width=CW + 12, height=CH + 12)
        self.roll_glow.pack(pady=6)
        self.roll_glow.pack_propagate(False)
        self.roll_cv = tk.Canvas(self.roll_glow, width=CW, height=CH, bg=CARD, highlightthickness=0)
        self.roll_cv.pack(padx=6, pady=6)
        self._ring_angle = 0
        self._roll_card_bg = self.roll_cv.create_rectangle(4, 4, CW - 4, CH - 4, outline=BORDER2, width=1, fill=CARD)
        self._cv_arc_deco = self.roll_cv.create_arc(130, 26, CW - 130, 104, start=20, extent=140, style=tk.ARC, outline=ACCENT, width=2)
        self._cv_title  = self.roll_cv.create_text(CW//2, CH//2-16, text="???",
            font=(_FONT, 36, "bold"), fill=FG2, anchor="center")
        self._cv_rarity = self.roll_cv.create_text(CW//2, CH//2+34, text="◆ COMMON ◆",
            font=(_BODY, 16, "bold"), fill=FG2, anchor="center")
        self._cv_reward = self.roll_cv.create_text(CW//2, CH-22, text="+0 coins",
            font=(_MONO, 10), fill=GOLD, anchor="center")
        self._ring_arc  = self.roll_cv.create_arc(
            14, 14, CW-14, CH-14, start=0, extent=64, style=tk.ARC, outline=ACCENT, width=3)

        def _init_sf(e=None):
            w = tab.winfo_width() or 1300; h = tab.winfo_height() or 800
            self._sf_cv.configure(width=w, height=h)
            if not self._starfield:
                self._starfield = StarfieldBackground(self._sf_cv, w, h)
            else:
                self._starfield.resize(w, h)
        tab.bind("<Configure>", _init_sf)

        brow = ctk.CTkFrame(center, fg_color="transparent"); brow.pack(pady=18)
        self.roll_btn = pill_btn(brow, "⚡ ROLL", self._do_roll,
                                  font=(_FONT, 16, "bold"), w=200, h=58, fg=ACCENT, hover=ACCENT2)
        self.roll_btn.pack(side="left", padx=8)
        self.roll_btn.bind("<Enter>", lambda e: self.roll_btn.configure(border_color=blend_colors(ACCENT, "#ffffff", 0.35)))
        self.roll_btn.bind("<Leave>", lambda e: self.roll_btn.configure(border_color=BORDER2))
        self.lucky_btn = pill_btn(brow, "🔥 Lucky", self._activate_lucky,
                                   fg="#7c2d12", hover="#9a3412", w=130, h=58)
        self.lucky_btn.pack(side="left", padx=6)
        self.lucky_btn.bind("<Enter>", lambda e: self.lucky_btn.configure(border_color=blend_colors(GOLD, "#ffffff", 0.3)))
        self.lucky_btn.bind("<Leave>", lambda e: self.lucky_btn.configure(border_color=BORDER2))
        self.auto_roll_switch = ctk.CTkSwitch(
            brow, text="Auto", width=72, height=28, command=self._toggle_auto_roll,
            progress_color=ACCENT, button_color=FG, button_hover_color="#cbd5e1", state="disabled")
        self.auto_roll_switch.pack(side="left", padx=8)
        self.auto_target_menu = ctk.CTkOptionMenu(
            brow, values=["Epic","Legendary","Mythic","Divine","Transcendent"],
            width=136, height=34, command=self._set_auto_target,
            fg_color=CARD2, button_color=ACCENT2, button_hover_color=ACCENT)
        self.auto_target_menu.pack(side="left", padx=4)

        irow = ctk.CTkFrame(center, fg_color="transparent"); irow.pack(pady=2)
        self.lbl_pity  = lbl(irow, "", color=FG2, font=F_LABEL); self.lbl_pity.pack(side="left", padx=14)
        self.lbl_rolls = lbl(irow, "", color=FG2, font=F_LABEL); self.lbl_rolls.pack(side="left", padx=14)
        self.lbl_auto  = lbl(irow, "", color=FG2, font=F_LABEL); self.lbl_auto.pack(side="left", padx=14)

        lbl(center, "RECENT PULLS", font=F_LABEL, color=FG2).pack(pady=(14,4))
        recent_wrap = ctk.CTkFrame(center, fg_color="transparent")
        recent_wrap.pack()
        self.recent_cv = tk.Canvas(
            recent_wrap, width=520, height=72, bg=BG, highlightthickness=0,
            bd=0, relief="flat")
        self.recent_cv.pack(fill="x")
        self.recent_xbar = ctk.CTkScrollbar(
            recent_wrap, orientation="horizontal", command=self.recent_cv.xview,
            width=520, height=10, fg_color="transparent", button_color=CARD2,
            button_hover_color=ACCENT2)
        self.recent_xbar.pack(fill="x", pady=(2, 0))
        self.recent_cv.configure(xscrollcommand=self.recent_xbar.set)
        self.recent_inner = ctk.CTkFrame(self.recent_cv, fg_color="transparent")
        self.recent_cv.create_window((0, 0), window=self.recent_inner, anchor="nw")
        self.recent_inner.bind(
            "<Configure>",
            lambda e: self.recent_cv.configure(scrollregion=self.recent_cv.bbox("all")))
        self._build_roll_friends_panel(tab)

    def _build_roll_friends_panel(self, roll_tab):
        panel = card_frame(roll_tab, width=300, height=218, border_color=blend_colors(ACCENT, BORDER2, 0.3))
        panel.place(relx=0.985, rely=0.985, anchor="se")
        panel.pack_propagate(False)
        self.roll_friends_panel = panel
        hdr = ctk.CTkFrame(panel, fg_color="transparent")
        hdr.pack(fill="x", padx=10, pady=(10, 4))
        lbl(hdr, "Friends", font=F_HEAD, color=FG).pack(side="left")
        ghost_btn(hdr, "Open", self._open_friends_tab, color=BLUE, w=72, h=28).pack(side="right")
        row = ctk.CTkFrame(panel, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=(0, 6))
        self.roll_friend_entry = ctk.CTkEntry(
            row, width=160, height=30, corner_radius=10, placeholder_text="Add username...",
            fg_color=CARD2, border_color=BORDER2, text_color=FG, font=F_SMALL
        )
        self.roll_friend_entry.pack(side="left", padx=(0, 6))
        pill_btn(row, "Add", self._send_friend_request_roll, fg="#14532d", hover="#166534", w=58, h=30, font=F_LABEL).pack(side="left")
        self.roll_friend_status = lbl(panel, "", color=FG2, font=F_LABEL)
        self.roll_friend_status.pack(anchor="w", padx=12, pady=(0, 2))
        self.roll_friend_list = ctk.CTkScrollableFrame(panel, fg_color="transparent", height=120)
        self.roll_friend_list.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        if not self.username:
            self.roll_friend_status.configure(text="Offline mode: friends unavailable")

    def _open_friends_tab(self):
        try:
            self.tabs.set("⚔ PvP")
        except Exception:
            pass

    def _refresh_roll_friends_async(self):
        if not self.username or not hasattr(self, "roll_friend_list"):
            return
        def _bg():
            friends = self.db.get_friends(self.username)
            self._ui_after(0, lambda: self._render_roll_friends(friends))
        threading.Thread(target=_bg, daemon=True).start()

    def _render_roll_friends(self, friends: list):
        if not hasattr(self, "roll_friend_list"):
            return
        for w in self.roll_friend_list.winfo_children():
            w.destroy()
        if not friends:
            lbl(self.roll_friend_list, "No friends yet.", color=FG2, font=F_LABEL).pack(anchor="w", padx=6, pady=4)
            return
        for fr in friends[:12]:
            row = ctk.CTkFrame(self.roll_friend_list, fg_color=CARD2, corner_radius=8, border_width=1, border_color=BORDER)
            row.pack(fill="x", pady=2)
            r2 = ctk.CTkFrame(row, fg_color="transparent")
            r2.pack(fill="x", padx=8, pady=5)
            lbl(r2, fr, color=FG, font=F_LABEL).pack(side="left")
            ghost_btn(r2, "Challenge", lambda u=fr: self._open_player_profile(u), color=PURPLE, w=84, h=24).pack(side="right")

    def _set_roll_preview(self, title: str, rarity: str, color: str, reward_text: str = ""):
        self.roll_glow.set_rarity(rarity)
        self.roll_cv.itemconfigure(self._cv_title, text=title, fill=color)
        self.roll_cv.itemconfigure(self._cv_rarity, text=f"◆ {rarity.upper()} ◆", fill=color)
        self.roll_cv.itemconfigure(self._cv_reward, text=reward_text or "", fill=GOLD if rarity != "Common" else FG2)
        self.roll_cv.itemconfigure(self._cv_arc_deco, outline=blend_colors(color, ACCENT, 0.35))

    def _draw_ring(self, angle):
        try: self.roll_cv.itemconfigure(self._ring_arc, start=angle, extent=90)
        except: pass

    def _do_roll(self):
        if self._rolling: return
        self._rolling = True
        self.roll_btn.configure(state="disabled")
        self.roll_cv.itemconfigure(self._ring_arc, outline=ACCENT)
        self._roll_anim.run()

    def _finish_roll_reveal(self):
        lvl_before = self.engine.state.level
        title, rarity, shards, coins, achs = self.engine.perform_roll()
        c = rarity_ui_color(rarity)
        self.roll_glow.set_rarity(rarity)
        self.roll_cv.itemconfigure(self._roll_card_bg, fill=blend_colors(CARD, c, 0.12))
        self.roll_cv.itemconfigure(self._ring_arc, outline=c)
        self.roll_cv.itemconfigure(self._cv_title, text="", fill=c)
        self.roll_cv.itemconfigure(self._cv_rarity, text="", fill=c)
        reward_txt = f"+{coins} coins" + (f"   +{shards} shards" if shards else "")
        self.roll_cv.itemconfigure(self._cv_reward, text="", fill=GOLD)
        ri = RARITY_ORDER.index(rarity)
        self._reveal_card_anim(title, rarity, reward_txt, c, 0, lvl_before, achs)

    def _reveal_card_anim(self, title, rarity, reward_txt, color, step, lvl_before, achs):
        if not self.roll_cv.winfo_exists():
            return
        if step < 4:
            flick = blend_colors(CARD, "#ffffff", 0.06 * (step + 1))
            self.roll_cv.itemconfigure(self._roll_card_bg, fill=flick)
            self.after(36, lambda: self._reveal_card_anim(title, rarity, reward_txt, color, step + 1, lvl_before, achs))
            return
        if step < 9:
            t = (step - 4) / 5.0
            reveal_col = blend_colors(FG2, color, t)
            self.roll_cv.itemconfigure(self._cv_title, text=title, fill=reveal_col)
            self.roll_cv.itemconfigure(self._cv_rarity, text=f"◆ {rarity.upper()} ◆", fill=reveal_col)
            self.roll_cv.itemconfigure(self._cv_reward, text=reward_txt)
            self.after(40, lambda: self._reveal_card_anim(title, rarity, reward_txt, color, step + 1, lvl_before, achs))
            return
        self._finalize_roll_outcome(title, rarity, reward_txt, color, lvl_before, achs)

    def _finalize_roll_outcome(self, title, rarity, reward_txt, color, lvl_before, achs):
        ri = RARITY_ORDER.index(rarity)
        if ri >= RARITY_ORDER.index("Rare"):
            self.play_rare_sound()
            self._particle_system.emit_burst(self.roll_cv, 280, 120, color, n=22 if ri < RARITY_ORDER.index("Legendary") else 38)
            self._title_glow(color, 0, 7 if ri < RARITY_ORDER.index("Legendary") else 11)
        if ri >= RARITY_ORDER.index("Legendary"):
            self.play_legendary_sound()
            self._screen_shake(7)
            self._particle_system.emit_burst(self.roll_cv, 280, 120, GOLD, n=54)
            odds = self._rarity_odds_text(rarity)
            self._big_notify(f"GLOBAL DROP\n{self.username or 'Offline Player'} rolled {rarity.upper()}\n{title}\n{odds}", color)
        if rarity == "Mythic":
            self._particle_system.emit_spiral(self.roll_cv, 280, 120, n=58)
            self._start_mythic_glow()
        self._add_recent(title, rarity)
        self._rolling = False
        self.roll_btn.configure(state="normal")
        self.after(700, lambda: self.roll_cv.itemconfigure(self._ring_arc, outline=BORDER2) if self.roll_cv.winfo_exists() else None)
        self._refresh_top_bar(); self._refresh_roll_info()
        self._refresh_inventory(); self._refresh_collection(); self._refresh_stats()
        if self.engine.state.level > lvl_before:
            self._show_levelup(self.engine.state.level)
            self._refresh_rebirth()
        for a in achs:
            self._notify(f"🏆  {a['name']}", GOLD)
        self._auto_roll_post_roll(rarity)

    def _title_glow(self, color: str, step: int, max_step: int):
        if not self.roll_cv.winfo_exists():
            return
        if step > max_step:
            self.roll_cv.itemconfigure(self._cv_title, fill=color)
            return
        t = abs(math.sin(step * 0.55))
        g = blend_colors(color, "#ffffff", min(0.65, t))
        self.roll_cv.itemconfigure(self._cv_title, fill=g)
        self.after(70, lambda: self._title_glow(color, step + 1, max_step))

    def _start_mythic_glow(self):
        if self._mythic_glow_running:
            return
        self._mythic_glow_running = True
        self._mythic_glow_tick(0)

    def _mythic_glow_tick(self, i):
        if not self.roll_cv.winfo_exists():
            self._mythic_glow_running = False
            return
        if not self._mythic_glow_running or self._rolling:
            self._mythic_glow_running = False
            return
        c = MYTHIC_GRADIENT[i % len(MYTHIC_GRADIENT)]
        self.roll_cv.itemconfigure(self._cv_title, fill=c)
        self.roll_cv.itemconfigure(self._ring_arc, outline=c)
        if i > 20:
            self._mythic_glow_running = False
            return
        self.after(70, lambda: self._mythic_glow_tick(i + 1))

    def _screen_shake(self, intensity=6, step=0):
        if not self.roll_cv.winfo_exists():
            return
        if step > 10:
            self._draw_ring(self._ring_angle)
            return
        self._draw_ring((self._ring_angle + random.randint(-intensity * 3, intensity * 3)) % 360)
        self.after(22, lambda: self._screen_shake(max(1, intensity - 1), step + 1))

    def _rarity_odds_text(self, rarity: str) -> str:
        shift = self.engine._upg("drop_shift")
        base = max(1, RARITIES.get(rarity, {}).get("weight", 1))
        luck = max(0.5, self.engine.state.luck_multiplier + shift * 0.08)
        approx = max(1, int(10000 / (base * luck)))
        return f"1 / {approx:,} odds"

    def _pulse_border(self, color, step):
        if step > 10:
            try: self.roll_cv.configure(highlightthickness=0)
            except: pass
            return
        try:
            self.roll_cv.configure(highlightthickness=2 if step%2==0 else 0,
                                    highlightbackground=color)
        except: pass
        self.after(100, lambda: self._pulse_border(color, step+1))

    def _add_recent(self, title, rarity):
        c = rarity_ui_color(rarity)
        self._recent_rolls.insert(0, (title, rarity, c))
        if len(self._recent_rolls) > 20: self._recent_rolls.pop()
        for w in self.recent_inner.winfo_children(): w.destroy()
        for idx, (t, r, col) in enumerate(self._recent_rolls):
            chip = ctk.CTkFrame(self.recent_inner, fg_color=blend_colors(CARD, col, 0.08), corner_radius=20,
                                 border_width=1, border_color=blend_colors(col, CARD, 0.2))
            chip.pack(side="left", padx=(18 if idx == 0 else 3, 3), pady=2)
            lbl(chip, r, color=col, font=F_LABEL).pack(side="left", padx=(8,2), pady=4)
            lbl(chip, t, color=FG, font=F_LABEL).pack(side="left", padx=(0,8), pady=4)
        self.recent_cv.update_idletasks()
        self.recent_cv.configure(scrollregion=self.recent_cv.bbox("all"))
        self.recent_cv.xview_moveto(0.0)
        self._slide_recent_in(0)

    def _slide_recent_in(self, step: int):
        if not hasattr(self, "recent_inner"):
            return
        kids = self.recent_inner.winfo_children()
        if not kids:
            return
        newest = kids[0]
        pad = max(3, 18 - step * 3)
        try:
            newest.pack_configure(padx=(pad, 3))
        except Exception:
            return
        if step < 5:
            self.after(28, lambda: self._slide_recent_in(step + 1))

    def _activate_lucky(self):
        s = self.engine.state
        if s.lucky_rolls_remaining > 0:
            self._notify(f"Already active! ({s.lucky_rolls_remaining} left)", GOLD)
        elif s.lucky_rolls > 0:
            s.lucky_rolls_remaining = 10; s.lucky_rolls -= 1
            self.engine.save_game()
            self._notify("🌟  Lucky Roll active (10 rolls)!", GOLD)
            self._refresh_top_bar()
        else:
            self._notify("No Lucky Rolls! Buy from Shop.", RED)

    def _set_auto_target(self, target):
        self.engine.state.auto_roll_target = target
        self.engine.save_game()
        self._refresh_roll_info()

    def _toggle_auto_roll(self):
        if self.engine._upg("auto_roll") <= 0:
            self.auto_roll_switch.deselect()
            self._notify("Unlock Auto Roll in Rebirth upgrades first.", RED)
            return
        self.engine.state.auto_roll_enabled = bool(self.auto_roll_switch.get())
        self.engine.save_game()
        self._refresh_roll_info()
        if self.engine.state.auto_roll_enabled:
            self.after(120, self._auto_roll_tick)

    def _auto_roll_post_roll(self, rarity: str):
        if not self.engine.state.auto_roll_enabled:
            return
        target = self.engine.state.auto_roll_target or "Legendary"
        if RARITY_ORDER.index(rarity) >= RARITY_ORDER.index(target):
            self.engine.state.auto_roll_enabled = False
            self.engine.save_game()
            self.auto_roll_switch.deselect()
            self._notify(f"Auto-roll stopped at {rarity} (target {target}).", GREEN)
        self._refresh_roll_info()
        if self.engine.state.auto_roll_enabled:
            delay = max(80, int(360 / self.engine.get_roll_speed_multiplier()))
            self.after(delay, self._auto_roll_tick)

    def _auto_roll_tick(self):
        if not self.engine.state.auto_roll_enabled:
            return
        if self.tabs.get() != "🎲 Roll":
            self.engine.state.auto_roll_enabled = False
            self.engine.save_game()
            self.auto_roll_switch.deselect()
            self._notify("Auto-roll paused (left Roll tab).", FG2)
            self._refresh_roll_info()
            return
        if not self._rolling:
            self._do_roll()

    # ══════════════════════════════════════════════════════════════════════════
    #  INVENTORY TAB
    # ══════════════════════════════════════════════════════════════════════════
    def _build_inv_tab(self):
        tab = self.tabs.tab("🎒 Inventory"); tab.configure(fg_color=BG)
        hdr = ctk.CTkFrame(tab, fg_color="transparent"); hdr.pack(fill="x", padx=20, pady=(14,6))
        lbl(hdr, "Inventory", font=F_TITLE).pack(side="left")
        brow = ctk.CTkFrame(hdr, fg_color="transparent"); brow.pack(side="right")
        ghost_btn(brow,"Equip Best", self._equip_best, color=GREEN, w=110, h=36).pack(side="left", padx=4)
        pill_btn(brow, "Equip",   self._equip_sel,   fg="#1d4ed8", hover="#1e40af", w=100, h=36).pack(side="left", padx=4)
        pill_btn(brow, "Merge",   self._merge_sel,   fg="#6d28d9", hover="#5b21b6", w=100, h=36).pack(side="left", padx=4)
        ghost_btn(brow,"Discard", self._discard_sel,  color=RED,    w=90,  h=36).pack(side="left", padx=4)

        filters = ctk.CTkFrame(tab, fg_color="transparent"); filters.pack(fill="x", padx=20, pady=(0,6))
        self.inv_search = ctk.CTkEntry(filters, width=220, height=34, corner_radius=10,
                                       fg_color=CARD2, border_color=BORDER2, text_color=FG,
                                       placeholder_text="Search title...")
        self.inv_search.pack(side="left", padx=(0,8))
        self.inv_search.bind("<KeyRelease>", lambda e: self._refresh_inventory())
        self.inv_rarity_filter = ctk.CTkOptionMenu(
            filters, values=["All"] + RARITY_ORDER, width=150, height=34,
            fg_color=CARD2, button_color=ACCENT2, button_hover_color=ACCENT,
            command=lambda _: self._refresh_inventory())
        self.inv_rarity_filter.set("All")
        self.inv_rarity_filter.pack(side="left", padx=4)
        self.inv_sort_menu = ctk.CTkOptionMenu(
            filters, values=["Rarity ↓","Count ↓","Name A→Z"], width=140, height=34,
            fg_color=CARD2, button_color=ACCENT2, button_hover_color=ACCENT,
            command=lambda _: self._refresh_inventory())
        self.inv_sort_menu.set("Rarity ↓")
        self.inv_sort_menu.pack(side="left", padx=4)
        self.inv_meta_lbl = lbl(filters, "", color=FG2, font=F_LABEL); self.inv_meta_lbl.pack(side="right")

        eq_row = ctk.CTkFrame(tab, fg_color="transparent"); eq_row.pack(anchor="w", padx=22, pady=(0,8))
        lbl(eq_row, "EQUIPPED", font=F_LABEL, color=FG2).pack(side="left", padx=(0,8))
        self.eq_lbl = lbl(eq_row, "None", color=FG2, font=F_SMALL); self.eq_lbl.pack(side="left")

        self.inv_list = ctk.CTkScrollableFrame(tab, fg_color="transparent", corner_radius=0)
        self.inv_list.pack(fill="both", expand=True, padx=16, pady=(0,12))
        self._inv_sel: Optional[str] = None

    def _refresh_inventory(self):
        self.engine._sanitize_battle_titles()
        for w in self.inv_list.winfo_children(): w.destroy()
        items = self.engine.get_inventory_sorted()
        q = (self.inv_search.get().strip().lower() if hasattr(self, "inv_search") else "")
        rf = (self.inv_rarity_filter.get() if hasattr(self, "inv_rarity_filter") else "All")
        if q:
            items = [it for it in items if q in it[0].lower()]
        if rf != "All":
            items = [it for it in items if it[2] == rf]
        sort_mode = self.inv_sort_menu.get() if hasattr(self, "inv_sort_menu") else "Rarity ↓"
        if sort_mode == "Count ↓":
            items.sort(key=lambda x: (-x[1], -RARITY_ORDER.index(x[2]), x[0]))
        elif sort_mode == "Name A→Z":
            items.sort(key=lambda x: x[0].lower())
        total_copies = sum(c for _, c, _ in self.engine.get_inventory_sorted())
        unique = len(self.engine.state.inventory)
        if hasattr(self, "inv_meta_lbl"):
            self.inv_meta_lbl.configure(text=f"{unique} unique · {total_copies} total")
        if not items:
            lbl(self.inv_list, "No titles yet — go roll!", color=FG2).pack(pady=40); return
        grid = ctk.CTkFrame(self.inv_list, fg_color="transparent")
        grid.pack(fill="both", expand=True, padx=2, pady=4)
        cols = 3
        for i in range(cols):
            grid.grid_columnconfigure(i, weight=1, uniform="invcol")
        total_w = sum(v["weight"] for v in RARITIES.values())
        for i, (title, count, rarity) in enumerate(items):
            r = i // cols
            cidx = i % cols
            chance = max(1, int(total_w / max(1, RARITIES[rarity]["weight"])))
            chance_txt = f"Drop chance ~ 1/{chance}"
            def click(t=title):
                self._inv_sel = t
                self._refresh_inventory()
            card = LootCard(grid, title, rarity, count, chance_txt, click)
            sel = (self._inv_sel == title)
            if sel:
                card.configure(border_width=2, border_color=rarity_ui_color(rarity))
            card.grid(row=r, column=cidx, sticky="ew", padx=6, pady=6)
            tags = ctk.CTkFrame(card, fg_color="transparent")
            tags.place(relx=1.0, x=-8, y=8, anchor="ne")
            if self.engine.state.equipped_title == title:
                chip = ctk.CTkFrame(tags, fg_color=GOLD, corner_radius=10)
                chip.pack(side="right", padx=(4, 0))
                lbl(chip, "EQ", font=F_LABEL, color="#000").pack(padx=6, pady=1)
            if title in (self.engine.state.battle_titles or []):
                chip2 = ctk.CTkFrame(tags, fg_color=PURPLE, corner_radius=10)
                chip2.pack(side="right", padx=(4, 0))
                lbl(chip2, "PVP", font=F_LABEL, color="#fff").pack(padx=6, pady=1)
        eq = self.engine.state.equipped_title; er = self.engine.state.equipped_rarity
        if eq and er:
            self.eq_lbl.configure(text=f"{eq}  [{er}]", text_color=RARITIES[er]["color"])
        else:
            self.eq_lbl.configure(text="None", text_color=FG2)

    def _equip_best(self):
        best = get_best_titles(self.engine.state, 1)
        if not best:
            self._notify("No titles to equip yet.", RED); return
        self._inv_sel = best[0]
        self._equip_sel()

    def _equip_sel(self):
        if not self._inv_sel: self._notify("Select a title first!", RED); return
        if self.engine.equip_title(self._inv_sel):
            self._notify(f"Equipped: {self._inv_sel}!", GREEN)
            self._refresh_inventory(); self._refresh_arena(); self._refresh_boss()
        else: self._notify("Could not equip.", RED)

    def _merge_sel(self):
        if not self._inv_sel: self._notify("Select a title to merge!", RED); return
        if not self.engine.is_unlocked("merge"):
            self._notify(f"Merge unlocks at level {UNLOCKS['merge']}!", RED); return
        ok, reason = self.engine.can_merge(self._inv_sel)
        if not ok: self._notify(reason, RED); return
        t, r, achs = self.engine.perform_merge(self._inv_sel)
        if t:
            self._notify(f"Merged → {t} [{r}]", RARITIES[r]["color"]); self._inv_sel = None
            self._refresh_inventory(); self._refresh_top_bar()
            self._refresh_arena(); self._refresh_boss()
            for a in achs: self._notify(f"🏆 {a['name']}", GOLD)
        else: self._notify(f"Merge failed: {r}", RED)

    def _discard_sel(self):
        if not self._inv_sel: self._notify("Select a title!", RED); return
        s = self.engine.state
        if self._inv_sel not in s.inventory: self._notify("Not in inventory.", RED); return
        s.inventory[self._inv_sel] -= 1
        if s.inventory[self._inv_sel] <= 0:
            del s.inventory[self._inv_sel]
            if s.equipped_title == self._inv_sel: s.equipped_title = s.equipped_rarity = None
            self._inv_sel = None
        self.engine.save_game(); self._notify("Discarded 1 title.", FG2)
        self._refresh_inventory(); self._refresh_top_bar()
        self._refresh_arena(); self._refresh_boss()

    # ══════════════════════════════════════════════════════════════════════════
    #  ARENA TAB
    # ══════════════════════════════════════════════════════════════════════════
    def _build_arena_tab(self):
        tab = self.tabs.tab("⚔️ Arena"); tab.configure(fg_color=BG)
        self.arena_lock_lbl = lbl(tab, "", color=RED, font=F_SMALL)
        self.arena_lock_lbl.pack(pady=4)
        lbl(tab, "Arena", font=F_TITLE).pack(pady=(4,2))
        lbl(tab, "Battle NPC opponents for coins, shards & XP. Cooldowns apply.",
            font=F_LABEL, color=FG2).pack()
        self.arena_eq_lbl = lbl(tab, "", color=FG2, font=F_SMALL); self.arena_eq_lbl.pack(pady=4)

        scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=16, pady=8)
        self._arena_fight_btns = []; self._arena_cd_lbls = []
        self._arena_res_lbls = []; self._arena_cv_list = []

        # 2 cards per row
        for i, opp in enumerate(ARENA_OPPONENTS):
            if i % 2 == 0:
                row_frame = ctk.CTkFrame(scroll, fg_color="transparent")
                row_frame.pack(fill="x", pady=4)
            c = card_frame(row_frame, width=420, height=180)
            c.pack(side="left", padx=8); c.pack_propagate(False)

            top_row = ctk.CTkFrame(c, fg_color="transparent"); top_row.pack(fill="x", padx=14, pady=(12,4))
            lbl(top_row, f"{opp['emoji']}  {opp['name']}", font=F_HEAD).pack(side="left")
            lbl(top_row, f"Power {opp['power']}", color=RED, font=F_SMALL).pack(side="right")

            rew = ctk.CTkFrame(c, fg_color="transparent"); rew.pack(anchor="w", padx=14)
            lbl(rew, f"🪙 {opp['coins']}", color=GOLD, font=F_LABEL).pack(side="left", padx=(0,8))
            lbl(rew, f"💎 {opp['shards']}", color=BLUE, font=F_LABEL).pack(side="left", padx=(0,8))
            lbl(rew, f"✨ {opp['xp']}xp", color=GREEN, font=F_LABEL).pack(side="left")

            cv = tk.Canvas(c, width=380, height=20, bg=CARD, highlightthickness=0)
            cv.pack(pady=4); self._arena_cv_list.append(cv)
            self._draw_arena_bars(cv, 1.0, 1.0)

            bottom = ctk.CTkFrame(c, fg_color="transparent"); bottom.pack(fill="x", padx=14)
            cd_lbl = lbl(bottom, "✅ Ready", color=GREEN, font=F_LABEL)
            cd_lbl.pack(side="left"); self._arena_cd_lbls.append(cd_lbl)
            res_lbl = lbl(bottom, "", color=FG, font=F_LABEL)
            res_lbl.pack(side="left", padx=8); self._arena_res_lbls.append(res_lbl)
            fb = pill_btn(bottom, "Fight", lambda idx=i: self._do_arena(idx),
                          fg="#7f1d1d", hover="#991b1b", w=100, h=32)
            fb.pack(side="right"); self._arena_fight_btns.append(fb)

    def _draw_arena_bars(self, cv, pf, ef, pc=BLUE, ec=RED):
        cv.delete("all")
        W, H = 380, 20; mid = W // 2
        pw = int((mid - 6) * pf); ew = int((mid - 6) * ef)
        cv.create_rectangle(2, 3, mid-4, H-3, fill=CARD2, outline="")
        if pw > 0: cv.create_rectangle(2, 3, 2+pw, H-3, fill=pc, outline="")
        cv.create_text(mid//2, H//2, text="YOU", fill=FG2, font=(_MONO, 7))
        cv.create_rectangle(mid+4, 3, W-2, H-3, fill=CARD2, outline="")
        if ew > 0: cv.create_rectangle(W-2-ew, 3, W-2, H-3, fill=ec, outline="")
        cv.create_text(mid + (W-mid)//2, H//2, text="FOE", fill=FG2, font=(_MONO, 7))
        cv.create_line(mid, 1, mid, H-1, fill=BORDER2, width=1)

    def _do_arena(self, idx):
        if not self.engine.is_unlocked("arena"):
            self._notify(f"Arena unlocks at level {UNLOCKS['arena']}!", RED); return
        opp = ARENA_OPPONENTS[idx]
        rem = self.engine.cooldown_remaining(f"arena_{idx}", opp["cooldown"])
        if rem > 0: self._notify(f"⏳ {fmt_cd(rem)}", RED); return
        self._arena_fight_btns[idx].configure(state="disabled")
        self._arena_res_lbls[idx].configure(text="")
        self._battle_anim_arena(idx, opp, 1.0, 0)

    def _battle_anim_arena(self, idx, opp, ehp, step):
        new_hp = max(0.0, ehp - random.uniform(0.12, 0.22))
        pf = 0.8 + 0.2 * math.sin(step * 0.5)
        self._draw_arena_bars(self._arena_cv_list[idx], min(1.0, pf), new_hp, GREEN, RED)
        frames = ["⚔️ Fighting…","💥 Clash!","🗡 Strike!","💫 Impact!","🔥 Final blow!"]
        if step < len(frames):
            self._arena_res_lbls[idx].configure(text=frames[step], text_color=FG)
        if new_hp > 0 and step < 12:
            self.after(160, lambda: self._battle_anim_arena(idx, opp, new_hp, step+1))
        else:
            self._resolve_arena(idx)

    def _resolve_arena(self, idx):
        win, name, achs = self.engine.perform_arena_battle(idx)
        opp = ARENA_OPPONENTS[idx]
        if win:
            self._draw_arena_bars(self._arena_cv_list[idx], 1.0, 0.0, GREEN, RED)
            self._arena_res_lbls[idx].configure(text=f"✅ +{opp['coins']}🪙", text_color=GREEN)
            self._notify(f"⚔️ Beat {name}!", GREEN)
        else:
            self._draw_arena_bars(self._arena_cv_list[idx], 0.2, 1.0, RED, RED)
            self._arena_res_lbls[idx].configure(text="❌ Defeated", text_color=RED)
        self._arena_fight_btns[idx].configure(state="normal")
        self._refresh_top_bar(); self._refresh_arena()
        for a in (achs or []): self._notify(f"🏆 {a['name']}", GOLD)

    def _refresh_arena(self):
        u = self.engine.is_unlocked("arena")
        self.arena_lock_lbl.configure(text="" if u else f"🔒 Arena unlocks at Level {UNLOCKS['arena']}")
        power = self.engine.get_equipped_power(); eq = self.engine.state.equipped_title or "None"
        er = self.engine.state.equipped_rarity or ""
        col = RARITIES[er]["color"] if er in RARITIES else FG2
        self.arena_eq_lbl.configure(text=f"Equipped: {eq}  [{er}]  ·  Power: {power}", text_color=col)

    def _refresh_arena_cds(self):
        if not hasattr(self, "_arena_cd_lbls"): return
        for i, opp in enumerate(ARENA_OPPONENTS):
            cd = self.engine.cooldown_remaining(f"arena_{i}", opp["cooldown"])
            if cd > 0: self._arena_cd_lbls[i].configure(text=f"⏳ {fmt_cd(cd)}", text_color=RED)
            else: self._arena_cd_lbls[i].configure(text="✅ Ready", text_color=GREEN)

    # ══════════════════════════════════════════════════════════════════════════
    #  BOSS TAB
    # ══════════════════════════════════════════════════════════════════════════
    def _build_boss_tab(self):
        tab = self.tabs.tab("💀 Boss"); tab.configure(fg_color=BG)
        self.boss_lock_lbl = lbl(tab, "", color=RED, font=F_SMALL); self.boss_lock_lbl.pack(pady=4)
        lbl(tab, "Boss Battles", font=F_TITLE).pack(pady=(4,2))
        lbl(tab, "Progressive bosses with long cooldowns. Each drops guaranteed high-rarity titles.",
            font=F_LABEL, color=FG2).pack()
        self.boss_token_lbl = lbl(tab, "", color=RED, font=F_SMALL); self.boss_token_lbl.pack(pady=2)
        self.boss_anim_lbl  = lbl(tab, "", font=(_FONT, 16, "bold"), color=FG); self.boss_anim_lbl.pack()
        self.boss_scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        self.boss_scroll.pack(fill="both", expand=True, padx=18, pady=8)
        self._boss_btns={}; self._boss_cd_lbls={}; self._boss_res_lbls={}
        self._boss_hp_bars={}; self._boss_anim_lbls={}; self._boss_cvs={}

    def _refresh_boss(self):
        u = self.engine.is_unlocked("boss")
        self.boss_lock_lbl.configure(text="" if u else f"🔒 Boss unlocks at Level {UNLOCKS['boss']}")
        self.boss_token_lbl.configure(text=f"Boss Tokens: {self.engine.state.boss_tokens} 🔑")
        for w in self.boss_scroll.winfo_children(): w.destroy()
        self._boss_btns.clear(); self._boss_cd_lbls.clear(); self._boss_res_lbls.clear()
        self._boss_hp_bars.clear(); self._boss_anim_lbls.clear(); self._boss_cvs.clear()
        s = self.engine.state
        for boss in BOSSES:
            lv_ok  = s.level >= boss["req_level"]
            rar_ok = RARITY_ORDER.index(s.highest_rarity_pulled) >= RARITY_ORDER.index(boss["req_rarity"])
            avail  = lv_ok and rar_ok and u
            col    = boss["color"]
            c = ctk.CTkFrame(self.boss_scroll,
                             fg_color=CARD if avail else SURFACE, corner_radius=16,
                             border_width=1, border_color=col if avail else BORDER)
            c.pack(fill="x", pady=8, padx=4)
            row = ctk.CTkFrame(c, fg_color="transparent"); row.pack(fill="x", padx=16, pady=14)

            # Portrait canvas
            pcv = tk.Canvas(row, width=72, height=72, bg=CARD if avail else SURFACE, highlightthickness=0)
            pcv.pack(side="left", padx=(0,16))
            self._draw_boss_portrait(pcv, boss, avail); self._boss_cvs[boss["id"]] = pcv

            info = ctk.CTkFrame(row, fg_color="transparent"); info.pack(side="left", fill="both", expand=True)
            lbl(info, boss["name"], font=F_HEAD, color=col if avail else FG2).pack(anchor="w")
            lbl(info, boss["desc"], font=F_LABEL, color=FG2).pack(anchor="w", pady=2)
            req = ctk.CTkFrame(info, fg_color="transparent"); req.pack(anchor="w", pady=2)
            lbl(req, f"Lv.{boss['req_level']}+", color=GREEN if lv_ok else RED, font=F_LABEL).pack(side="left", padx=(0,8))
            lbl(req, f"{boss['req_rarity']}+",    color=GREEN if rar_ok else RED,font=F_LABEL).pack(side="left", padx=(0,8))
            lbl(req, f"Power: {boss['power']}",   color=FG2,                    font=F_LABEL).pack(side="left")
            rew = ctk.CTkFrame(info, fg_color="transparent"); rew.pack(anchor="w", pady=2)
            lbl(rew, f"🪙 {boss['coins']}", color=GOLD, font=F_LABEL).pack(side="left", padx=(0,8))
            lbl(rew, f"💎 {boss['shards']}", color=BLUE, font=F_LABEL).pack(side="left", padx=(0,8))
            lbl(rew, f"Guarantee: {boss['guarantee']}+",
                color=RARITIES[boss["guarantee"]]["color"], font=F_LABEL).pack(side="left")

            right = ctk.CTkFrame(row, fg_color="transparent", width=210); right.pack(side="right"); right.pack_propagate(False)
            lbl(right, f"🔑 ×{boss['token_cost']}", color=RED if avail else FG2, font=F_LABEL).pack(pady=(0,4))
            hp = ctk.CTkProgressBar(right, width=190, height=10, corner_radius=5,
                                     fg_color=CARD2, progress_color=col)
            hp.pack(pady=4); hp.set(1.0 if avail else 0.2); self._boss_hp_bars[boss["id"]] = hp
            al = lbl(right, "", color=col, font=(_FONT, 11, "bold")); al.pack(); self._boss_anim_lbls[boss["id"]] = al
            cd = self.engine.cooldown_remaining(f"boss_{boss['id']}", boss["cooldown"])
            cd_t = f"⏳ {fmt_cd(cd)}" if cd > 0 else ("✅ Ready" if avail else "🔒 Locked")
            cd_c = RED if cd > 0 else (GREEN if avail else FG2)
            cl = lbl(right, cd_t, color=cd_c, font=F_LABEL); cl.pack(pady=2); self._boss_cd_lbls[boss["id"]] = cl
            rl = lbl(right, "", color=FG, font=F_LABEL); rl.pack(); self._boss_res_lbls[boss["id"]] = rl
            fb = pill_btn(right, "💀  Fight", lambda bid=boss["id"]: self._do_boss(bid),
                          fg=col if avail else FG2,
                          hover=blend_colors(col,"#000000",0.3) if avail else FG2, w=185, h=38)
            fb.configure(state="normal" if avail else "disabled")
            fb.pack(pady=6); self._boss_btns[boss["id"]] = fb

    def _draw_boss_portrait(self, cv, boss, avail):
        col = boss["color"] if avail else "#333344"
        dim = "#1a1a2e" if avail else "#0f0f1a"
        cv.delete("all")
        cv.create_oval(4,4,68,68, outline=col, width=2, fill=dim)
        cv.create_text(36,36, text=boss["emoji"], font=(_FONT,22), fill=col)
        for ang in range(0,360,90):
            x = 36+30*math.cos(math.radians(ang)); y = 36+30*math.sin(math.radians(ang))
            cv.create_oval(x-3,y-3,x+3,y+3, fill=col, outline="")

    def _do_boss(self, boss_id):
        boss = next(b for b in BOSSES if b["id"] == boss_id)
        s = self.engine.state
        if not self.engine.is_unlocked("boss"): self._notify(f"Boss unlocks at {UNLOCKS['boss']}!", RED); return
        if s.level < boss["req_level"]: self._notify(f"Need level {boss['req_level']}!", RED); return
        if RARITY_ORDER.index(s.highest_rarity_pulled) < RARITY_ORDER.index(boss["req_rarity"]):
            self._notify(f"Need {boss['req_rarity']}+ pulled!", RED); return
        rem = self.engine.cooldown_remaining(f"boss_{boss_id}", boss["cooldown"])
        if rem > 0: self._notify(f"Boss cooldown: {fmt_cd(rem)}", RED); return
        if s.boss_tokens < boss["token_cost"]: self._notify(f"Need {boss['token_cost']} Boss Tokens!", RED); return
        if boss_id in self._boss_fighting: return
        self._boss_fighting.add(boss_id)
        if boss_id in self._boss_btns: self._boss_btns[boss_id].configure(state="disabled")
        if boss_id in self._boss_hp_bars: self._boss_hp_bars[boss_id].set(1.0)
        if boss_id in self._boss_res_lbls: self._boss_res_lbls[boss_id].configure(text="")
        self._boss_drain(boss_id, boss, 1.0)

    def _boss_drain(self, boss_id, boss, hp):
        new_hp = max(0.0, hp - random.uniform(0.07, 0.15))
        if boss_id in self._boss_hp_bars: self._boss_hp_bars[boss_id].set(new_hp)
        atk = ["💥 Strike!","⚡ Surge!","🗡 Slash!","🌀 Vortex!","❄️ Frost!","🔥 Inferno!","☠️ Deathblow!"]
        if boss_id in self._boss_anim_lbls: self._boss_anim_lbls[boss_id].configure(text=random.choice(atk))
        if new_hp > 0: self.after(140, lambda: self._boss_drain(boss_id, boss, new_hp))
        else:
            if boss_id in self._boss_anim_lbls: self._boss_anim_lbls[boss_id].configure(text="")
            self._resolve_boss(boss_id, boss)

    def _resolve_boss(self, boss_id, boss):
        win, name, title, rarity, achs = self.engine.perform_boss_battle(boss_id)
        col = boss["color"]
        if not win:
            if boss_id in self._boss_res_lbls: self._boss_res_lbls[boss_id].configure(text="❌ Defeated", text_color=RED)
            if boss_id in self._boss_hp_bars: self._boss_hp_bars[boss_id].set(1.0)
            self._notify(f"❌ Defeated by {name}!", RED)
        else:
            rc = RARITIES[rarity]["color"] if rarity else GREEN
            if boss_id in self._boss_res_lbls: self._boss_res_lbls[boss_id].configure(text=f"✅ Slain!  {title}", text_color=GREEN)
            if boss_id in self._boss_hp_bars: self._boss_hp_bars[boss_id].set(0.0)
            if boss_id in self._boss_cvs: self._spawn_particles(self._boss_cvs[boss_id], 36, 36, rc, n=25)
            self._big_notify(f"💀 {name.upper()} SLAIN!\n{title}  [{rarity}]", rc)
        self._boss_fighting.discard(boss_id)
        if boss_id in self._boss_btns: self._boss_btns[boss_id].configure(state="normal")
        self._refresh_top_bar(); self._refresh_boss()
        self._refresh_inventory(); self._refresh_collection(); self._refresh_stats()
        for a in (achs or []): self._notify(f"🏆 {a['name']}", GOLD)

    def _refresh_boss_cds(self):
        if not hasattr(self, "_boss_cd_lbls"): return
        s = self.engine.state
        for boss in BOSSES:
            bid = boss["id"]
            if bid not in self._boss_cd_lbls: continue
            lv_ok  = s.level >= boss["req_level"]
            rar_ok = RARITY_ORDER.index(s.highest_rarity_pulled) >= RARITY_ORDER.index(boss["req_rarity"])
            avail  = lv_ok and rar_ok and self.engine.is_unlocked("boss")
            if not avail: continue
            cd = self.engine.cooldown_remaining(f"boss_{bid}", boss["cooldown"])
            if cd > 0:
                self._boss_cd_lbls[bid].configure(text=f"⏳ {fmt_cd(cd)}", text_color=RED)
                if bid in self._boss_btns and bid not in self._boss_fighting:
                    self._boss_btns[bid].configure(state="disabled")
            else:
                self._boss_cd_lbls[bid].configure(text="✅ Ready", text_color=GREEN)
                if bid in self._boss_btns and bid not in self._boss_fighting:
                    self._boss_btns[bid].configure(state="normal")

    # ══════════════════════════════════════════════════════════════════════════
    #  SHOP TAB
    # ══════════════════════════════════════════════════════════════════════════
    def _build_shop_tab(self):
        tab = self.tabs.tab("🛒 Shop"); tab.configure(fg_color=BG)
        lbl(tab, "Shop", font=F_TITLE).pack(pady=(16,4))
        dc = card_frame(tab); dc.pack(fill="x", padx=20, pady=8)
        dr = ctk.CTkFrame(dc, fg_color="transparent"); dr.pack(fill="x", padx=16, pady=12)
        lbl(dr, "🎁", font=(_FONT,24)).pack(side="left", padx=(0,12))
        dl = ctk.CTkFrame(dr, fg_color="transparent"); dl.pack(side="left", fill="x", expand=True)
        lbl(dl, "Daily Reward", font=F_HEAD).pack(anchor="w")
        lbl(dl, "Coins, shards & Lucky Roll — free every 24h", color=FG2, font=F_LABEL).pack(anchor="w")
        pill_btn(dr, "Claim", self._claim_daily, fg="#166534", hover="#14532d", w=100, h=36).pack(side="right")
        grid = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        grid.pack(fill="both", expand=True, padx=18, pady=8)
        for i in range(0, len(SHOP_ITEMS), 2):
            rf = ctk.CTkFrame(grid, fg_color="transparent"); rf.pack(fill="x", pady=5)
            for j in range(2):
                if i+j >= len(SHOP_ITEMS): break
                item = SHOP_ITEMS[i+j]
                c = card_frame(rf, width=380, height=110); c.pack(side="left", padx=8); c.pack_propagate(False)
                tr = ctk.CTkFrame(c, fg_color="transparent"); tr.pack(fill="x", padx=14, pady=(12,4))
                lbl(tr, f"{item['emoji']}  {item['name']}", font=F_HEAD).pack(side="left")
                pp = ctk.CTkFrame(tr, fg_color=CARD2, corner_radius=12); pp.pack(side="right")
                lbl(pp, f"🪙 {item['cost']}", color=GOLD, font=F_SMALL).pack(padx=10, pady=4)
                lbl(c, item["desc"], color=FG2, font=F_LABEL).pack(anchor="w", padx=14)
                pill_btn(c, "Buy", lambda iid=item["id"]: self._do_buy(iid),
                         fg="#1e3a5f", hover="#1e40af", w=90, h=30).pack(anchor="e", padx=14, pady=6)

    def _do_buy(self, iid):
        ok, msg = self.engine.perform_purchase(iid)
        self._notify(msg, GREEN if ok else RED)
        self._refresh_top_bar(); self._refresh_craft(); self._refresh_boss()

    def _claim_daily(self):
        ok, result = self.engine.claim_daily()
        if ok:
            c, s, l = result
            self._notify(f"🎁 Daily!  +{c}🪙  +{s}💎  +{l} Lucky Roll", GREEN)
            self._refresh_top_bar(); self._refresh_craft()
        else: self._notify(result, FG2)

    # ══════════════════════════════════════════════════════════════════════════
    #  CRAFT TAB
    # ══════════════════════════════════════════════════════════════════════════
    def _build_craft_tab(self):
        tab = self.tabs.tab("⚗️ Craft"); tab.configure(fg_color=BG)
        self.craft_lock_lbl = lbl(tab, "", color=RED, font=F_SMALL); self.craft_lock_lbl.pack(pady=4)
        lbl(tab, "Crafting", font=F_TITLE).pack(pady=(4,2))
        self.craft_shard_lbl = lbl(tab, "", color=BLUE, font=F_SMALL); self.craft_shard_lbl.pack()
        grid = ctk.CTkFrame(tab, fg_color="transparent"); grid.pack(pady=20)
        self.craft_result_lbl = lbl(tab, "", font=F_HEAD, color=FG); self.craft_result_lbl.pack(pady=8)
        for i, recipe in enumerate(CRAFT_RECIPES):
            c = card_frame(grid, width=250, height=200); c.grid(row=0, column=i, padx=10, pady=6); c.pack_propagate(False)
            lbl(c, recipe["emoji"], font=(_FONT,28)).pack(pady=(16,4))
            lbl(c, recipe["name"], font=F_HEAD).pack()
            lbl(c, recipe["desc"], color=FG2, font=F_LABEL).pack(pady=4)
            sp = ctk.CTkFrame(c, fg_color=CARD2, corner_radius=14); sp.pack(pady=4)
            lbl(sp, f"💎 {recipe['cost_shards']}", color=BLUE, font=F_SMALL).pack(padx=12, pady=5)
            pill_btn(c, "Craft", lambda rid=recipe["id"]: self._do_craft(rid),
                     fg="#0c4a6e", hover="#075985", w=150, h=34).pack(pady=6)

    def _do_craft(self, rid):
        if not self.engine.is_unlocked("craft"):
            self._notify(f"Craft unlocks at level {UNLOCKS['craft']}!", RED); return
        t, r, achs = self.engine.perform_craft(rid)
        if t:
            c = RARITIES[r]["color"]
            self.craft_result_lbl.configure(text=f"Crafted: {t}  [{r}]", text_color=c)
            if RARITY_ORDER.index(r) >= RARITY_ORDER.index("Legendary"):
                self._big_notify(f"⚗️ CRAFTED!\n{t}  [{r}]", c)
        else:
            self.craft_result_lbl.configure(text=str(r), text_color=RED)
            self._notify(str(r), RED)
        self._refresh_top_bar(); self._refresh_craft()
        self._refresh_inventory(); self._refresh_collection(); self._refresh_stats()
        for a in (achs or []): self._notify(f"🏆 {a['name']}", GOLD)

    def _refresh_craft(self):
        self.craft_lock_lbl.configure(
            text="" if self.engine.is_unlocked("craft") else f"🔒 Craft unlocks at Level {UNLOCKS['craft']}")
        self.craft_shard_lbl.configure(text=f"Your Shards: {self.engine.state.shards} 💎")

    # ══════════════════════════════════════════════════════════════════════════
    #  COLLECTION TAB
    # ══════════════════════════════════════════════════════════════════════════
    def _build_collection_tab(self):
        tab = self.tabs.tab("📖 Collection"); tab.configure(fg_color=BG)
        lbl(tab, "Collection", font=F_TITLE).pack(pady=(16,4))
        self.coll_prog_lbl = lbl(tab, "", color=GREEN, font=F_SMALL); self.coll_prog_lbl.pack()
        self.coll_pbar = ctk.CTkProgressBar(tab, width=520, height=6, corner_radius=3,
                                             fg_color=CARD2, progress_color=GREEN)
        self.coll_pbar.pack(pady=6); self.coll_pbar.set(0)
        self.coll_scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        self.coll_scroll.pack(fill="both", expand=True, padx=18, pady=8)

    def _refresh_collection(self):
        for w in self.coll_scroll.winfo_children(): w.destroy()
        unique, total = self.engine.get_collection_count()
        pct = unique / total if total else 0
        self.coll_prog_lbl.configure(text=f"{unique} of {total} titles  ({int(pct*100)}%)")
        self.coll_pbar.set(pct)
        for rarity in RARITY_ORDER:
            col = RARITIES[rarity]["color"]
            cnt = sum(1 for t in TITLES[rarity] if t in self.engine.state.collection)
            hdr = ctk.CTkFrame(self.coll_scroll, fg_color=CARD, corner_radius=10, border_width=1, border_color=BORDER)
            hdr.pack(fill="x", pady=(10,3), padx=4)
            hr = ctk.CTkFrame(hdr, fg_color="transparent"); hr.pack(fill="x", padx=12, pady=6)
            dot = ctk.CTkFrame(hr, fg_color=col, width=8, height=8, corner_radius=4)
            dot.pack(side="left", padx=(0,8))
            lbl(hr, rarity, color=col, font=F_HEAD).pack(side="left")
            lbl(hr, f"{cnt}/{len(TITLES[rarity])}", color=FG2, font=F_SMALL).pack(side="right")
            row = ctk.CTkFrame(self.coll_scroll, fg_color="transparent"); row.pack(fill="x", padx=8, pady=3)
            for title in TITLES[rarity]:
                got = title in self.engine.state.collection
                cf = ctk.CTkFrame(row, fg_color=CARD2 if got else SURFACE, corner_radius=10,
                                   width=188, height=52, border_width=1,
                                   border_color=col if got else BORDER)
                cf.pack(side="left", padx=4, pady=3); cf.pack_propagate(False)
                ctk.CTkLabel(cf, text=("✦ " if got else "?")+( title if got else "???"),
                             font=F_LABEL, text_color=col if got else "#2a2a3a").place(
                    relx=0.5, rely=0.5, anchor="center")

    # ══════════════════════════════════════════════════════════════════════════
    #  ONLINE TAB
    # ══════════════════════════════════════════════════════════════════════════
    def _build_online_tab(self):
        tab = self.tabs.tab("🌍 Online"); tab.configure(fg_color=BG)
        hdr = ctk.CTkFrame(tab, fg_color="transparent"); hdr.pack(fill="x", padx=20, pady=(14,6))
        lbl(hdr, "Online Players", font=F_TITLE).pack(side="left")
        ghost_btn(hdr, "↻ Refresh", self._refresh_online, w=110, h=34).pack(side="right")

        self.online_scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent", width=500)
        self.online_scroll.pack(side="left", fill="both", expand=True, padx=(16,8), pady=8)

        lbl(tab, "Global Feed  (Epic+)", font=F_HEAD, color=FG2).pack(anchor="w", padx=12, pady=(14,4))
        self.feed_scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent", width=340)
        self.feed_scroll.pack(side="right", fill="both", expand=True, padx=(8,16), pady=8)

        self._cached_online = []; self._cached_feed = []

    def _refresh_online(self):
        def _bg():
            try:
                self._cached_online = self.db.get_online_players()
                self._cached_feed   = self.db.get_recent_rolls()
            except: pass
            self._ui_after(0, self._render_online)
        threading.Thread(target=_bg, daemon=True).start()

    def _render_online(self):
        for w in self.online_scroll.winfo_children(): w.destroy()
        rows = getattr(self, "_cached_online", [])
        if not rows:
            lbl(self.online_scroll, "No players online right now.", color=FG2).pack(pady=20); 
        else:
            for r in rows:
                un = r["username"]; rar = r.get("rarity","Common") or "Common"
                lvl = r.get("level","?"); eq  = r.get("equipped_title","")
                col = RARITIES.get(rar, {}).get("color", FG2)
                c = card_frame(self.online_scroll); c.pack(fill="x", pady=3, padx=4)
                cr = ctk.CTkFrame(c, fg_color="transparent"); cr.pack(fill="x", padx=14, pady=10)
                # Online dot
                dot = ctk.CTkFrame(cr, fg_color=GREEN, width=8, height=8, corner_radius=4)
                dot.pack(side="left", padx=(0,8))
                lbl(cr, un, font=F_HEAD).pack(side="left")
                lbl(cr, f"Lv.{lvl}", color=FG2, font=F_LABEL).pack(side="left", padx=8)
                lbl(cr, rar, color=col, font=F_LABEL).pack(side="left")
                if eq: lbl(cr, eq, color=FG2, font=F_LABEL).pack(side="left", padx=8)
                pill_btn(cr, "View", lambda u=un: self._open_player_profile(u),
                         fg=CARD2, hover=CARD, w=70, h=28).pack(side="right")

        # Feed
        for w in self.feed_scroll.winfo_children(): w.destroy()
        feed = getattr(self, "_cached_feed", [])
        if not feed:
            lbl(self.feed_scroll, "No recent pulls.", color=FG2).pack(pady=20)
        else:
            for r in feed:
                un = r["username"]; title = r["title"]; rar = r["rarity"]
                col = RARITIES.get(rar,{}).get("color", FG2)
                ts  = r.get("rolled_at","")
                c = ctk.CTkFrame(self.feed_scroll, fg_color=CARD, corner_radius=10, border_width=1, border_color=BORDER)
                c.pack(fill="x", pady=2, padx=4)
                cr = ctk.CTkFrame(c, fg_color="transparent"); cr.pack(fill="x", padx=10, pady=6)
                lbl(cr, un, color=FG2, font=F_LABEL, width=80, anchor="w").pack(side="left")
                lbl(cr, title, color=col, font=F_SMALL).pack(side="left", padx=4)
                lbl(cr, rar, color=col, font=F_LABEL).pack(side="right")

    # ══════════════════════════════════════════════════════════════════════════
    #  LEADERBOARD TAB
    # ══════════════════════════════════════════════════════════════════════════
    def _build_leaderboard_tab(self):
        tab = self.tabs.tab("🏆 Leaderboard"); tab.configure(fg_color=BG)
        hdr = ctk.CTkFrame(tab, fg_color="transparent"); hdr.pack(fill="x", padx=20, pady=(14,6))
        lbl(hdr, "Leaderboard", font=F_TITLE).pack(side="left")
        ghost_btn(hdr, "↻ Refresh", self._refresh_leaderboard, w=110, h=34).pack(side="right")

        # Column headers
        cols = ctk.CTkFrame(tab, fg_color=CARD2, corner_radius=8)
        cols.pack(fill="x", padx=20, pady=(0,4))
        cr = ctk.CTkFrame(cols, fg_color="transparent"); cr.pack(fill="x", padx=14, pady=6)
        for txt, w in [("#",40),("Player",150),("Highest Rarity",140),
                       ("Rolls",80),("Level",60),("Rebirth",70),("PvP",50),("Boss",50),("Rift",50),("Score",95)]:
            lbl(cr, txt, color=FG2, font=F_LABEL, width=w, anchor="w").pack(side="left", padx=4)

        self.lb_scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        self.lb_scroll.pack(fill="both", expand=True, padx=20, pady=8)

    def _refresh_leaderboard(self):
        def _bg():
            rows = self.db.get_leaderboard()
            self._ui_after(0, lambda: self._render_leaderboard(rows))
        threading.Thread(target=_bg, daemon=True).start()

    def _render_leaderboard(self, rows):
        for w in self.lb_scroll.winfo_children(): w.destroy()
        if not rows:
            lbl(self.lb_scroll, "No players yet.", color=FG2).pack(pady=20); return
        for i, r in enumerate(rows):
            un    = r["username"]; rar  = r.get("rarity","Common") or "Common"
            rolls = r.get("rolls",0) or 0; lvl  = r.get("level",1) or 1
            reb   = r.get("rebirths",0) or 0
            pvpw  = r.get("pvp_wins",0) or 0; bw   = r.get("boss_wins",0) or 0
            rw    = r.get("rift_wins",0) or 0
            score = r.get("score",0) or 0
            col   = RARITIES.get(rar,{}).get("color", FG2)
            is_me = (un == self.username)
            c = ctk.CTkFrame(self.lb_scroll,
                             fg_color=CARD2 if is_me else CARD,
                             corner_radius=10, border_width=1,
                             border_color=GOLD if is_me else BORDER)
            c.pack(fill="x", pady=2)
            cr = ctk.CTkFrame(c, fg_color="transparent"); cr.pack(fill="x", padx=14, pady=8)
            # Rank badge
            rank_col = [GOLD,"#9ca3af","#cd7f32",FG2][min(i,3)]
            lbl(cr, f"#{i+1}", color=rank_col, font=F_MONOS, width=40, anchor="w").pack(side="left", padx=4)
            lbl(cr, un,   color=GOLD if is_me else FG, font=F_BODY, width=150, anchor="w").pack(side="left", padx=4)
            lbl(cr, rar,  color=col,  font=F_SMALL, width=140, anchor="w").pack(side="left", padx=4)
            lbl(cr, str(rolls), color=FG2, font=F_MONOS, width=80, anchor="w").pack(side="left", padx=4)
            lbl(cr, str(lvl),   color=FG2, font=F_MONOS, width=60, anchor="w").pack(side="left", padx=4)
            lbl(cr, str(reb),   color=PURPLE, font=F_MONOS, width=70, anchor="w").pack(side="left", padx=4)
            lbl(cr, str(pvpw),  color=BLUE, font=F_MONOS, width=50, anchor="w").pack(side="left", padx=4)
            lbl(cr, str(bw),    color=RED,  font=F_MONOS, width=50, anchor="w").pack(side="left", padx=4)
            lbl(cr, str(rw),    color=PURPLE,  font=F_MONOS, width=50, anchor="w").pack(side="left", padx=4)
            lbl(cr, f"{int(score):,}", color=GOLD, font=F_MONOS, width=95, anchor="w").pack(side="left", padx=4)

    # ══════════════════════════════════════════════════════════════════════════
    #  PVP TAB
    # ══════════════════════════════════════════════════════════════════════════
    def _build_pvp_tab(self):
        tab = self.tabs.tab("⚔ PvP"); tab.configure(fg_color=BG)
        lbl(tab, "PvP Battles", font=F_TITLE).pack(pady=(16,4))
        lbl(tab, "Challenge other players. Set your battle titles, wager coins/shards, fight!",
            font=F_LABEL, color=FG2).pack()

        panes = ctk.CTkFrame(tab, fg_color="transparent"); panes.pack(fill="both", expand=True, padx=12, pady=8)

        # ── Left: battle titles + send challenge ──────────────────────────
        left = ctk.CTkFrame(panes, fg_color="transparent"); left.pack(side="left", fill="both", expand=True, padx=8)

        lbl(left, "Your Battle Titles", font=F_HEAD).pack(anchor="w", pady=(0,6))
        lbl(left, "Pick up to 3 titles to fight with (top by power if not set).",
            color=FG2, font=F_LABEL).pack(anchor="w")
        self.pvp_bt_lbl = lbl(left, "", color=PURPLE, font=F_SMALL); self.pvp_bt_lbl.pack(anchor="w", pady=4)
        ghost_btn(left, "Set Best 3 Automatically", self._auto_set_battle_titles, w=220, h=34).pack(anchor="w", pady=4)

        div = ctk.CTkFrame(left, fg_color=BORDER, height=1); div.pack(fill="x", pady=10)
        lbl(left, "Friends", font=F_HEAD).pack(anchor="w", pady=(0,6))
        fr = ctk.CTkFrame(left, fg_color="transparent"); fr.pack(fill="x", pady=4)
        self.friend_entry = ctk.CTkEntry(
            fr, width=220, height=34, corner_radius=10, fg_color=CARD2, border_color=BORDER2,
            text_color=FG, font=F_BODY, placeholder_text="username to add")
        self.friend_entry.pack(side="left", padx=(0,8))
        ghost_btn(fr, "Add Friend", self._send_friend_request, color=GREEN, w=110, h=34).pack(side="left")
        self.friend_status_lbl = lbl(left, "", color=FG2, font=F_LABEL); self.friend_status_lbl.pack(anchor="w", pady=(0,4))
        self.friend_list_scroll = ctk.CTkScrollableFrame(left, fg_color="transparent", height=90)
        self.friend_list_scroll.pack(fill="x", pady=(0,8))

        divf = ctk.CTkFrame(left, fg_color=BORDER, height=1); divf.pack(fill="x", pady=10)

        lbl(left, "Challenge a Player", font=F_HEAD).pack(anchor="w", pady=(0,6))
        un_row = ctk.CTkFrame(left, fg_color="transparent"); un_row.pack(fill="x", pady=4)
        lbl(un_row, "Username:", color=FG2, font=F_LABEL, width=80).pack(side="left")
        self.pvp_target_entry = ctk.CTkEntry(un_row, width=200, height=36, corner_radius=10,
                                              fg_color=CARD2, border_color=BORDER2, text_color=FG, font=F_BODY)
        self.pvp_target_entry.pack(side="left", padx=8)

        wr = ctk.CTkFrame(left, fg_color="transparent"); wr.pack(fill="x", pady=4)
        lbl(wr, "Wager:", color=FG2, font=F_LABEL, width=80).pack(side="left")
        self.pvp_wager_coins = ctk.CTkEntry(wr, width=100, height=34, corner_radius=10,
                                             fg_color=CARD2, border_color=BORDER2,
                                             text_color=GOLD, font=F_BODY, placeholder_text="coins")
        self.pvp_wager_coins.pack(side="left", padx=4)
        self.pvp_wager_shards = ctk.CTkEntry(wr, width=100, height=34, corner_radius=10,
                                              fg_color=CARD2, border_color=BORDER2,
                                              text_color=BLUE, font=F_BODY, placeholder_text="shards")
        self.pvp_wager_shards.pack(side="left", padx=4)

        self.pvp_send_lbl = lbl(left, "", color=FG2, font=F_LABEL); self.pvp_send_lbl.pack(anchor="w", pady=4)

        pill_btn(left, "⚔️  Send Battle Request", self._send_battle_request,
                 fg="#7f1d1d", hover="#991b1b", w=240, h=42).pack(anchor="w", pady=6)

        lbl(left, "Peek Inventory (10 shards)", font=F_HEAD).pack(anchor="w", pady=(12,4))
        pr = ctk.CTkFrame(left, fg_color="transparent"); pr.pack(fill="x", pady=4)
        self.pvp_peek_entry = ctk.CTkEntry(pr, width=200, height=36, corner_radius=10,
                                            fg_color=CARD2, border_color=BORDER2,
                                            text_color=FG, font=F_BODY, placeholder_text="username")
        self.pvp_peek_entry.pack(side="left", padx=(0,8))
        ghost_btn(pr, "Peek 👁", self._peek_inventory, w=100, h=36).pack(side="left")

        div2 = ctk.CTkFrame(left, fg_color=BORDER, height=1); div2.pack(fill="x", pady=12)
        lbl(left, "Trade Titles", font=F_HEAD).pack(anchor="w", pady=(0,6))
        lbl(left, "Send a title-for-title trade request.", color=FG2, font=F_LABEL).pack(anchor="w")

        tr1 = ctk.CTkFrame(left, fg_color="transparent"); tr1.pack(fill="x", pady=4)
        self.trade_target_entry = ctk.CTkEntry(
            tr1, width=200, height=34, corner_radius=10, fg_color=CARD2, border_color=BORDER2,
            text_color=FG, font=F_BODY, placeholder_text="trade partner")
        self.trade_target_entry.pack(side="left", padx=(0,8))
        self.trade_offer_title_entry = ctk.CTkEntry(
            tr1, width=200, height=34, corner_radius=10, fg_color=CARD2, border_color=BORDER2,
            text_color=FG, font=F_BODY, placeholder_text="you offer title")
        self.trade_offer_title_entry.pack(side="left")

        tr2 = ctk.CTkFrame(left, fg_color="transparent"); tr2.pack(fill="x", pady=4)
        self.trade_offer_count_entry = ctk.CTkEntry(
            tr2, width=100, height=34, corner_radius=10, fg_color=CARD2, border_color=BORDER2,
            text_color=FG, font=F_BODY, placeholder_text="offer #")
        self.trade_offer_count_entry.insert(0, "1")
        self.trade_offer_count_entry.pack(side="left", padx=(0,8))
        self.trade_request_title_entry = ctk.CTkEntry(
            tr2, width=200, height=34, corner_radius=10, fg_color=CARD2, border_color=BORDER2,
            text_color=FG, font=F_BODY, placeholder_text="you want title")
        self.trade_request_title_entry.pack(side="left", padx=(0,8))
        self.trade_request_count_entry = ctk.CTkEntry(
            tr2, width=100, height=34, corner_radius=10, fg_color=CARD2, border_color=BORDER2,
            text_color=FG, font=F_BODY, placeholder_text="want #")
        self.trade_request_count_entry.insert(0, "1")
        self.trade_request_count_entry.pack(side="left")
        pill_btn(left, "🤝 Send Trade Request", self._send_trade_request,
                 fg="#0f766e", hover="#115e59", w=240, h=40).pack(anchor="w", pady=6)

        # ── Right: inbox + battle results ──────────────────────────────────
        right = ctk.CTkFrame(panes, fg_color="transparent"); right.pack(side="right", fill="both", expand=True, padx=8)

        inb_hdr = ctk.CTkFrame(right, fg_color="transparent"); inb_hdr.pack(fill="x")
        lbl(inb_hdr, "Inbox", font=F_HEAD).pack(side="left")
        ghost_btn(inb_hdr, "↻", self._refresh_pvp, w=50, h=30).pack(side="right")

        self.pvp_inbox_scroll = ctk.CTkScrollableFrame(right, fg_color="transparent", height=220)
        self.pvp_inbox_scroll.pack(fill="x", pady=4)

        lbl(right, "Sent Requests", font=F_HEAD).pack(anchor="w", pady=(8,4))
        self.pvp_sent_scroll = ctk.CTkScrollableFrame(right, fg_color="transparent", height=160)
        self.pvp_sent_scroll.pack(fill="x", pady=4)

        lbl(right, "Friend Requests", font=F_HEAD).pack(anchor="w", pady=(8,4))
        self.friend_req_scroll = ctk.CTkScrollableFrame(right, fg_color="transparent", height=120)
        self.friend_req_scroll.pack(fill="x", pady=4)

        lbl(right, "Incoming Trades", font=F_HEAD).pack(anchor="w", pady=(8,4))
        self.trade_inbox_scroll = ctk.CTkScrollableFrame(right, fg_color="transparent", height=160)
        self.trade_inbox_scroll.pack(fill="x", pady=4)

        lbl(right, "Sent Trades", font=F_HEAD).pack(anchor="w", pady=(8,4))
        self.trade_sent_scroll = ctk.CTkScrollableFrame(right, fg_color="transparent", height=140)
        self.trade_sent_scroll.pack(fill="x", pady=4)

        lbl(right, "Last Battle Result", font=F_HEAD).pack(anchor="w", pady=(8,4))
        self.pvp_result_frame = ctk.CTkScrollableFrame(right, fg_color="transparent", height=200)
        self.pvp_result_frame.pack(fill="both", expand=True, pady=4)

    def _auto_set_battle_titles(self):
        titles = get_best_titles(self.engine.state, 3)
        if not titles: self._notify("No titles in inventory!", RED); return
        self.engine.set_battle_titles(titles)
        self._refresh_pvp_titles()
        self._notify(f"Battle titles set: {', '.join(titles)}", PURPLE)

    def _refresh_pvp_titles(self):
        self.engine._sanitize_battle_titles()
        bt = self.engine.get_battle_titles_for_pvp()
        if bt:
            slots = bt + ["[Empty Slot]"] * max(0, 3 - len(bt))
            self.pvp_bt_lbl.configure(text="  ·  ".join(slots), text_color=PURPLE)
        else:
            self.pvp_bt_lbl.configure(text="No titles selected", text_color=FG2)

    def _send_friend_request(self):
        if not self.username:
            self._notify("Must be logged in for friends.", RED); return
        target = self.friend_entry.get().strip()
        if not target:
            self._notify("Enter a username to add.", RED); return
        self._send_friend_request_target(target, status_setter=lambda: self.friend_status_lbl.configure(text=f"Friend request: {target}"))

    def _send_friend_request_roll(self):
        if not self.username:
            self._notify("Must be logged in for friends.", RED); return
        target = self.roll_friend_entry.get().strip() if hasattr(self, "roll_friend_entry") else ""
        if not target:
            self._notify("Enter a username to add.", RED); return
        self._send_friend_request_target(target, status_setter=lambda: self.roll_friend_status.configure(text=f"Request sent: {target}"))

    def _send_friend_request_target(self, target: str, status_setter=None):
        def _bg():
            ok, msg = self.db.send_friend_request(self.username, target)
            self._ui_after(0, lambda: self._notify(msg, GREEN if ok else RED))
            if ok and status_setter:
                self._ui_after(0, status_setter)
            self._ui_after(120, self._refresh_pvp)
            self._ui_after(120, self._refresh_roll_friends_async)
        threading.Thread(target=_bg, daemon=True).start()

    def _accept_friend_request(self, req_id: int):
        def _bg():
            ok = self.db.accept_friend_request(req_id)
            self._ui_after(0, lambda: self._notify("Friend added!" if ok else "Could not accept friend request.", GREEN if ok else RED))
            self._ui_after(120, self._refresh_pvp)
        threading.Thread(target=_bg, daemon=True).start()

    def _decline_friend_request(self, req_id: int):
        def _bg():
            self.db.decline_friend_request(req_id)
            self._ui_after(0, lambda: self._notify("Friend request declined.", FG2))
            self._ui_after(120, self._refresh_pvp)
        threading.Thread(target=_bg, daemon=True).start()

    def _send_battle_request(self):
        if not self.username: self._notify("Must be logged in for PvP!", RED); return
        if not self.engine.get_battle_titles_for_pvp():
            self._notify("Set at least 1 battle title you actually own first.", RED); return
        target = self.pvp_target_entry.get().strip()
        if not target: self._notify("Enter a username to challenge!", RED); return
        if target == self.username: self._notify("Can't challenge yourself!", RED); return
        # Validate wager
        try:
            wc = int(self.pvp_wager_coins.get() or 0)
            ws = int(self.pvp_wager_shards.get() or 0)
        except ValueError:
            self._notify("Wager must be numbers!", RED); return
        if wc < 0 or ws < 0: self._notify("Wager can't be negative!", RED); return
        s = self.engine.state
        if wc > s.coins:  self._notify(f"Not enough coins (have {s.coins})", RED); return
        if ws > s.shards: self._notify(f"Not enough shards (have {s.shards})", RED); return
        def _bg():
            ok, msg = self.db.send_battle_request(self.username, target, wc, ws)
            self._ui_after(0, lambda: self._notify(msg, GREEN if ok else RED))
            self._ui_after(100, self._refresh_pvp)
        threading.Thread(target=_bg, daemon=True).start()
        self.pvp_send_lbl.configure(text=f"Sending to {target}…", text_color=FG2)

    def _peek_inventory(self):
        if not self.username: self._notify("Must be logged in!", RED); return
        target = self.pvp_peek_entry.get().strip()
        if not target: self._notify("Enter a username!", RED); return
        if self.engine.state.shards < 10: self._notify("Need 10 shards to peek!", RED); return
        self.engine.state.shards -= 10; self.engine.save_game()
        self._refresh_top_bar()
        def _bg():
            profile = self.db.get_player_profile(target)
            self._ui_after(0, lambda: self._show_peek(target, profile))
        threading.Thread(target=_bg, daemon=True).start()

    def _show_peek(self, username: str, profile: Optional[dict]):
        for w in self.pvp_result_frame.winfo_children(): w.destroy()
        if not profile:
            lbl(self.pvp_result_frame, f"Player '{username}' not found.", color=RED).pack(pady=10); return
        lbl(self.pvp_result_frame, f"👁  {username}'s Inventory", font=F_HEAD, color=GOLD).pack(anchor="w", pady=(4,8))
        data = profile["data"]
        inventory = data.get("inventory", {}) if isinstance(data, dict) else {}
        if not inventory:
            lbl(self.pvp_result_frame, "Empty inventory.", color=FG2).pack(); return
        items = [(t, c, _title_rarity(t)) for t, c in inventory.items()]
        items.sort(key=lambda x: -RARITY_ORDER.index(x[2]))
        for title, count, rarity in items[:20]:
            col = RARITIES.get(rarity,{}).get("color", FG2)
            r = ctk.CTkFrame(self.pvp_result_frame, fg_color=CARD, corner_radius=8)
            r.pack(fill="x", pady=2)
            lbl(r, rarity, color=col, font=F_LABEL, width=90, anchor="w").pack(side="left", padx=8, pady=6)
            lbl(r, title, color=FG, font=F_BODY).pack(side="left")
            lbl(r, f"×{count}", color=FG2, font=F_MONOS).pack(side="right", padx=10)

    def _send_trade_request(self):
        if not self.username:
            self._notify("Must be logged in for trading.", RED); return
        target = self.trade_target_entry.get().strip()
        offered_title = self.trade_offer_title_entry.get().strip()
        requested_title = self.trade_request_title_entry.get().strip()
        if not target or not offered_title or not requested_title:
            self._notify("Fill in partner + offered title + requested title.", RED); return
        if not self.db.are_friends(self.username, target):
            self._notify("You can only trade with friends.", RED); return
        try:
            offered_count = int(self.trade_offer_count_entry.get() or 1)
            requested_count = int(self.trade_request_count_entry.get() or 1)
        except ValueError:
            self._notify("Trade counts must be valid numbers.", RED); return
        if offered_count <= 0 or requested_count <= 0:
            self._notify("Trade counts must be at least 1.", RED); return
        ok, msg = self.engine.can_send_trade(offered_title, offered_count)
        if not ok:
            self._notify(msg, RED); return
        def _bg():
            ok2, msg2 = self.db.send_trade_request(
                self.username, target, offered_title, offered_count, requested_title, requested_count)
            self._ui_after(0, lambda: self._notify(msg2, GREEN if ok2 else RED))
            self._ui_after(120, self._refresh_pvp)
        threading.Thread(target=_bg, daemon=True).start()

    def _accept_trade(self, trade: dict):
        if not self.username:
            return
        trade_id = trade["id"]
        sender = trade["sender"]
        offered_title = trade["offered_title"]; offered_count = int(trade["offered_count"] or 1)
        requested_title = trade["requested_title"]; requested_count = int(trade["requested_count"] or 1)
        s = self.engine.state
        if s.inventory.get(requested_title, 0) < requested_count:
            self._notify(f"Need {requested_count}× {requested_title} to accept.", RED); return

        def _bg():
            profile = self.db.get_player_profile(sender)
            if not profile:
                self._ui_after(0, lambda: self._notify("Trader no longer exists.", RED)); return
            try:
                sender_state = PlayerState.from_dict(profile["data"])
            except Exception:
                sender_state = PlayerState()
            if sender_state.inventory.get(offered_title, 0) < offered_count:
                self._ui_after(0, lambda: self._notify("Sender no longer has offered titles.", RED)); return
            # Local receiver adjustments
            s.inventory[requested_title] -= requested_count
            if s.inventory[requested_title] <= 0:
                del s.inventory[requested_title]
                if s.equipped_title == requested_title:
                    s.equipped_title = None; s.equipped_rarity = None
            s.inventory[offered_title] = s.inventory.get(offered_title, 0) + offered_count
            s.title_trades_completed += 1
            # Sender adjustments
            sender_state.inventory[offered_title] -= offered_count
            if sender_state.inventory[offered_title] <= 0:
                del sender_state.inventory[offered_title]
                if sender_state.equipped_title == offered_title:
                    sender_state.equipped_title = None; sender_state.equipped_rarity = None
            sender_state.inventory[requested_title] = sender_state.inventory.get(requested_title, 0) + requested_count
            sender_state.title_trades_completed += 1

            self.engine.save_game()
            self.db.save_player(sender, sender_state)
            self.db.resolve_trade(trade_id)
            self._ui_after(0, lambda: self._notify("Trade completed successfully.", GREEN))
            self._ui_after(0, self._refresh_inventory)
            self._ui_after(0, self._refresh_top_bar)
            self._ui_after(120, self._refresh_pvp)
        threading.Thread(target=_bg, daemon=True).start()

    def _decline_trade(self, trade_id: int):
        def _bg():
            self.db.decline_trade(trade_id)
            self._ui_after(0, lambda: self._notify("Trade declined.", FG2))
            self._ui_after(120, self._refresh_pvp)
        threading.Thread(target=_bg, daemon=True).start()

    def _refresh_pvp(self):
        if not self.username: return
        def _bg():
            inbox = self.db.get_pending_requests(self.username)
            sent  = self.db.get_sent_requests(self.username)
            in_trades = self.db.get_incoming_trades(self.username)
            out_trades = self.db.get_outgoing_trades(self.username)
            friends = self.db.get_friends(self.username)
            fin = self.db.get_incoming_friend_requests(self.username)
            fout = self.db.get_outgoing_friend_requests(self.username)
            self._ui_after(0, lambda: self._render_pvp_inbox(inbox, sent, in_trades, out_trades, friends, fin, fout))
        threading.Thread(target=_bg, daemon=True).start()
        self._refresh_pvp_titles()

    def _render_pvp_inbox(self, inbox: list, sent: list, in_trades: list, out_trades: list,
                          friends: list, fin: list, fout: list):
        self._render_roll_friends(friends)
        for w in self.friend_list_scroll.winfo_children(): w.destroy()
        if not friends:
            lbl(self.friend_list_scroll, "No friends yet.", color=FG2).pack(pady=4)
        else:
            for fr in friends[:25]:
                r = ctk.CTkFrame(self.friend_list_scroll, fg_color=CARD, corner_radius=8)
                r.pack(fill="x", pady=2)
                rr = ctk.CTkFrame(r, fg_color="transparent"); rr.pack(fill="x", padx=10, pady=6)
                lbl(rr, fr, color=FG, font=F_BODY).pack(side="left")
                ghost_btn(rr, "Use", lambda u=fr: self._open_player_profile(u), w=64, h=26).pack(side="right")

        for w in self.friend_req_scroll.winfo_children(): w.destroy()
        if not fin and not fout:
            lbl(self.friend_req_scroll, "No pending friend requests.", color=FG2).pack(pady=4)
        else:
            for req in fin[:8]:
                rid = req["id"]; sender = req["sender"]
                c = card_frame(self.friend_req_scroll); c.pack(fill="x", pady=2)
                cr = ctk.CTkFrame(c, fg_color="transparent"); cr.pack(fill="x", padx=8, pady=6)
                lbl(cr, f"From {sender}", font=F_BODY).pack(side="left")
                pill_btn(cr, "Accept", lambda i=rid: self._accept_friend_request(i),
                         fg="#166534", hover="#14532d", w=76, h=28).pack(side="right", padx=(4,0))
                ghost_btn(cr, "Decline", lambda i=rid: self._decline_friend_request(i),
                          color=RED, w=76, h=28).pack(side="right")
            for req in fout[:8]:
                c = ctk.CTkFrame(self.friend_req_scroll, fg_color=CARD, corner_radius=8)
                c.pack(fill="x", pady=2)
                cr = ctk.CTkFrame(c, fg_color="transparent"); cr.pack(fill="x", padx=8, pady=6)
                lbl(cr, f"Pending → {req['receiver']}", color=FG2, font=F_LABEL).pack(side="left")

        for w in self.pvp_inbox_scroll.winfo_children(): w.destroy()
        if not inbox:
            lbl(self.pvp_inbox_scroll, "No pending challenges.", color=FG2).pack(pady=8)
        else:
            for req in inbox:
                rid  = req["id"]; challenger = req["challenger"]
                wc   = req.get("wager_coins",0) or 0
                ws   = req.get("wager_shards",0) or 0
                c = card_frame(self.pvp_inbox_scroll); c.pack(fill="x", pady=4)
                cr = ctk.CTkFrame(c, fg_color="transparent"); cr.pack(fill="x", padx=14, pady=10)
                lbl(cr, f"⚔  {challenger} challenges you!", font=F_BODY).pack(anchor="w")
                lbl(cr, f"Wager: {wc}🪙  {ws}💎", color=GOLD, font=F_SMALL).pack(anchor="w")
                br = ctk.CTkFrame(cr, fg_color="transparent"); br.pack(anchor="w", pady=6)
                pill_btn(br, "Accept & Fight", lambda r=req: self._accept_battle(r),
                         fg="#166534", hover="#14532d", w=150, h=34).pack(side="left", padx=(0,8))
                ghost_btn(br, "Decline", lambda rid2=rid: self._decline_battle(rid2),
                          color=RED, w=90, h=34).pack(side="left")

        for w in self.pvp_sent_scroll.winfo_children(): w.destroy()
        if not sent:
            lbl(self.pvp_sent_scroll, "No sent requests.", color=FG2).pack(pady=4)
        else:
            for req in sent[:10]:
                defender = req["defender"]; status = req.get("status","pending")
                wc = req.get("wager_coins",0) or 0; ws = req.get("wager_shards",0) or 0
                col = GREEN if status=="resolved" else (RED if status=="declined" else FG2)
                c = ctk.CTkFrame(self.pvp_sent_scroll, fg_color=CARD, corner_radius=8)
                c.pack(fill="x", pady=2)
                cr = ctk.CTkFrame(c, fg_color="transparent"); cr.pack(fill="x", padx=12, pady=6)
                lbl(cr, f"→ {defender}", font=F_BODY).pack(side="left")
                lbl(cr, f"{wc}🪙 {ws}💎", color=GOLD, font=F_LABEL).pack(side="left", padx=8)
                lbl(cr, status.upper(), color=col, font=F_LABEL).pack(side="right")

        for w in self.trade_inbox_scroll.winfo_children(): w.destroy()
        if not in_trades:
            lbl(self.trade_inbox_scroll, "No pending trades.", color=FG2).pack(pady=4)
        else:
            for tr in in_trades[:10]:
                tid = tr["id"]
                card = card_frame(self.trade_inbox_scroll); card.pack(fill="x", pady=3)
                cr = ctk.CTkFrame(card, fg_color="transparent"); cr.pack(fill="x", padx=12, pady=8)
                lbl(cr, f"From {tr['sender']}", font=F_BODY).pack(anchor="w")
                lbl(cr, f"Gives: {tr['offered_count']}× {tr['offered_title']}", color=GREEN, font=F_LABEL).pack(anchor="w")
                lbl(cr, f"Wants: {tr['requested_count']}× {tr['requested_title']}", color=GOLD, font=F_LABEL).pack(anchor="w")
                br = ctk.CTkFrame(cr, fg_color="transparent"); br.pack(anchor="w", pady=4)
                pill_btn(br, "Accept Trade", lambda t=tr: self._accept_trade(t),
                         fg="#166534", hover="#14532d", w=130, h=32).pack(side="left", padx=(0,8))
                ghost_btn(br, "Decline", lambda x=tid: self._decline_trade(x), color=RED, w=90, h=32).pack(side="left")

        for w in self.trade_sent_scroll.winfo_children(): w.destroy()
        if not out_trades:
            lbl(self.trade_sent_scroll, "No sent trades.", color=FG2).pack(pady=4)
        else:
            for tr in out_trades[:10]:
                col = GREEN if tr["status"] == "resolved" else (RED if tr["status"] == "declined" else FG2)
                card = ctk.CTkFrame(self.trade_sent_scroll, fg_color=CARD, corner_radius=8)
                card.pack(fill="x", pady=2)
                cr = ctk.CTkFrame(card, fg_color="transparent"); cr.pack(fill="x", padx=10, pady=6)
                lbl(cr, f"→ {tr['receiver']}", font=F_BODY).pack(side="left")
                lbl(cr, f"{tr['offered_count']}×{tr['offered_title']} ↔ {tr['requested_count']}×{tr['requested_title']}",
                    color=FG2, font=F_LABEL).pack(side="left", padx=8)
                lbl(cr, tr["status"].upper(), color=col, font=F_LABEL).pack(side="right")

    def _accept_battle(self, req: dict):
        if not self.username: return
        if not self.engine.get_battle_titles_for_pvp():
            self._notify("Set at least 1 battle title you own before accepting.", RED); return
        rid        = req["id"]
        challenger = req["challenger"]
        wc         = req.get("wager_coins",0) or 0
        ws         = req.get("wager_shards",0) or 0
        s = self.engine.state

        # Check wager can be covered by both
        if wc > s.coins:  self._notify(f"Need {wc} coins to accept wager!", RED); return
        if ws > s.shards: self._notify(f"Need {ws} shards to accept wager!", RED); return

        # Fetch challenger profile
        def _bg():
            profile = self.db.get_player_profile(challenger)
            if not profile:
                self._ui_after(0, lambda: self._notify("Challenger not found!", RED)); return
            cdata = profile["data"]
            try:
                cstate = PlayerState.from_dict(cdata)
            except:
                cstate = PlayerState()
            if not get_best_titles(cstate, 3):
                self._ui_after(0, lambda: self._notify("Challenger has no valid battle titles.", RED))
                return
            if wc > cstate.coins or ws > cstate.shards:
                self._ui_after(0, lambda: self._notify("Challenger can no longer cover this wager.", RED))
                return
            my_titles   = self.engine.get_battle_titles_for_pvp()
            opp_titles  = get_best_titles(cstate, 3)
            result      = pvp_simulate(my_titles, opp_titles)
            won         = result["winner"] == "me"

            # Apply wager
            if won:
                s.coins  += wc; s.shards += ws
                s.pvp_wins += 1
                # Deduct from challenger (best effort via DB update)
                cstate.coins  = max(0, cstate.coins - wc)
                cstate.shards = max(0, cstate.shards - ws)
                cstate.pvp_losses += 1
            else:
                s.coins  = max(0, s.coins - wc)
                s.shards = max(0, s.shards - ws)
                s.pvp_losses += 1
                cstate.coins  += wc; cstate.shards += ws
                cstate.pvp_wins += 1

            achs = self.engine.check_achievements()
            self.engine.save_game()
            self.db.save_player(challenger, cstate)
            self.db.resolve_battle(rid, result, self.username if won else challenger)

            self._ui_after(0, lambda: self._show_pvp_result(result, won, challenger, wc, ws, achs))
        threading.Thread(target=_bg, daemon=True).start()

    def _show_pvp_result(self, result: dict, won: bool, opponent: str,
                          wc: int, ws: int, achs: list):
        self._refresh_top_bar()
        self._refresh_pvp()
        for w in self.pvp_result_frame.winfo_children(): w.destroy()

        outcome_col = GREEN if won else RED
        outcome_txt = "VICTORY!" if won else "DEFEAT"
        lbl(self.pvp_result_frame, f"⚔  vs {opponent}  —  {outcome_txt}",
            font=F_TITLE, color=outcome_col).pack(pady=(8,12))
        if wc or ws:
            wager_msg = (f"+{wc}🪙 +{ws}💎" if won else f"-{wc}🪙 -{ws}💎")
            lbl(self.pvp_result_frame, f"Wager: {wager_msg}", color=GOLD, font=F_BODY).pack()

        for i, rnd in enumerate(result.get("rounds", [])):
            rw = won if rnd["winner"] == "me" else not won
            rc = GREEN if rnd["winner"] == "me" else RED
            mc = RARITIES.get(rnd["my_rarity"],{}).get("color", FG2)
            oc = RARITIES.get(rnd["opp_rarity"],{}).get("color", FG2)
            hype = random.choice(["⚡ Clash!", "🔥 Burst!", "💥 Impact!", "🌀 Momentum Shift!", "✨ Critical Moment!"])
            c = ctk.CTkFrame(self.pvp_result_frame, fg_color=CARD, corner_radius=10, border_width=1, border_color=rc)
            c.pack(fill="x", pady=4)
            cr = ctk.CTkFrame(c, fg_color="transparent"); cr.pack(fill="x", padx=14, pady=8)
            lbl(cr, f"Round {i+1}  ·  {hype}", color=FG2, font=F_LABEL).pack(anchor="w")
            vs = ctk.CTkFrame(cr, fg_color="transparent"); vs.pack(fill="x", pady=4)
            left2 = ctk.CTkFrame(vs, fg_color="transparent"); left2.pack(side="left", expand=True)
            lbl(left2, rnd["my_title"],   color=mc, font=F_BODY).pack()
            lbl(left2, f"Power: {rnd['my_power']}", color=FG2, font=F_LABEL).pack()
            lbl(vs, "VS", color=FG2, font=F_LABEL).pack(side="left", padx=12)
            right2 = ctk.CTkFrame(vs, fg_color="transparent"); right2.pack(side="right", expand=True)
            lbl(right2, rnd["opp_title"],  color=oc, font=F_BODY).pack()
            lbl(right2, f"Power: {rnd['opp_power']}", color=FG2, font=F_LABEL).pack()
            winner_txt = "✅ You win!" if rnd["winner"]=="me" else "❌ They win"
            lbl(cr, winner_txt, color=rc, font=F_SMALL).pack()

        score_txt = f"{result['my_score']} — {result['opp_score']}"
        lbl(self.pvp_result_frame, f"Final Score: {score_txt}", font=F_HEAD, color=outcome_col).pack(pady=8)

        if won: self._big_notify(f"⚔  PvP VICTORY!\nvs {opponent}", GREEN)
        else:   self._notify(f"⚔  Defeated by {opponent}.", RED)
        for a in achs: self._notify(f"🏆 {a['name']}", GOLD)

    def _decline_battle(self, request_id: int):
        def _bg(): self.db.decline_request(request_id); self.after(100, self._refresh_pvp)
        threading.Thread(target=_bg, daemon=True).start()
        self._notify("Battle request declined.", FG2)

    def _open_player_profile(self, username: str):
        """Switch to PvP tab and pre-fill the peek/challenge entries."""
        self.tabs.set("⚔ PvP")
        try:
            self.pvp_target_entry.delete(0, "end")
            self.pvp_target_entry.insert(0, username)
            self.pvp_peek_entry.delete(0, "end")
            self.pvp_peek_entry.insert(0, username)
            self.trade_target_entry.delete(0, "end")
            self.trade_target_entry.insert(0, username)
        except: pass

    # ══════════════════════════════════════════════════════════════════════════
    #  STATS TAB
    # ══════════════════════════════════════════════════════════════════════════
    def _build_stats_tab(self):
        tab = self.tabs.tab("📊 Stats"); tab.configure(fg_color=BG)
        lbl(tab, "Statistics", font=F_TITLE).pack(pady=(16,8))
        self._stats_scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        self._stats_scroll.pack(fill="both", expand=True, padx=24, pady=8)
        self._stat_vals = {}
        rows = [
            ("⚡","Total Rolls","total_rolls"),("🏆","Arena Wins","total_wins"),
            ("💀","Losses","total_losses"),("👹","Boss Wins","total_boss_wins"),
            ("⚔","PvP Wins","pvp_wins"),("🤝","PvP Losses","pvp_losses"),
            ("🔄","Trades","title_trades_completed"),
            ("🌀","Void Essence","void_essence"),("🌌","Rift Wins","total_rift_wins"),
            ("⚗️","Merges","total_merges"),("🔮","Crafts","total_crafts"),
            ("🌟","Highest Rarity","highest_rarity_pulled"),("♻️","Rebirths","rebirths"),
            ("🍀","Lucky Rolls","lucky_rolls"),("🎯","Pity Counter","pity_counter"),
            ("✨","Luck Multiplier","luck_multiplier"),("🏅","Achievements","_ach_count"),
        ]
        for icon, label_, key in rows:
            row = ctk.CTkFrame(self._stats_scroll, fg_color=CARD, corner_radius=12, border_width=1, border_color=BORDER)
            row.pack(fill="x", pady=3)
            lbl(row, icon, font=(_FONT,14)).pack(side="left", padx=(14,8), pady=10)
            lbl(row, label_, color=FG2, font=F_BODY).pack(side="left")
            v = lbl(row, "—", color=FG, font=F_MONOS); v.pack(side="right", padx=16)
            self._stat_vals[key] = v
        lbl(self._stats_scroll, "Achievements", font=F_HEAD, color=GOLD).pack(pady=(20,8))
        self.ach_frame = ctk.CTkFrame(self._stats_scroll, fg_color="transparent"); self.ach_frame.pack(fill="x")

    def _refresh_stats(self):
        s = self.engine.state
        data = {
            "total_rolls":str(s.total_rolls),"total_wins":str(s.total_wins),
            "total_losses":str(s.total_losses),"total_boss_wins":str(s.total_boss_wins),
            "pvp_wins":str(s.pvp_wins),"pvp_losses":str(s.pvp_losses),
            "title_trades_completed":str(s.title_trades_completed),
            "void_essence":str(s.void_essence),"total_rift_wins":str(s.total_rift_wins),
            "total_merges":str(s.total_merges),"total_crafts":str(s.total_crafts),
            "highest_rarity_pulled":s.highest_rarity_pulled,"rebirths":str(s.rebirths),
            "lucky_rolls":str(s.lucky_rolls),"pity_counter":str(s.pity_counter),
            "luck_multiplier":f"{s.luck_multiplier:.2f}×",
            "_ach_count":f"{len(s.achievements)} / {len(ACHIEVEMENTS)}",
        }
        for key, val in data.items():
            if key not in self._stat_vals: continue
            col = RARITIES[val]["color"] if key=="highest_rarity_pulled" and val in RARITIES else FG
            self._stat_vals[key].configure(text=val, text_color=col)
        for w in self.ach_frame.winfo_children(): w.destroy()
        for ach in ACHIEVEMENTS:
            got = ach["id"] in s.achievements
            row = ctk.CTkFrame(self.ach_frame, fg_color=CARD2 if got else CARD,
                               corner_radius=10, border_width=1, border_color=BORDER)
            row.pack(fill="x", pady=2)
            lbl(row, "✅" if got else "🔒", font=(_FONT,12)).pack(side="left", padx=(12,6), pady=8)
            lbl(row, ach["name"],  font=F_BODY, color=GOLD if got else FG2).pack(side="left")
            lbl(row, ach["desc"],  font=F_LABEL, color=FG2 if got else "#2a2a3a").pack(side="left", padx=8)
            if got:
                lbl(row, f"+{ach['rc']}🪙  +{ach['rs']}💎", font=F_LABEL, color=GREEN).pack(side="right", padx=14)

    # ══════════════════════════════════════════════════════════════════════════
    #  REBIRTH TAB
    # ══════════════════════════════════════════════════════════════════════════
    def _build_rebirth_tab(self):
        tab = self.tabs.tab("♻️ Rebirth"); tab.configure(fg_color=BG)
        self.rb_lock_lbl = lbl(tab, "", color=RED, font=F_SMALL); self.rb_lock_lbl.pack(pady=6)
        lbl(tab, "Rebirth", font=F_HERO, color="#c084fc").pack(pady=(16,4))
        lbl(tab, "Reset your progress for a permanent power upgrade.", color=FG2, font=F_BODY).pack()
        info = card_frame(tab, width=540, height=260); info.pack(pady=20); info.pack_propagate(False)
        lbl(info, "Requirements", font=F_HEAD, color=GOLD).pack(pady=(16,8))
        lbl(info, f"• Level {UNLOCKS['rebirth']}+", font=F_BODY).pack()
        lbl(info, "• Must have pulled Legendary+", font=F_BODY).pack()
        self.rb_cost_lbl = lbl(info, "", color=GOLD, font=F_BODY); self.rb_cost_lbl.pack(pady=6)
        div = ctk.CTkFrame(info, fg_color=BORDER, height=1); div.pack(fill="x", padx=24, pady=8)
        lbl(info, "Reward", font=F_HEAD, color=GREEN).pack()
        lbl(info, "+20% permanent luck multiplier per rebirth", color=FG2, font=F_SMALL).pack(pady=2)
        lbl(info, "Each rebirth also grants 1 Rebirth Point for upgrades.", color=FG2, font=F_SMALL).pack(pady=2)
        self.rb_count_lbl = lbl(info, "", color="#c084fc", font=F_BODY); self.rb_count_lbl.pack(pady=4)
        self.rb_points_lbl = lbl(info, "", color=BLUE, font=F_BODY); self.rb_points_lbl.pack(pady=2)
        self.rb_reasons_lbl = lbl(tab, "", font=F_SMALL, color=RED); self.rb_reasons_lbl.pack(pady=4)
        pill_btn(tab, "♻️  Rebirth Now", self._do_rebirth, fg="#581c87", hover="#4c1d95",
                 font=F_HEAD, w=230, h=54).pack(pady=10)
        self.rb_upg_frame = ctk.CTkScrollableFrame(tab, fg_color="transparent", height=230)
        self.rb_upg_frame.pack(fill="both", expand=True, padx=22, pady=(4, 10))

    # ══════════════════════════════════════════════════════════════════════════
    #  ENDGAME TAB
    # ══════════════════════════════════════════════════════════════════════════
    def _build_endgame_tab(self):
        tab = self.tabs.tab("🌌 Endgame"); tab.configure(fg_color=BG)
        lbl(tab, "Endgame Rifts", font=F_TITLE).pack(pady=(16,4))
        lbl(tab, "Late-game rebirth challenges with heavy rewards.", color=FG2, font=F_LABEL).pack()
        self.eg_info_lbl = lbl(tab, "", color=BLUE, font=F_SMALL); self.eg_info_lbl.pack(pady=4)
        self.eg_lock_lbl = lbl(tab, "", color=RED, font=F_SMALL); self.eg_lock_lbl.pack(pady=2)
        self.eg_scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        self.eg_scroll.pack(fill="both", expand=True, padx=18, pady=8)
        self._eg_cd_lbls = {}
        self._eg_res_lbls = {}

    def _refresh_endgame(self):
        if not hasattr(self, "eg_scroll"):
            return
        s = self.engine.state
        self.eg_info_lbl.configure(
            text=f"Void Essence: {s.void_essence}  ·  Rift Wins: {s.total_rift_wins}  ·  Rebirths: {s.rebirths}")
        locked = s.level < 45 or s.rebirths < 3
        self.eg_lock_lbl.configure(
            text="🔒 Unlocks at Level 45 and 3 Rebirths" if locked else "")
        for w in self.eg_scroll.winfo_children(): w.destroy()
        self._eg_cd_lbls.clear(); self._eg_res_lbls.clear()

        for rift in ENDGAME_RIFTS:
            ok, reason, _ = self.engine.can_enter_rift(rift["id"])
            unlocked = s.level >= rift["req_level"] and s.rebirths >= rift["req_rebirths"]
            border = "#7c3aed" if unlocked else BORDER
            card = card_frame(self.eg_scroll, border_color=border)
            card.pack(fill="x", pady=6, padx=4)
            row = ctk.CTkFrame(card, fg_color="transparent"); row.pack(fill="x", padx=14, pady=12)
            left = ctk.CTkFrame(row, fg_color="transparent"); left.pack(side="left", fill="both", expand=True)
            lbl(left, f"{rift['emoji']}  {rift['name']}", font=F_HEAD,
                color=PURPLE if unlocked else FG2).pack(anchor="w")
            lbl(left, rift["desc"], font=F_LABEL, color=FG2).pack(anchor="w", pady=2)
            req = ctk.CTkFrame(left, fg_color="transparent"); req.pack(anchor="w", pady=2)
            lbl(req, f"Lv.{rift['req_level']}+", color=GREEN if s.level >= rift["req_level"] else RED, font=F_LABEL).pack(side="left", padx=(0,8))
            lbl(req, f"Rebirth {rift['req_rebirths']}+", color=GREEN if s.rebirths >= rift["req_rebirths"] else RED, font=F_LABEL).pack(side="left", padx=(0,8))
            lbl(req, f"Power {rift['base_power']}", color=FG2, font=F_LABEL).pack(side="left")
            rew = ctk.CTkFrame(left, fg_color="transparent"); rew.pack(anchor="w")
            lbl(rew, f"🪙 {rift['reward_coins']}", color=GOLD, font=F_LABEL).pack(side="left", padx=(0,8))
            lbl(rew, f"💎 {rift['reward_shards']}", color=BLUE, font=F_LABEL).pack(side="left", padx=(0,8))
            lbl(rew, f"🌀 {rift['reward_essence']} essence", color=PURPLE, font=F_LABEL).pack(side="left", padx=(0,8))
            lbl(rew, f"Guarantee: {rift['guarantee']}+", color=RARITIES[rift["guarantee"]]["color"], font=F_LABEL).pack(side="left")

            right = ctk.CTkFrame(row, fg_color="transparent", width=230); right.pack(side="right"); right.pack_propagate(False)
            lbl(right, f"Cost: {rift['token_cost']}🔑 + {rift['shard_cost']}💎", color=RED if unlocked else FG2, font=F_LABEL).pack(pady=(2,4))
            cd = self.engine.cooldown_remaining(f"rift_{rift['id']}", rift["cooldown"])
            cdt = f"⏳ {fmt_cd(cd)}" if cd > 0 else ("✅ Ready" if unlocked else "🔒 Locked")
            cdc = RED if cd > 0 else (GREEN if unlocked else FG2)
            cd_lbl = lbl(right, cdt, color=cdc, font=F_LABEL); cd_lbl.pack()
            self._eg_cd_lbls[rift["id"]] = cd_lbl
            res_lbl = lbl(right, "", color=FG, font=F_LABEL); res_lbl.pack(pady=2)
            self._eg_res_lbls[rift["id"]] = res_lbl
            btn = pill_btn(right, "Enter Rift", lambda rid=rift["id"]: self._do_rift(rid),
                           fg="#4c1d95" if unlocked else FG2, hover="#5b21b6" if unlocked else FG2,
                           w=170, h=36)
            if not ok:
                btn.configure(state="disabled")
                if unlocked and reason:
                    res_lbl.configure(text=reason, text_color=RED)
            btn.pack(pady=4)

    def _do_rift(self, rift_id: str):
        win, name, title, rarity, achs = self.engine.perform_rift_run(rift_id)
        if not win:
            self._notify(f"Rift failed: {name}", RED)
            if rift_id in self._eg_res_lbls:
                self._eg_res_lbls[rift_id].configure(text="❌ Failed run", text_color=RED)
        else:
            col = RARITIES.get(rarity or "Legendary", {}).get("color", GREEN)
            self._notify(f"🌌 Cleared {name}!", GREEN)
            if rift_id in self._eg_res_lbls:
                self._eg_res_lbls[rift_id].configure(text=f"✅ {title}", text_color=GREEN)
            if title and rarity:
                self._big_notify(f"🌌 RIFT CLEAR!\n{title}  [{rarity}]", col)
        for a in (achs or []):
            self._notify(f"🏆 {a['name']}", GOLD)
        self._refresh_top_bar()
        self._refresh_inventory()
        self._refresh_collection()
        self._refresh_stats()
        self._refresh_endgame()

    def _refresh_endgame_cds(self):
        if not hasattr(self, "_eg_cd_lbls"):
            return
        s = self.engine.state
        for rift in ENDGAME_RIFTS:
            rid = rift["id"]
            if rid not in self._eg_cd_lbls:
                continue
            unlocked = s.level >= rift["req_level"] and s.rebirths >= rift["req_rebirths"]
            if not unlocked:
                self._eg_cd_lbls[rid].configure(text="🔒 Locked", text_color=FG2)
                continue
            cd = self.engine.cooldown_remaining(f"rift_{rid}", rift["cooldown"])
            if cd > 0:
                self._eg_cd_lbls[rid].configure(text=f"⏳ {fmt_cd(cd)}", text_color=RED)
            else:
                self._eg_cd_lbls[rid].configure(text="✅ Ready", text_color=GREEN)

    # ══════════════════════════════════════════════════════════════════════════
    #  UPDATES TAB
    # ══════════════════════════════════════════════════════════════════════════
    def _build_updates_tab(self):
        tab = self.tabs.tab("📰 Updates"); tab.configure(fg_color=BG)
        lbl(tab, "Patch Notes", font=F_TITLE).pack(pady=(16,4))
        lbl(tab, "What changed in LUL'S RNG and where the game is headed.",
            color=FG2, font=F_LABEL).pack()
        self.upd_scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        self.upd_scroll.pack(fill="both", expand=True, padx=18, pady=10)
        self._render_updates()

    def _render_updates(self):
        for w in self.upd_scroll.winfo_children():
            w.destroy()
        for upd in UPDATES_LOG:
            card = card_frame(self.upd_scroll, border_color="#1d4ed8")
            card.pack(fill="x", pady=6, padx=4)
            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(fill="x", padx=14, pady=12)
            hdr = ctk.CTkFrame(row, fg_color="transparent")
            hdr.pack(fill="x")
            lbl(hdr, f"v{upd['version']}  ·  {upd['title']}", font=F_HEAD, color=GOLD).pack(side="left")
            lbl(hdr, upd["date"], font=F_LABEL, color=FG2).pack(side="right")
            for item in upd["highlights"]:
                lbl(row, f"• {item}", font=F_BODY, color=FG).pack(anchor="w", pady=1)
        next_card = card_frame(self.upd_scroll, border_color=PURPLE)
        next_card.pack(fill="x", pady=(10,6), padx=4)
        r = ctk.CTkFrame(next_card, fg_color="transparent"); r.pack(fill="x", padx=14, pady=12)
        lbl(r, "What's Next", font=F_HEAD, color=PURPLE).pack(anchor="w")
        lbl(r, "• Seasonal events and rotating limited titles", color=FG2).pack(anchor="w")
        lbl(r, "• More endgame Rift tiers and team raids", color=FG2).pack(anchor="w")
        lbl(r, "• Guild systems and social progression", color=FG2).pack(anchor="w")

    def _do_rebirth(self):
        if not self.engine.is_unlocked("rebirth"):
            self._notify(f"Rebirth unlocks at level {UNLOCKS['rebirth']}!", RED); return
        ok, result = self.engine.perform_rebirth()
        if ok:
            self._big_notify("♻️  REBORN\nYour power grows.", PURPLE)
            self._refresh_all()
        else:
            self._notify("Cannot rebirth: " + " | ".join(result), RED)

    def _refresh_rebirth(self):
        self.rb_lock_lbl.configure(
            text="" if self.engine.is_unlocked("rebirth")
            else f"🔒 Rebirth unlocks at Level {UNLOCKS['rebirth']}")
        _, _, cost = self.engine.can_rebirth()
        self.rb_cost_lbl.configure(text=f"• {cost:,} coins required")
        self.rb_count_lbl.configure(text=f"Rebirths completed: {self.engine.state.rebirths}")
        self.rb_points_lbl.configure(text=f"Rebirth Points: {self.engine.state.rebirth_points}")
        ok, reasons, _ = self.engine.can_rebirth()
        self.rb_reasons_lbl.configure(
            text="\n".join(f"  ✗ {r}" for r in reasons) if reasons else "  ✓ Ready to rebirth!")
        self._render_rebirth_upgrades()

    def _render_rebirth_upgrades(self):
        for w in self.rb_upg_frame.winfo_children(): w.destroy()
        for upg in REBIRTH_UPGRADES:
            ok, msg, lvl, cost = self.engine.can_buy_rebirth_upgrade(upg["id"])
            maxed = lvl >= upg["max"]
            card = card_frame(self.rb_upg_frame)
            card.pack(fill="x", pady=4, padx=4)
            row = ctk.CTkFrame(card, fg_color="transparent"); row.pack(fill="x", padx=14, pady=10)
            left = ctk.CTkFrame(row, fg_color="transparent"); left.pack(side="left", fill="x", expand=True)
            lbl(left, upg["name"], font=F_HEAD, color=FG).pack(anchor="w")
            lbl(left, upg["desc"], font=F_LABEL, color=FG2).pack(anchor="w")
            lbl(left, f"Level {lvl}/{upg['max']}", font=F_SMALL, color=PURPLE).pack(anchor="w", pady=(2,0))
            right = ctk.CTkFrame(row, fg_color="transparent"); right.pack(side="right")
            if maxed:
                lbl(right, "MAXED", color=GREEN, font=F_LABEL).pack(pady=(4,2))
            else:
                lbl(right, f"Cost: {cost} RP", color=BLUE, font=F_LABEL).pack(pady=(4,2))
            btn = pill_btn(
                right, "Upgrade" if not maxed else "Done",
                lambda uid=upg["id"]: self._buy_rebirth_upgrade(uid),
                fg="#1f2937" if not maxed else "#14532d",
                hover="#111827" if not maxed else "#166534",
                w=110, h=32)
            btn.pack()
            if maxed or (not ok and "Need" in msg):
                btn.configure(state="disabled")

    def _buy_rebirth_upgrade(self, upg_id: str):
        ok, msg = self.engine.buy_rebirth_upgrade(upg_id)
        self._notify(msg, GREEN if ok else RED)
        if ok:
            if upg_id == "auto_roll":
                self.auto_roll_switch.configure(state="normal")
            self._refresh_rebirth()
            self._refresh_roll_info()

    # ══════════════════════════════════════════════════════════════════════════
    #  NOTIFICATIONS
    # ══════════════════════════════════════════════════════════════════════════
    def _notify(self, msg: str, color=GREEN):
        try:
            b = ctk.CTkFrame(self, fg_color=CARD, corner_radius=24,
                              border_width=1, border_color=color)
            ctk.CTkLabel(b, text=msg, font=F_SMALL, text_color=color).pack(padx=18, pady=10)
            b.place(relx=0.5, rely=0.97, anchor="s")
            def slide(step):
                if not b.winfo_exists(): return
                b.place(relx=0.5, rely=0.97-step*0.003, anchor="s")
                if step < 8: self.after(20, lambda: slide(step+1))
            slide(0)
            self.after(2600, lambda: b.destroy() if b.winfo_exists() else None)
        except: pass

    def _big_notify(self, msg: str, color: str):
        try:
            p = ctk.CTkFrame(self, fg_color=CARD, corner_radius=24,
                              border_width=2, border_color=color)
            ctk.CTkLabel(p, text=msg, font=(_FONT, 22, "bold"),
                         text_color=color, justify="center").pack(padx=52, pady=36)
            p.place(relx=0.5, rely=0.5, anchor="center")
            self.after(3400, lambda: p.destroy() if p.winfo_exists() else None)
        except: pass

    def _is_tab_unlocked(self, tab_name: str) -> bool:
        lvl = self.engine.state.level if self.engine else 1
        req = TAB_UNLOCK_LEVELS.get(tab_name, 1)
        return lvl >= req

    def _next_locked_level(self) -> Optional[int]:
        lvl = self.engine.state.level if self.engine else 1
        locked_levels = sorted({req for req in TAB_UNLOCK_LEVELS.values() if req > lvl})
        return locked_levels[0] if locked_levels else None

    def _update_tab_access(self, announce=False):
        if not hasattr(self, "tabs") or not self.engine:
            return
        lvl = self.engine.state.level
        next_lvl = self._next_locked_level()

        if announce and lvl > self._last_unlock_level_checked:
            newly = [t for t, req in TAB_UNLOCK_LEVELS.items()
                     if self._last_unlock_level_checked < req <= lvl]
            for t in sorted(newly, key=lambda x: TAB_UNLOCK_LEVELS.get(x, 1)):
                self._notify(f"🔓 Unlocked: {t}", GREEN)
            self._last_unlock_level_checked = lvl

        sb = getattr(self.tabs, "_segmented_button", None)
        buttons = getattr(sb, "_buttons_dict", {}) if sb else {}
        for t, req in TAB_UNLOCK_LEVELS.items():
            btn = buttons.get(t)
            if not btn:
                continue
            if lvl >= req:
                btn.configure(text_color=FG, hover_color="#162032")
            elif next_lvl is not None and req == next_lvl:
                btn.configure(text_color="#7f8aa3", hover_color="#1a2333")
            else:
                btn.configure(text_color="#556079", hover_color="#111827")

        current = self.tabs.get()
        if self._is_tab_unlocked(current):
            self._last_open_tab = current
        else:
            try:
                self.tabs.set(self._last_open_tab if self._is_tab_unlocked(self._last_open_tab) else "🎲 Roll")
            except Exception:
                pass

    def _on_tab_selected(self, *_):
        if not hasattr(self, "tabs") or not self.engine:
            return
        current = self.tabs.get()
        if self._is_tab_unlocked(current):
            self._last_open_tab = current
            return
        req = TAB_UNLOCK_LEVELS.get(current, 1)
        self._notify(f"{current} opens at level {req}.", RED)
        try:
            self.tabs.set(self._last_open_tab if self._is_tab_unlocked(self._last_open_tab) else "🎲 Roll")
        except Exception:
            pass

    # ══════════════════════════════════════════════════════════════════════════
    #  GLOBAL REFRESH
    # ══════════════════════════════════════════════════════════════════════════
    def _refresh_top_bar(self):
        s = self.engine.state; xp, need = s.xp, xp_for_level(s.level)
        self.lbl_level.configure(text=f"LV {s.level}")
        self.lbl_coins.configure(text=f"🪙 {s.coins:,}")
        self.lbl_shards.configure(text=f"💎 {s.shards}")
        self.lbl_tokens.configure(text=f"🔑 {s.boss_tokens}")
        if s.lucky_rolls_remaining > 0:
            lk = f"Aura ×{s.lucky_rolls_remaining}"
        elif s.lucky_rolls > 0:
            lk = f"Aura Bank {s.lucky_rolls}"
        else:
            lk = "Aura None"
        self.lbl_lucky.configure(text=lk)
        self.xp_bar.set(xp / max(need, 1))
        self._update_tab_access(announce=True)

    def _refresh_roll_info(self):
        s = self.engine.state
        self.lbl_pity.configure(text=f"PITY  {s.pity_counter}")
        self.lbl_rolls.configure(text=f"ROLLS  {s.total_rolls:,}")
        at = s.auto_roll_target or "Legendary"
        if hasattr(self, "auto_target_menu"):
            try: self.auto_target_menu.set(at)
            except: pass
        if hasattr(self, "auto_roll_switch"):
            if self.engine._upg("auto_roll") > 0:
                self.auto_roll_switch.configure(state="normal")
                if s.auto_roll_enabled: self.auto_roll_switch.select()
                else: self.auto_roll_switch.deselect()
            else:
                self.auto_roll_switch.deselect()
                self.auto_roll_switch.configure(state="disabled")
        if s.auto_roll_enabled and self.engine._upg("auto_roll") > 0:
            self.lbl_auto.configure(text=f"AUTO  ON → {at}", text_color=BLUE)
        elif self.engine._upg("auto_roll") > 0:
            self.lbl_auto.configure(text=f"AUTO  OFF → {at}", text_color=FG2)
        else:
            self.lbl_auto.configure(text="AUTO  LOCKED", text_color=RED)

    def _check_daily_launch(self):
        ok, result = self.engine.claim_daily()
        if ok:
            c, s, _ = result
            self._notify(f"🎁 Daily reward!  +{c:,}🪙  +{s}💎", GREEN)
            self._refresh_top_bar()

    def _quick_daily_claim(self):
        self._claim_daily()

    def _quick_sync(self):
        self._refresh_all()
        self._notify("Synced game panels.", BLUE)

    def _tick_live_status(self):
        if not hasattr(self, "live_status_lbl"):
            return
        self._live_tick_n += 1
        # Rotate tip every 8 seconds while keeping key progression always visible.
        if self._live_tick_n % 8 == 0:
            self._live_tip_idx = (self._live_tip_idx + 1) % len(LIVE_TIPS)
        s = self.engine.state if self.engine else PlayerState()
        cloud = "Cloud: Online" if self.db.conn else "Cloud: Offline"
        status = (
            f"Live: Lv.{s.level} · Rebirths {s.rebirths} · Essence {s.void_essence} · {cloud}  |  "
            f"{LIVE_TIPS[self._live_tip_idx]}"
        )
        self.live_status_lbl.configure(text=status)

    def _refresh_all(self):
        self._refresh_top_bar(); self._refresh_roll_info()
        self._refresh_inventory(); self._refresh_arena(); self._refresh_boss()
        self._refresh_craft(); self._refresh_collection()
        self._refresh_stats(); self._refresh_rebirth(); self._refresh_endgame()
        self._render_updates() if hasattr(self, "upd_scroll") else None
        self._refresh_pvp_titles()
        self._refresh_leaderboard()
        self._refresh_online()
        self._refresh_pvp()
        self._refresh_roll_friends_async()
        self._tick_live_status()

    def _final_sync(self):
        try:
            if not self.engine:
                return True, ""
            # Always persist local first.
            self.engine.save_game()
            # If playing online, perform one final cloud write and report failures.
            if self.engine.username:
                if not self.db.conn:
                    self.db.reconnect_if_needed(force=True)
                if not self.db.conn:
                    return False, "Cloud sync unavailable (offline). Local save was kept."
                ok = self.db.save_player(self.engine.username, self.engine.state)
                if not ok:
                    return False, "Cloud sync failed on close. Local save was kept."
            return True, ""
        except Exception:
            return False, "Unexpected save error on close. Local save was kept."

    def _on_close(self):
        self._is_closing = True
        ok, msg = self._final_sync()
        if not ok:
            try:
                messagebox.showwarning("Save Warning", msg)
            except Exception:
                print(f"[WARN] {msg}")
        self.destroy()


# ══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    app = LulsRNG()
    app.mainloop()
