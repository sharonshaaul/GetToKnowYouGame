"""SQLite-backed shared room state for multi-phone play."""

from __future__ import annotations

import random
import sqlite3
import string
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from questions import QUESTIONS, fill_question

DB_PATH = Path(__file__).resolve().parent / "game.db"


@contextmanager
def connect():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS rooms (
                code TEXT PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'lobby',
                answerer TEXT,
                subject TEXT,
                question TEXT,
                question_index INTEGER NOT NULL DEFAULT 0,
                used_indices TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_code TEXT NOT NULL,
                name TEXT NOT NULL,
                joined_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(room_code, name),
                FOREIGN KEY (room_code) REFERENCES rooms(code) ON DELETE CASCADE
            );
            """
        )


def _code(n: int = 4) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(random.choices(alphabet, k=n))


def create_room() -> str:
    init_db()
    with connect() as conn:
        for _ in range(20):
            code = _code()
            try:
                conn.execute("INSERT INTO rooms (code, status) VALUES (?, 'lobby')", (code,))
                return code
            except sqlite3.IntegrityError:
                continue
    raise RuntimeError("לא הצלחנו ליצור קוד חדר")


def room_exists(code: str) -> bool:
    init_db()
    with connect() as conn:
        row = conn.execute("SELECT 1 FROM rooms WHERE code = ?", (code.upper(),)).fetchone()
        return row is not None


def get_room(code: str) -> dict[str, Any] | None:
    init_db()
    with connect() as conn:
        row = conn.execute("SELECT * FROM rooms WHERE code = ?", (code.upper(),)).fetchone()
        return dict(row) if row else None


def list_players(code: str) -> list[str]:
    init_db()
    with connect() as conn:
        rows = conn.execute(
            "SELECT name FROM players WHERE room_code = ? ORDER BY joined_at, id",
            (code.upper(),),
        ).fetchall()
        return [r["name"] for r in rows]


def add_player(code: str, name: str) -> tuple[bool, str]:
    init_db()
    name = name.strip()
    if not name:
        return False, "נא להזין שם"
    if len(name) > 40:
        return False, "השם ארוך מדי"
    code = code.upper().strip()
    room = get_room(code)
    if not room:
        return False, "החדר לא נמצא"
    if room["status"] == "ended":
        return False, "המשחק כבר הסתיים"
    with connect() as conn:
        try:
            conn.execute(
                "INSERT INTO players (room_code, name) VALUES (?, ?)",
                (code, name),
            )
        except sqlite3.IntegrityError:
            return True, "כבר מחוברים"
    return True, "הצטרפת בהצלחה"


def _parse_used(used: str) -> set[int]:
    if not used.strip():
        return set()
    return {int(x) for x in used.split(",") if x.strip().isdigit()}


def _serialize_used(used: set[int]) -> str:
    return ",".join(str(i) for i in sorted(used))


def start_or_next_round(code: str) -> tuple[bool, str]:
    """Start game or advance to next question. Needs at least 2 players."""
    init_db()
    code = code.upper()
    room = get_room(code)
    if not room:
        return False, "החדר לא נמצא"
    players = list_players(code)
    if len(players) < 2:
        return False, "צריך לפחות שני שחקנים"

    used = _parse_used(room["used_indices"] or "")
    available = [i for i in range(len(QUESTIONS)) if i not in used]
    if not available:
        used = set()
        available = list(range(len(QUESTIONS)))

    q_idx = random.choice(available)
    used.add(q_idx)
    answerer = random.choice(players)
    others = [p for p in players if p != answerer]
    subject = random.choice(others)
    question = fill_question(QUESTIONS[q_idx], subject)

    with connect() as conn:
        conn.execute(
            """
            UPDATE rooms
            SET status = 'playing',
                answerer = ?,
                subject = ?,
                question = ?,
                question_index = ?,
                used_indices = ?
            WHERE code = ?
            """,
            (answerer, subject, question, q_idx, _serialize_used(used), code),
        )
    return True, "ok"


def end_game(code: str) -> None:
    init_db()
    with connect() as conn:
        conn.execute(
            "UPDATE rooms SET status = 'ended' WHERE code = ?",
            (code.upper(),),
        )


def back_to_lobby(code: str) -> None:
    init_db()
    with connect() as conn:
        conn.execute(
            """
            UPDATE rooms
            SET status = 'lobby',
                answerer = NULL,
                subject = NULL,
                question = NULL,
                question_index = 0,
                used_indices = ''
            WHERE code = ?
            """,
            (code.upper(),),
        )
