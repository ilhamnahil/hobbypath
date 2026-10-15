"""SQLite persistence for hobbies, plan tasks and practice sessions."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS hobbies (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT    NOT NULL,
    goal          TEXT    NOT NULL,
    level         TEXT    NOT NULL,
    hours_per_week REAL   NOT NULL,
    weeks         INTEGER NOT NULL,
    summary       TEXT    DEFAULT '',
    source        TEXT    DEFAULT 'offline',
    created_at    TEXT    NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    hobby_id    INTEGER NOT NULL REFERENCES hobbies(id) ON DELETE CASCADE,
    week        INTEGER NOT NULL,
    title       TEXT    NOT NULL,
    details     TEXT    DEFAULT '',
    minutes     INTEGER DEFAULT 0,
    is_milestone INTEGER DEFAULT 0,
    done        INTEGER DEFAULT 0,
    done_at     TEXT
);
CREATE TABLE IF NOT EXISTS sessions (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    hobby_id  INTEGER NOT NULL REFERENCES hobbies(id) ON DELETE CASCADE,
    day       TEXT    NOT NULL,
    minutes   INTEGER NOT NULL,
    note      TEXT    DEFAULT ''
);
"""


class Store:
    def __init__(self, path: str | Path = "hobbypath.db"):
        self.path = str(path)
        with self._conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ---- hobbies ---------------------------------------------------------
    def add_hobby(self, name: str, goal: str, level: str, hours_per_week: float,
                  weeks: int, plan: dict, source: str = "offline") -> int:
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO hobbies (name, goal, level, hours_per_week, weeks, summary, source, created_at)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (name, goal, level, hours_per_week, weeks, plan.get("summary", ""), source,
                 datetime.now().isoformat(timespec="seconds")),
            )
            hobby_id = cur.lastrowid
            for wk in plan["weeks"]:
                for t in wk["tasks"]:
                    c.execute(
                        "INSERT INTO tasks (hobby_id, week, title, details, minutes, is_milestone)"
                        " VALUES (?,?,?,?,?,?)",
                        (hobby_id, wk["week"], t["title"], t.get("details", ""),
                         int(t.get("minutes", 0)), int(bool(t.get("milestone", False)))),
                    )
            return hobby_id

    def hobbies(self) -> list[sqlite3.Row]:
        with self._conn() as c:
            return c.execute("SELECT * FROM hobbies ORDER BY created_at DESC").fetchall()

    def hobby(self, hobby_id: int) -> sqlite3.Row | None:
        with self._conn() as c:
            return c.execute("SELECT * FROM hobbies WHERE id=?", (hobby_id,)).fetchone()

    def delete_hobby(self, hobby_id: int) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM hobbies WHERE id=?", (hobby_id,))

    # ---- tasks -----------------------------------------------------------
    def tasks(self, hobby_id: int) -> list[sqlite3.Row]:
        with self._conn() as c:
            return c.execute("SELECT * FROM tasks WHERE hobby_id=? ORDER BY week, id",
                             (hobby_id,)).fetchall()

    def set_task_done(self, task_id: int, done: bool) -> None:
        with self._conn() as c:
            c.execute("UPDATE tasks SET done=?, done_at=? WHERE id=?",
                      (int(done), date.today().isoformat() if done else None, task_id))

    # ---- sessions --------------------------------------------------------
    def log_session(self, hobby_id: int, day: date, minutes: int, note: str = "") -> None:
        with self._conn() as c:
            c.execute("INSERT INTO sessions (hobby_id, day, minutes, note) VALUES (?,?,?,?)",
                      (hobby_id, day.isoformat(), int(minutes), note))

    def sessions(self, hobby_id: int) -> list[sqlite3.Row]:
        with self._conn() as c:
            return c.execute("SELECT * FROM sessions WHERE hobby_id=? ORDER BY day DESC, id DESC",
                             (hobby_id,)).fetchall()
