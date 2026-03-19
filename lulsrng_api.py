"""
LUL'S RNG HTTPS API (Render-ready)

This backend exposes a small RPC API over HTTPS so school networks that block
direct Postgres traffic can still use online features through normal web (443).
"""

import json
import os
import threading
import time
import hashlib
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from typing import Optional
from urllib.parse import urlparse, urlunparse

import psycopg2
import psycopg2.extras
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse


DB_URL = os.getenv("LULSRNG_DB_URL", "").strip()
API_TOKEN = os.getenv("LULSRNG_API_TOKEN", "").strip()


def hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


@dataclass
class PlayerState:
    level: int = 1
    xp: int = 0
    coins: int = 100
    shards: int = 0
    boss_tokens: int = 0
    rebirths: int = 0
    luck_multiplier: float = 1.0
    total_rolls: int = 0
    pity_counter: int = 0
    lucky_rolls: int = 0
    lucky_rolls_remaining: int = 0
    inventory: dict = field(default_factory=dict)
    equipped_title: Optional[str] = None
    equipped_rarity: Optional[str] = None
    battle_titles: list = field(default_factory=list)
    achievements: list = field(default_factory=list)
    collection: list = field(default_factory=list)
    free_merge: bool = False
    last_daily: str = ""
    total_wins: int = 0
    total_losses: int = 0
    total_boss_wins: int = 0
    total_merges: int = 0
    total_crafts: int = 0
    highest_rarity_pulled: str = "Common"
    cooldowns: dict = field(default_factory=dict)
    pvp_wins: int = 0
    pvp_losses: int = 0
    rebirth_points: int = 0
    rebirth_upgrades: dict = field(default_factory=dict)
    auto_roll_enabled: bool = False
    auto_roll_target: str = "Legendary"
    title_trades_completed: int = 0
    void_essence: int = 0
    total_rift_wins: int = 0

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            return cls()
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class Database:
    def __init__(self):
        self.conn = None
        self.lock = threading.Lock()
        self.last_error = ""
        self._next_reconnect_at = 0.0
        self._reconnect_backoff = 3.0
        self._connect()
        if self.conn:
            self._create_tables()

    def _candidate_dsns(self):
        seen = set()
        out = []
        for dsn in [DB_URL, os.getenv("LULSRNG_DB_URL_FALLBACK", "").strip()]:
            if not dsn or dsn in seen:
                continue
            seen.add(dsn)
            out.append(dsn)
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
                    dsn443 = urlunparse((
                        p.scheme,
                        f"{auth}{host}:443",
                        p.path,
                        p.params,
                        p.query,
                        p.fragment,
                    ))
                    if dsn443 not in seen:
                        seen.add(dsn443)
                        out.append(dsn443)
            except Exception:
                pass
        return out

    def _connect(self):
        if not DB_URL:
            self.last_error = "LULSRNG_DB_URL missing"
            self.conn = None
            return False
        errs = []
        for dsn in self._candidate_dsns():
            try:
                self.conn = psycopg2.connect(
                    dsn,
                    connect_timeout=8,
                    keepalives=1,
                    keepalives_idle=30,
                    keepalives_interval=10,
                    keepalives_count=3,
                    application_name="luls_rng_api",
                )
                self.conn.autocommit = False
                self.last_error = ""
                self._reconnect_backoff = 3.0
                self._next_reconnect_at = 0.0
                print("[API] Connected to Neon")
                return True
            except Exception as e:
                errs.append(str(e))
        self.conn = None
        self.last_error = errs[0] if errs else "Unknown DB error"
        print(f"[API] DB connection failed: {self.last_error}")
        return False

    def reconnect_if_needed(self, force=False):
        if self.conn and not force:
            return True
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
                self.last_error = str(e)
                try:
                    self.conn.rollback()
                except Exception:
                    pass
                if "connection" in str(e).lower() or "closed" in str(e).lower():
                    self.conn = None
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

    def register(self, username: str, password: str):
        if not self.conn:
            self.reconnect_if_needed(force=True)
        if not self.conn:
            return True, "offline"
        existing = self._exec("SELECT username FROM players WHERE username=%s", (username,), fetch="one")
        if existing:
            return False, "Username already taken"
        ph = hash_password(password)
        ok = self._exec(
            "INSERT INTO players(username,password_h,data) VALUES(%s,%s,%s)",
            (username, ph, json.dumps(PlayerState().to_dict()))
        )
        return (True, "ok") if ok else (False, "DB error")

    def login(self, username: str, password: str):
        if not self.conn:
            self.reconnect_if_needed(force=True)
        if not self.conn:
            return True, None
        ph = hash_password(password)
        row = self._exec("SELECT data,password_h FROM players WHERE username=%s", (username,), fetch="one")
        if not row:
            return False, "Username not found"
        if row["password_h"] != ph:
            return False, "Wrong password"
        return True, PlayerState.from_dict(row["data"])

    def save_player(self, username: str, state):
        if not self.conn or not username:
            return False
        if isinstance(state, dict):
            state = PlayerState.from_dict(state)
        elif not isinstance(state, PlayerState):
            state = PlayerState()
        ok = self._exec(
            "UPDATE players SET data=%s, last_seen=NOW() WHERE username=%s",
            (json.dumps(state.to_dict()), username)
        )
        return bool(ok)

    def get_leaderboard(self):
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
                   ) AS score,
                   last_seen
            FROM players
            ORDER BY score DESC, (data->>'total_rolls')::int DESC
            LIMIT 50
        """, fetch="all")
        return rows or []

    def post_roll(self, username: str, title: str, rarity: str):
        self._exec(
            "INSERT INTO global_rolls(username,title,rarity) VALUES(%s,%s,%s)",
            (username, title, rarity)
        )
        self._exec(
            "DELETE FROM global_rolls WHERE id NOT IN "
            "(SELECT id FROM global_rolls ORDER BY rolled_at DESC LIMIT 200)"
        )
        return True

    def get_recent_rolls(self):
        rows = self._exec(
            "SELECT username,title,rarity,rolled_at FROM global_rolls ORDER BY rolled_at DESC LIMIT 30",
            fetch="all"
        )
        return rows or []

    def get_online_players(self):
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

    def get_player_profile(self, username: str):
        row = self._exec("SELECT username, data FROM players WHERE username=%s", (username,), fetch="one")
        if not row:
            return None
        return {"username": row["username"], "data": row["data"]}

    def send_battle_request(self, challenger: str, defender: str, wager_coins: int, wager_shards: int):
        if not challenger or not defender:
            return False, "Invalid challenger/defender."
        if challenger == defender:
            return False, "Cannot battle yourself."
        wager_coins = max(0, int(wager_coins or 0))
        wager_shards = max(0, int(wager_shards or 0))

        # Hard anti-spam guardrail: one request every 5 seconds per challenger.
        recent = self._exec(
            "SELECT id FROM battle_requests WHERE challenger=%s "
            "AND created_at > NOW() - INTERVAL '5 seconds' "
            "ORDER BY created_at DESC LIMIT 1",
            (challenger,), fetch="one"
        )
        if recent:
            return False, "You're sending battle requests too fast. Wait a few seconds."

        # Keep queue bounded to avoid inbox spam.
        pending_total = self._exec(
            "SELECT COUNT(*)::int AS c FROM battle_requests WHERE challenger=%s AND status='pending'",
            (challenger,), fetch="one"
        )
        if pending_total and int(pending_total.get("c", 0) or 0) >= 5:
            return False, "Too many pending requests. Wait for responses first."

        # Avoid duplicate or mirrored pending battles for the same pair.
        pair_pending = self._exec(
            "SELECT id FROM battle_requests "
            "WHERE status='pending' AND ((challenger=%s AND defender=%s) OR (challenger=%s AND defender=%s)) "
            "LIMIT 1",
            (challenger, defender, defender, challenger), fetch="one"
        )
        if pair_pending:
            return False, "A pending battle already exists between these players."

        existing = self._exec(
            "SELECT id FROM battle_requests WHERE challenger=%s AND defender=%s AND status='pending'",
            (challenger, defender), fetch="one"
        )
        if existing:
            return False, "Already sent a request to this player"
        ok = self._exec(
            "INSERT INTO battle_requests(challenger,defender,wager_coins,wager_shards) VALUES(%s,%s,%s,%s)",
            (challenger, defender, wager_coins, wager_shards)
        )
        return (True, "Battle request sent!") if ok else (False, "DB error")

    def get_pending_requests(self, username: str):
        rows = self._exec(
            "SELECT id,challenger,defender,wager_coins,wager_shards,created_at "
            "FROM battle_requests WHERE defender=%s AND status='pending' ORDER BY created_at DESC",
            (username,), fetch="all"
        )
        return rows or []

    def get_sent_requests(self, username: str):
        rows = self._exec(
            "SELECT id,challenger,defender,wager_coins,wager_shards,status,result,created_at "
            "FROM battle_requests WHERE challenger=%s ORDER BY created_at DESC LIMIT 20",
            (username,), fetch="all"
        )
        return rows or []

    def decline_request(self, request_id: int):
        self._exec("UPDATE battle_requests SET status='declined' WHERE id=%s", (request_id,))
        return True

    def resolve_battle(self, request_id: int, result: dict, winner: str):
        self._exec(
            "UPDATE battle_requests SET status='resolved', result=%s WHERE id=%s",
            (json.dumps(result), request_id)
        )
        return True

    def get_active_boss_race(self):
        row = self._exec(
            "SELECT * FROM boss_race_events WHERE active=TRUE AND ends_at > NOW() "
            "ORDER BY started_at DESC LIMIT 1",
            fetch="one"
        )
        return dict(row) if row else None

    def claim_boss_race(self, event_id: int, username: str):
        self._exec(
            "UPDATE boss_race_events SET winner=%s, active=FALSE WHERE id=%s AND winner IS NULL",
            (username, event_id)
        )
        return True

    def _norm_pair(self, a: str, b: str):
        return (a, b) if a < b else (b, a)

    def are_friends(self, user1: str, user2: str):
        a, b = self._norm_pair(user1, user2)
        row = self._exec("SELECT 1 FROM friends WHERE user_a=%s AND user_b=%s", (a, b), fetch="one")
        return bool(row)

    def send_trade_request(self, sender: str, receiver: str, offered_title: str, offered_count: int, requested_title: str, requested_count: int):
        if sender == receiver:
            return False, "Can't trade with yourself"
        if not self.are_friends(sender, receiver):
            return False, "Trading is friends-only. Add each other first."
        existing = self._exec(
            "SELECT id FROM title_trades WHERE sender=%s AND receiver=%s AND status='pending' "
            "AND offered_title=%s AND requested_title=%s",
            (sender, receiver, offered_title, requested_title), fetch="one"
        )
        if existing:
            return False, "Similar pending trade already exists"
        ok = self._exec(
            "INSERT INTO title_trades(sender,receiver,offered_title,offered_count,requested_title,requested_count) "
            "VALUES(%s,%s,%s,%s,%s,%s)",
            (sender, receiver, offered_title, offered_count, requested_title, requested_count)
        )
        return (True, "Trade request sent!") if ok else (False, "DB error")

    def get_incoming_trades(self, username: str):
        rows = self._exec(
            "SELECT * FROM title_trades WHERE receiver=%s AND status='pending' ORDER BY created_at DESC LIMIT 25",
            (username,), fetch="all"
        )
        return rows or []

    def get_outgoing_trades(self, username: str):
        rows = self._exec(
            "SELECT * FROM title_trades WHERE sender=%s ORDER BY created_at DESC LIMIT 25",
            (username,), fetch="all"
        )
        return rows or []

    def decline_trade(self, trade_id: int):
        self._exec("UPDATE title_trades SET status='declined' WHERE id=%s AND status='pending'", (trade_id,))
        return True

    def resolve_trade(self, trade_id: int):
        self._exec("UPDATE title_trades SET status='resolved' WHERE id=%s AND status='pending'", (trade_id,))
        return True

    def send_friend_request(self, sender: str, receiver: str):
        if sender == receiver:
            return False, "Can't add yourself"
        if self.are_friends(sender, receiver):
            return False, "Already friends"
        existing = self._exec(
            "SELECT id FROM friend_requests WHERE sender=%s AND receiver=%s AND status='pending'",
            (sender, receiver), fetch="one"
        )
        if existing:
            return False, "Friend request already sent"
        reverse = self._exec(
            "SELECT id FROM friend_requests WHERE sender=%s AND receiver=%s AND status='pending'",
            (receiver, sender), fetch="one"
        )
        if reverse:
            a, b = self._norm_pair(sender, receiver)
            self._exec("INSERT INTO friends(user_a,user_b) VALUES(%s,%s) ON CONFLICT DO NOTHING", (a, b))
            self._exec("UPDATE friend_requests SET status='accepted' WHERE id=%s", (reverse["id"],))
            return True, "Friend request auto-accepted!"
        ok = self._exec("INSERT INTO friend_requests(sender,receiver) VALUES(%s,%s)", (sender, receiver))
        return (True, "Friend request sent!") if ok else (False, "DB error")

    def get_incoming_friend_requests(self, username: str):
        rows = self._exec(
            "SELECT * FROM friend_requests WHERE receiver=%s AND status='pending' ORDER BY created_at DESC LIMIT 25",
            (username,), fetch="all"
        )
        return rows or []

    def get_outgoing_friend_requests(self, username: str):
        rows = self._exec(
            "SELECT * FROM friend_requests WHERE sender=%s AND status='pending' ORDER BY created_at DESC LIMIT 25",
            (username,), fetch="all"
        )
        return rows or []

    def accept_friend_request(self, req_id: int):
        row = self._exec(
            "SELECT sender,receiver FROM friend_requests WHERE id=%s AND status='pending'",
            (req_id,), fetch="one"
        )
        if not row:
            return False
        a, b = self._norm_pair(row["sender"], row["receiver"])
        ok1 = self._exec("INSERT INTO friends(user_a,user_b) VALUES(%s,%s) ON CONFLICT DO NOTHING", (a, b))
        ok2 = self._exec("UPDATE friend_requests SET status='accepted' WHERE id=%s", (req_id,))
        return bool(ok1 and ok2)

    def decline_friend_request(self, req_id: int):
        self._exec("UPDATE friend_requests SET status='declined' WHERE id=%s AND status='pending'", (req_id,))
        return True

    def get_friends(self, username: str):
        rows = self._exec(
            "SELECT CASE WHEN user_a=%s THEN user_b ELSE user_a END AS friend "
            "FROM friends WHERE user_a=%s OR user_b=%s ORDER BY friend ASC",
            (username, username, username), fetch="all"
        )
        return [r["friend"] for r in (rows or [])]


def _encode(obj):
    if isinstance(obj, PlayerState):
        return {"__player_state__": obj.to_dict()}
    if isinstance(obj, dict):
        return {k: _encode(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_encode(v) for v in obj]
    if isinstance(obj, tuple):
        return [_encode(v) for v in obj]
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    return obj


def _decode(obj):
    if isinstance(obj, dict):
        if "__player_state__" in obj:
            return PlayerState.from_dict(obj["__player_state__"])
        return {k: _decode(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_decode(v) for v in obj]
    return obj


ALLOWED_METHODS = {
    "register", "login", "save_player",
    "get_leaderboard",
    "post_roll", "get_recent_rolls",
    "get_online_players",
    "get_player_profile",
    "send_battle_request", "get_pending_requests", "get_sent_requests", "decline_request", "resolve_battle",
    "get_active_boss_race", "claim_boss_race",
    "send_trade_request", "get_incoming_trades", "get_outgoing_trades", "decline_trade", "resolve_trade",
    "are_friends", "send_friend_request", "get_incoming_friend_requests", "get_outgoing_friend_requests",
    "accept_friend_request", "decline_friend_request", "get_friends",
}

DB = Database()
app = FastAPI(title="LUL'S RNG API", version="1.1.2")


def _require_token(req: Request):
    if not API_TOKEN:
        return
    if req.headers.get("X-API-Token", "") != API_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.get("/health")
def health(req: Request):
    _require_token(req)
    DB.reconnect_if_needed()
    return {"ok": True, "db_connected": bool(DB.conn), "db_error": DB.last_error}


@app.post("/rpc")
async def rpc(req: Request):
    _require_token(req)
    payload = await req.json()
    method = str(payload.get("method", "")).strip()
    args = _decode(payload.get("args", []))
    kwargs = _decode(payload.get("kwargs", {}))
    if method not in ALLOWED_METHODS:
        return JSONResponse({"ok": False, "error": f"Method not allowed: {method}"}, status_code=400)
    fn = getattr(DB, method, None)
    if not callable(fn):
        return JSONResponse({"ok": False, "error": f"Unknown method: {method}"}, status_code=400)
    try:
        result = fn(*args, **kwargs)
        return {"ok": True, "result": _encode(result)}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
