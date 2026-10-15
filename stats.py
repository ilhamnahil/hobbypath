"""Progress, streak and milestone calculations (pure functions, easy to test)."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Iterable


def current_streak(practice_days: Iterable[date], today: date | None = None) -> int:
    """Consecutive days with practice, ending today (or yesterday, so a streak
    isn't 'lost' before you've had the chance to practise today)."""
    today = today or date.today()
    days = set(practice_days)
    start = today if today in days else today - timedelta(days=1)
    streak = 0
    while start in days:
        streak += 1
        start -= timedelta(days=1)
    return streak


def longest_streak(practice_days: Iterable[date]) -> int:
    days = sorted(set(practice_days))
    best = run = 0
    prev = None
    for d in days:
        run = run + 1 if prev and d - prev == timedelta(days=1) else 1
        best = max(best, run)
        prev = d
    return best


def completion(tasks: list[dict]) -> float:
    if not tasks:
        return 0.0
    return sum(1 for t in tasks if t["done"]) / len(tasks)


def current_week(tasks: list[dict]) -> int:
    """First week that still has an open task (the week you're 'in')."""
    open_weeks = [t["week"] for t in tasks if not t["done"]]
    if open_weeks:
        return min(open_weeks)
    return max((t["week"] for t in tasks), default=1)


def minutes_per_week(sessions: list[dict], start: date) -> dict[int, int]:
    """Total practice minutes keyed by plan week (1-based) since `start`."""
    out: dict[int, int] = defaultdict(int)
    for s in sessions:
        d = s["day"] if isinstance(s["day"], date) else date.fromisoformat(s["day"])
        wk = max(1, (d - start).days // 7 + 1)
        out[wk] += int(s["minutes"])
    return dict(out)


BADGES = [
    (1, "🌱 First step"),
    (3, "🔥 3-day streak"),
    (7, "⭐ One full week"),
    (14, "🏅 Two-week habit"),
    (30, "🏆 30-day legend"),
]


def earned_badges(longest: int) -> list[str]:
    return [label for need, label in BADGES if longest >= need]
