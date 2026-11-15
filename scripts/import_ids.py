#!/usr/bin/env python3
"""Merge a user-supplied "ID = Title" list (e.g. a GameTDB export) into data/catalog.json.

  python scripts/import_ids.py PATH_TO_ID_TITLE_TXT [--apply] [--catalog PATH] [--any-region]

Dry-run by default. Only GameCube-looking IDs are read: 6 chars [A-Z0-9], first char G, 4th char E
(NTSC-U, which is what catalog code4 means; --any-region drops the 4th-char rule).
 - existing entry without code4 + exactly equal normalized title -> code4 is set
 - existing entry with a different code4 -> reported as conflict, never overwritten
 - unknown title -> minimal entry (title, code4, year 0, empty lists) is appended
 - ambiguous (same title, several different code4) or code4 already used by another title -> skipped, reported
Standard library only.
"""
import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

DEFAULT_CATALOG = Path(__file__).resolve().parent.parent / "data" / "catalog.json"


def norm(s):
    """pawtation.core.norm plus accent stripping and "$" -> "s"."""
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    s = s.lower().replace("&", "and").replace("$", "s")
    s = re.sub(r"\[.*?\]|\(.*?\)", " ", s)
    return re.sub(r"[^a-z0-9]+", "", s)


def slugify(s):
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", s.lower().replace("&", "and")).strip("-") or "game"


def read_ids(path, any_region=False):
    """-> list of (id6, title) for GameCube-looking IDs, file order."""
    pat = re.compile(r"(G[A-Z0-9]{5}) = (.+?)\s*") if any_region else re.compile(r"(G[A-Z0-9]{2}E[A-Z0-9]{2}) = (.+?)\s*")
    out = []
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        m = pat.fullmatch(line)
        if m:
            out.append(m.groups())
    return out


def plan(cat, ids):
    games = cat["games"]
    by_name = {}
    for g in games:
        for n in [g["title"], *(g.get("aliases") or [])]:
            by_name.setdefault(norm(n), g)
    used = {g["code4"]: g for g in games if g.get("code4")}
    # group by normalized title -> ordered distinct code4s; titles with brackets/parens (mods, discs) are ignored
    groups = {}
    for gid, t in ids:
        if re.search(r"[\[\(]", t):
            continue
        groups.setdefault(norm(t), {"title": t, "codes": []})
        if gid[:4] not in groups[norm(t)]["codes"]:
            groups[norm(t)]["codes"].append(gid[:4])
    # a code4 used by several different titles is ambiguous (hacks/mods share codes)
    code_titles = {}
    for n, grp in groups.items():
        for c in grp["codes"]:
            code_titles.setdefault(c, set()).add(n)
    acts = {"set": [], "add": [], "conflict": [], "skip": []}
    pending_used = dict(used)
    for n, grp in groups.items():
        t, codes = grp["title"], grp["codes"]
        if not n:
            continue
        if len(codes) != 1 or any(len(code_titles[c]) != 1 for c in codes):
            if n in by_name or len(codes) > 1:
                acts["skip"].append((t, codes, "ambiguous code4/title"))
            continue
        c = codes[0]
        g = by_name.get(n)
        if g is not None:
            if not g.get("code4"):
                if c in pending_used:
                    acts["conflict"].append((t, c, f"code4 already used by {pending_used[c]['key']}"))
                else:
                    acts["set"].append((g["key"], c)); pending_used[c] = g
            elif g["code4"] != c:
                acts["conflict"].append((t, c, f"{g['key']} already has {g['code4']}"))
        else:
            if c in pending_used:
                acts["conflict"].append((t, c, f"code4 already used by {pending_used[c]['key']}"))
            else:
                acts["add"].append((t, c)); pending_used[c] = {"key": "(new)"}
    return acts


def apply(cat, acts):
    by_key = {g["key"]: g for g in cat["games"]}
    for key, c in acts["set"]:
        by_key[key]["code4"] = c
    keys = set(by_key)
    for t, c in acts["add"]:
        k = slugify(t)
        i = 2
        while k in keys:
            k = f"{slugify(t)}-{i}"; i += 1
        keys.add(k)
        cat["games"].append({"key": k, "title": t, "year": 0, "developer": "", "genres": [], "tags": [],
                             "aliases": [], "code4": c})


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ids_file")
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry-run)")
    ap.add_argument("--catalog", default=str(DEFAULT_CATALOG))
    ap.add_argument("--any-region", action="store_true")
    a = ap.parse_args(argv)
    cat = json.loads(Path(a.catalog).read_text(encoding="utf-8"))
    acts = plan(cat, read_ids(a.ids_file, a.any_region))
    for key, c in acts["set"]:
        print(f"set code4   {key} = {c}")
    for t, c in acts["add"]:
        print(f"add entry   {t} [{c}]")
    for t, c, why in acts["conflict"]:
        print(f"CONFLICT    {t} [{c}]: {why}")
    for t, codes, why in acts["skip"]:
        print(f"skip        {t} {codes}: {why}")
    print(f"{len(acts['set'])} code4 to set, {len(acts['add'])} to add, {len(acts['conflict'])} conflicts, "
          f"{len(acts['skip'])} skipped" + ("" if a.apply else "  (dry-run; use --apply)"))
    if a.apply and (acts["set"] or acts["add"]):
        apply(cat, acts)
        with open(a.catalog, "w", encoding="utf-8") as f:
            json.dump(cat, f, indent=1, ensure_ascii=False)
            f.write("\n")
        print("wrote", a.catalog)
    return 0


if __name__ == "__main__":
    sys.exit(main())
