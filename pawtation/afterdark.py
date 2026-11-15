"""After Dark: the opt-in 18+ content tier (docs/SPEC_V2.md section 4).

Off by default. Unlocking takes a date of birth ONCE, checks it against today's date, and stores only
`state["afterdark"] = {"unlocked": True, "confirmed_on": "YYYY-MM-DD"}`. The birth date itself is never
stored, logged, printed or put into a message: nothing in this module keeps a reference to it.

Everything that serves content asks `is_unlocked(state)`; when it says no, After Dark files are not even read
(see pawtation/cast.py). This module imports nothing from the rest of the app.
"""
from __future__ import annotations

import datetime
import re

ADULT_AGE = 18
MAX_AGE = 120                      # older than this is a typo, not a birthday
LOCKED = {"unlocked": False}

_FORMATS = (
    (re.compile(r"^([0-9]{4})-([0-9]{1,2})-([0-9]{1,2})$"), (1, 2, 3)),      # YYYY-MM-DD
    (re.compile(r"^([0-9]{1,2})/([0-9]{1,2})/([0-9]{4})$"), (3, 1, 2)),      # MM/DD/YYYY
    (re.compile(r"^([0-9]{1,2})\.([0-9]{1,2})\.([0-9]{4})$"), (3, 2, 1)),    # DD.MM.YYYY
)

MSG_UNLOCKED = "After Dark is unlocked. It stays on until you lock it again (afterdark --lock)."
MSG_ALREADY = "After Dark is already unlocked."
MSG_UNDERAGE = "After Dark is for adults only (18+). It stays locked."
MSG_INVALID = "That is not a date of birth I can use (try YYYY-MM-DD). After Dark stays locked."
MSG_LOCKED = "After Dark is locked."


def parse_date(text) -> datetime.date | None:
    """`YYYY-MM-DD`, `MM/DD/YYYY` or `DD.MM.YYYY` -> date. Anything else (or an impossible date) -> None."""
    if not isinstance(text, str):
        return None
    text = text.strip()
    for rx, (y, m, d) in _FORMATS:
        hit = rx.match(text)
        if hit:
            try:
                return datetime.date(int(hit.group(y)), int(hit.group(m)), int(hit.group(d)))
            except ValueError:
                return None
    return None


def _as_date(value) -> datetime.date | None:
    if isinstance(value, datetime.datetime):
        return value.date()
    return value if isinstance(value, datetime.date) else None


def age_on(birthdate: datetime.date, today: datetime.date) -> int:
    """Whole years completed on `today`. Someone born on 29 February has their birthday on 1 March in years
    without one (so they turn 18 on 1 March)."""
    before_birthday = (today.month, today.day) < (birthdate.month, birthdate.day)
    return today.year - birthdate.year - (1 if before_birthday else 0)


def clean_state(value) -> dict:
    """The only two shapes ever stored. Anything hand-edited, damaged or half-filled reads as locked."""
    if (isinstance(value, dict) and value.get("unlocked") is True and isinstance(value.get("confirmed_on"), str)
            and parse_date(value["confirmed_on"]) is not None):
        return {"unlocked": True, "confirmed_on": parse_date(value["confirmed_on"]).isoformat()}
    return dict(LOCKED)


def is_unlocked(state) -> bool:
    return isinstance(state, dict) and clean_state(state.get("afterdark"))["unlocked"]


def confirmed_on(state) -> str | None:
    """The day After Dark was unlocked (ISO date), or None while locked."""
    return clean_state(state.get("afterdark")).get("confirmed_on") if isinstance(state, dict) else None


def unlock(state: dict, birthdate, today: datetime.date | None = None) -> tuple[bool, str]:
    """Check the date of birth and, for an adult, unlock. Returns (ok, message); the message never contains the
    birth date. An already-unlocked state returns ok straight away without looking at `birthdate` at all."""
    if is_unlocked(state):
        return True, MSG_ALREADY
    if not isinstance(state, dict):
        return False, MSG_LOCKED
    today = _as_date(today) or datetime.date.today()
    born = _as_date(birthdate)
    state["afterdark"] = dict(LOCKED)                    # also repairs a damaged entry; no record of the attempt
    if born is None or born > today:
        return False, MSG_INVALID
    age = age_on(born, today)
    if age > MAX_AGE:
        return False, MSG_INVALID
    if age < ADULT_AGE:
        return False, MSG_UNDERAGE
    state["afterdark"] = {"unlocked": True, "confirmed_on": today.isoformat()}
    return True, MSG_UNLOCKED


def lock(state: dict) -> None:
    state["afterdark"] = dict(LOCKED)


def status(state) -> str:
    day = confirmed_on(state)
    return f"After Dark is unlocked (confirmed on {day})." if day else MSG_LOCKED
