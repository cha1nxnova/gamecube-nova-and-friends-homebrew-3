#!/usr/bin/env python3
"""Reproducible catalog generator (stdlib only, no network at runtime).

Usage:
  python scripts/build_catalog.py --wiki wiki.json --gametdb wiitdb.txt \
      [--catalog data/catalog.json] [--out data/catalog.json] [--report]

Inputs (download them yourself, see docs/CATALOG_SOURCES.md):
  --wiki     JSON from the MediaWiki API (action=parse&prop=wikitext&formatversion=2)
             for "List of GameCube games", or a raw wikitext file.
  --gametdb  GameTDB "ID = Title" export (wiitdb.txt?LANG=EN).

Existing entries in the catalog are kept byte-for-byte (same keys/tags/aliases/code4);
new entries are only appended. Re-running on its own output is idempotent.
"""
import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

ALLOWED_TAGS = {"furry", "furry-adjacent", "cats-and-dogs", "cat-adjacent", "cozy", "cute", "racing",
                "party", "horror", "spooky", "rpg", "sports", "fighting", "platformer", "adventure",
                "action", "scifi", "co-op", "weird", "arcade", "fox", "dragon", "bongos"}

# Hand-reviewed GameTDB-title -> Wikipedia-title equivalences (normalized equality after mapping).
# Keys and values are compared with norm(); keep this list tiny and justified in docs/CATALOG_SOURCES.md.
TITLE_ALIASES = {
}


def core_norm(s):
    """Same as pawtation.core.norm."""
    s = s.lower().replace("&", "and")
    s = re.sub(r"\[.*?\]|\(.*?\)", " ", s)
    return re.sub(r"[^a-z0-9]+", "", s)


def unaccent(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def norm(s):
    """core.norm after stripping accents (so "Pokémon" dedupes against "Pokemon")."""
    return core_norm(unaccent(s).replace("$", "s"))   # "Game$!" == "Games!"


def slugify(s):
    s = re.sub(r"[^a-z0-9]+", "-", unaccent(s).lower().replace("&", "and"))
    return s.strip("-")


# ---------- wikitext parsing ----------
def split_top(s, sep):
    """Split s on sep, ignoring separators inside [[ ]] and {{ }}."""
    out, depth_b, depth_c, i, cur = [], 0, 0, 0, []
    while i < len(s):
        two = s[i:i + 2]
        if two == "[[":
            depth_b += 1; cur.append(two); i += 2; continue
        if two == "]]":
            depth_b -= 1; cur.append(two); i += 2; continue
        if two == "{{":
            depth_c += 1; cur.append(two); i += 2; continue
        if two == "}}":
            depth_c -= 1; cur.append(two); i += 2; continue
        if depth_b <= 0 and depth_c <= 0 and s.startswith(sep, i):
            out.append("".join(cur)); cur = []; i += len(sep); continue
        cur.append(s[i]); i += 1
    out.append("".join(cur))
    return out


def clean(s):
    s = re.sub(r"<!--.*?-->", "", s, flags=re.S)
    s = re.sub(r"<ref[^>]*/>", "", s)
    s = re.sub(r"<ref[^>]*>.*?</ref>", "", s, flags=re.S)
    s = re.sub(r"<sup>.*?</sup>", "", s)
    s = re.sub(r"\{\{(?:hlist|plainlist|flatlist)\s*\|(.*?)\}\}", lambda m: "\x00".join(m.group(1).split("|")), s, flags=re.S)
    s = re.sub(r"\{\{(?:nowrap|lang\|[a-z-]+)\|(.*?)\}\}", r"\1", s)
    s = re.sub(r"\{\{[^{}]*\}\}", "", s)
    s = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = s.replace("'''", "").replace("''", "").replace("&amp;", "&").replace("&nbsp;", " ")
    return s


def cell_content(c):
    c = c.strip()
    parts = split_top(c, "|")
    if len(parts) > 1 and (parts[0].strip() == "" or "=" in parts[0]):
        c = "|".join(parts[1:])
    return c.strip()


def parse_wiki(text):
    i = text.index('id="softwarelist"')
    j = text.index("\n|}", i)
    body = text[i:j]
    rows = []
    for chunk in re.split(r"\n\|-[^\n]*", body)[1:]:
        cells = []
        for line in chunk.split("\n"):
            if line.startswith("|") and not line.startswith("|+"):
                for c in split_top(line[1:], "||"):
                    cells.append(cell_content(c))
            elif line.startswith("!") or not line.strip():
                continue
            elif cells:
                cells[-1] += "\n" + line
        if len(cells) < 7:
            continue
        raw_title = cells[0]
        parts = re.split(r"<br\s*/?>", raw_title)
        title = clean(parts[0]).strip()
        alts = [clean(p).strip() for p in parts[1:]]
        alts = [a for a in alts if a]
        dev = ", ".join(x.strip() for x in clean(cells[1]).split("\x00") if x.strip()) if cells[1] else ""
        dev = re.sub(r"\s+", " ", clean(cells[1]).replace("\x00", ", ")).strip()
        years = []
        for c in cells[3:7]:
            years += [int(y) for y in re.findall(r"\b(19\d\d|20\d\d)-\d\d-\d\d", c)]
            years += [int(y) for y in re.findall(r"\{\{dts\|(\d{4})\|", c)]
        if not title or not years:
            continue   # cancelled / unreleased everywhere
        rows.append({"title": title, "alts": alts, "developer": dev, "year": min(years)})
    return rows


def load_wiki(path):
    raw = Path(path).read_text(encoding="utf-8")
    try:
        d = json.loads(raw)
        return d["parse"]["wikitext"]
    except (ValueError, KeyError, TypeError):
        return raw


# ---------- GameTDB ----------
def load_gametdb(path):
    """-> {code4: set(raw titles)} for G??E?? (NTSC-U) IDs. Titles with brackets/parens are skipped
    (hack/mod/disc suffixes), except they still count as titles for ambiguity detection."""
    by_code, by_title = {}, {}
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.fullmatch(r"(G[A-Z0-9]{2}E[A-Z0-9]{2}) = (.+?)\s*", line)
        if not m:
            continue
        gid, t = m.groups()
        by_code.setdefault(gid[:4], set()).add((gid, t))
    return by_code


def code_candidates(by_code):
    """-> {norm title: set(code4)} using only clean titles, excluding code4s that carry >1 distinct title."""
    t2c = {}
    for code4, items in by_code.items():
        titles = {norm(t) for _, t in items}
        clean_titles = {norm(t) for _, t in items if not re.search(r"[\[\(]", t)}
        if len(titles) != 1:      # same code4 used by several different titles (hacks/mods): ambiguous
            continue
        for n in clean_titles:
            t2c.setdefault(n, set()).add(code4)
    return t2c


# ---------- build ----------
def build(catalog_path, wiki_path, gametdb_path):
    cat = json.loads(Path(catalog_path).read_text(encoding="utf-8"))
    games = cat["games"]
    orig_n = len(games)
    names, keys, codes = {}, {g["key"] for g in games}, {g["code4"] for g in games if g.get("code4")}
    for g in games:
        for n in [g["title"], *(g.get("aliases") or [])]:
            names[norm(n)] = g["key"]
    t2c = code_candidates(load_gametdb(gametdb_path))
    rows = parse_wiki(load_wiki(wiki_path))
    added, skipped_dup, ambiguous, new = 0, 0, [], []
    for r in rows:
        n = norm(r["title"])
        if n in names:
            skipped_dup += 1
            continue
        alias_set = []
        if unaccent(r["title"]) != r["title"]:
            alias_set.append(unaccent(r["title"]))
        for a in r["alts"]:
            if norm(a) and norm(a) != n and norm(a) not in names and a not in alias_set:
                alias_set.append(a)
        key = slugify(r["title"]) or "game"
        if key in keys:
            key = f"{key}-{r['year']}"
        i = 2
        while key in keys:
            key = f"{slugify(r['title'])}-{r['year']}-{i}"; i += 1
        entry = {"key": key, "title": r["title"], "year": r["year"], "developer": r["developer"],
                 "genres": [], "tags": [], "aliases": alias_set}
        cands = t2c.get(n)
        if cands is None:
            for src, dst in TITLE_ALIASES.items():
                if norm(dst) == n:
                    cands = t2c.get(norm(src))
        if cands:
            if len(cands) == 1:
                c4 = next(iter(cands))
                if c4 not in codes:
                    entry["code4"] = c4
                    codes.add(c4)
            else:
                ambiguous.append((r["title"], sorted(cands)))
        keys.add(key)
        names[n] = key
        for a in alias_set:
            names[norm(a)] = key
        new.append(entry)
    cat["games"] = games + new
    n_code = sum(1 for g in cat["games"] if g.get("code4"))
    if new:
        cat["_comment"] = (f"Catalog of {len(cat['games'])} GameCube titles ({orig_n} hand-curated seed entries + "
                           f"{len(new)} generated by scripts/build_catalog.py from Wikipedia 'List of GameCube games' "
                           f"(title/year/developer) and the GameTDB title list (code4, exact normalized title match only; "
                           f"{n_code} entries have code4). code4 = NTSC-U game code; entries without it still match by "
                           f"filename. Not every release is listed. See docs/CATALOG_SOURCES.md and HANDOFF.md.")
    return cat, {"rows": len(rows), "dups": skipped_dup, "new": len(new), "ambiguous": ambiguous}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wiki", required=True)
    ap.add_argument("--gametdb", required=True)
    ap.add_argument("--catalog", default="data/catalog.json")
    ap.add_argument("--out", default=None, help="write result here (default: print stats only)")
    a = ap.parse_args(argv)
    cat, st = build(a.catalog, a.wiki, a.gametdb)
    print(f"wiki rows parsed: {st['rows']}, duplicates of existing: {st['dups']}, new: {st['new']}, "
          f"total: {len(cat['games'])}, with code4: {sum(1 for g in cat['games'] if g.get('code4'))}")
    for t, c in st["ambiguous"]:
        print(f"  ambiguous code4 omitted: {t} -> {c}")
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(cat, f, indent=1, ensure_ascii=False)
            f.write("\n")
        print("wrote", a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
