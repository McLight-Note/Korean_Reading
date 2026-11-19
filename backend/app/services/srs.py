"""Spaced repetition (SM-2 style), pure and deterministic.

A card state is {"ease", "interval", "reps", "lapses", "due", "last"}; dates are ISO 'YYYY-MM-DD' strings and
`today` is passed in, so the function has no hidden clock and is trivially testable. Grades:
0 = again, 1 = hard, 2 = good, 3 = easy.
"""
from __future__ import annotations

from datetime import date, timedelta

MIN_EASE = 1.3
GRADES = {0: "again", 1: "hard", 2: "good", 3: "easy"}


def new_state(today: str) -> dict:
    return {"ease": 2.5, "interval": 0, "reps": 0, "lapses": 0, "due": today, "last": None}


def schedule(state: dict | None, grade: int, today: str) -> dict:
    if grade not in GRADES:
        raise ValueError("grade must be 0..3")
    s = {**new_state(today), **{k: v for k, v in (state or {}).items() if v is not None}}      # tolerate partial states
    ease, interval, reps, lapses = float(s["ease"]), int(s["interval"]), int(s["reps"]), int(s["lapses"])
    if grade == 0:                                   # again: relearn; shown again today
        if reps > 0:
            lapses += 1
        reps, interval = 0, 0
        ease = max(MIN_EASE, ease - 0.2)
    elif grade == 1:                                 # hard
        interval = 1 if reps == 0 else max(interval + 1, round(interval * 1.2))
        ease = max(MIN_EASE, ease - 0.15)
        reps += 1
    elif grade == 2:                                 # good
        interval = 1 if reps == 0 else 3 if reps == 1 else max(interval + 1, round(interval * ease))
        reps += 1
    else:                                            # easy
        interval = 3 if reps == 0 else max(interval + 2, round(interval * ease * 1.3))
        ease += 0.15
        reps += 1
    due = date.fromisoformat(today) + timedelta(days=interval)
    return {"ease": round(ease, 3), "interval": interval, "reps": reps, "lapses": lapses, "due": due.isoformat(), "last": today}


def is_due(state: dict, today: str) -> bool:
    return state["due"] <= today
