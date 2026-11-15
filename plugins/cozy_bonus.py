"""Example plugin (safe to delete or edit). Shows every hook once. See docs/MODDING.md.

- Chat: say "boop" to the pets.
- Planner: games tagged "cozy" get a small nudge during exam season (off by default; flip EXAM_SEASON).
- Command: `python -m pawtation boop`
"""
EXAM_SEASON = False


def register(api):
    api.chat(r"\bboop\b", lambda brain, m, ctx: brain._line(ctx["pet"], "Boop received. Returning one (1) boop."))
    api.score(lambda rom, state, now: 4 if EXAM_SEASON and "cozy" in rom.tags else 0)
    api.command("boop", lambda args: print("Mochi: ...boop."), help="example plugin command")
