#!/usr/bin/env python3
"""Fill track_attributes.csv with each track's banking, by layout and era, from its Wikipedia infobox.  python fetch_track_banking.py [--min-races 3]
For every track in cup_series.parquet with at least --min-races races: open the track's article (its own name first, then a search) and read the infobox `banking`,
`banking2`, ... fields with their `layout`, `layout2`, ... labels. The steepest angle of each is kept (the turns; the straights are always lower). A layout whose label has years,
like "Quad-oval (1997-2021)" or "(2022-present)", gives the seasons it covers (from_season / to_season, blank = open); road and dirt layouts are skipped; a label without years
covers every season. One row per layout. A track with a hand-written `notes` value is never refetched, so a correction survives a rerun. The `shape` column is filled by hand.
One request per page at most, a project user-agent, 0.8 s between requests; pages are cached in $TRACK_PAGE_CACHE (default /tmp/nascarvis_track_pages).
Wikipedia text is CC BY-SA 4.0; only the angle, a short excerpt and the article link are kept here."""
import argparse, collections, csv, json, os, re, time, urllib.error, urllib.parse, urllib.request
import pyarrow.parquet as pq
HERE = os.path.dirname(os.path.abspath(__file__))
UA = "nascarvis/1.0 (https://github.com/intelati26/nascarvis; personal research)"
CACHE = os.environ.get("TRACK_PAGE_CACHE", "/tmp/nascarvis_track_pages"); os.makedirs(CACHE, exist_ok=True)
OUT = os.path.join(HERE, "track_attributes.csv")
FIELDS = ["track", "races", "from_season", "to_season", "banking_deg", "banking_text", "layout", "article", "shape", "notes"]
SKIP_LAYOUT = re.compile(r"road|roval|infield|dirt|short track", re.I)
norm = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())
_last = [0.0]


def get(url):
    wait = 0.8 - (time.time() - _last[0])
    if wait > 0: time.sleep(wait)
    _last[0] = time.time()
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=60).read().decode("utf-8", "replace")


def cached(name, fn):
    p = os.path.join(CACHE, name)
    if os.path.exists(p): return open(p, encoding="utf-8").read()
    v = fn(); open(p, "w", encoding="utf-8").write(v); return v


def raw_page(title):
    try:
        return cached("p_" + norm(title) + ".txt", lambda: get("https://en.wikipedia.org/w/index.php?title=" + urllib.parse.quote(title) + "&action=raw"))
    except urllib.error.HTTPError:
        return ""


def page(title, depth=0):
    """(final title, wikitext), following a redirect."""
    txt = raw_page(title)
    m = re.match(r"\s*#redirect\s*\[\[([^\]|#]+)", txt, re.I)
    return page(m.group(1), depth + 1) if m and depth < 3 else (title, txt)


def search(track):
    q = urllib.parse.urlencode({"action": "query", "list": "search", "srsearch": f"{track} NASCAR track", "srlimit": 5, "format": "json"})
    hits = [h["title"] for h in json.loads(cached("s_" + norm(track) + ".json", lambda: get("https://en.wikipedia.org/w/api.php?" + q)))["query"]["search"]]
    return next((h for h in hits if norm(h) == norm(track)), None) or next((h for h in hits if norm(h).startswith(norm(track)) and "museum" not in h.lower()), None)


def article(track):
    """(title, wikitext) of the track's article: its own name first, then a search; only a page with an infobox `banking` field counts."""
    for title in [track, search(track)]:
        if not title: continue
        t, txt = page(title)
        if re.search(r"^\s*\|\s*banking\s*=", txt, re.M | re.I): return t, txt
    return None, ""


def field(txt, name):
    m = re.search(r"^\s*\|\s*" + name + r"\s*=\s*(.*)$", txt, re.M | re.I)
    return m.group(1) if m else ""


def clean(raw):
    return re.sub(r"\s+", " ", re.sub(r"<br\s*/?>", "; ", re.sub(r"'''|\[\[|\]\]", "", raw))).strip()[:120]


ANGLE = re.compile(r"(\d+(?:\.\d+)?)(?:\s*(?:–|-|&ndash;|—)\s*(\d+(?:\.\d+)?))?\s*(?:°|&deg;|degrees|deg\b)")
NOT_TURNS = re.compile(r"straight|tri-oval|stretch", re.I)


def turn_angle(raw):
    """The banking of the turns: the mean of the angles given for the turns (a range such as 17-20 counts as its midpoint). The straights, the tri-oval and the front and back
    stretches are left out. A text with no segment about turns (e.g. "5° (Turns)" or "9° (corners)") uses every angle that is not a straight; None when there is no angle."""
    segs = [x for x in re.split(r"<br\s*/?>|;|\n", raw.replace("'" * 3, "")) if ANGLE.search(x)]
    turns = [x for x in segs if re.search(r"turn|corner", x, re.I) and not NOT_TURNS.search(x)]
    use = turns or [x for x in segs if not NOT_TURNS.search(x)] or segs
    vals = [(float(m.group(1)) + float(m.group(2) or m.group(1))) / 2 for x in use for m in ANGLE.finditer(x)]
    return round(sum(vals) / len(vals), 1) if vals else None


def layouts(txt):
    """[(from_season or '', to_season or '', turn banking or None, infobox text, layout label)], one per layout of the infobox."""
    out = []
    for k in [""] + [str(n) for n in range(2, 9)]:
        raw = field(txt, "banking" + k)
        if not raw.strip() and k: continue
        label = clean(field(txt, "layout" + k))
        if SKIP_LAYOUT.search(label): continue
        deg = turn_angle(raw)
        m = re.search(r"(\d{4})\s*(?:–|-|&ndash;|—)\s*(\d{4}|present)", label)
        lo, hi = (m.group(1), "" if m.group(2) == "present" else m.group(2)) if m else ("", "")
        if deg is not None: out.append((lo, hi, deg, clean(raw), label))
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--min-races", type=int, default=3); a = ap.parse_args()
    t = pq.read_table(os.path.join(HERE, "cup_series.parquet")).to_pydict()
    races = collections.defaultdict(set)
    for s, r, tr in zip(t["Season"], t["Race"], t["Track"]): races[tr].add((s, r))
    old = collections.defaultdict(list)
    if os.path.exists(OUT):
        for r in csv.DictReader(open(OUT, encoding="utf-8")): old[r["track"]].append(r)
    rows = []
    for track, rs in sorted(races.items(), key=lambda kv: -len(kv[1])):
        if len(rs) < a.min_races: continue
        if any(r.get("notes") for r in old.get(track, [])):                       # a hand-edited track is never refetched
            for r in old[track]: r["races"] = len(rs); rows.append(r)
            continue
        got, url = [], ""
        try:
            title, txt = article(track)
            if title: got = layouts(txt); url = "https://en.wikipedia.org/wiki/" + title.replace(" ", "_")
        except Exception as e:
            print("  error", track, e)
        for lo, hi, deg, text, label in got or [("", "", None, "", "")]:
            rows.append({"track": track, "races": len(rs), "from_season": lo, "to_season": hi, "banking_deg": "" if deg is None else f"{deg:g}",
                         "banking_text": text, "layout": label, "article": url, "shape": "", "notes": ""})
        print(f"{len(rs):4d} {track[:40]:40s} " + ("; ".join(f"{g[0] or '..'}-{g[1] or 'now'} {g[2]:g}°" for g in got) or "-"))
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS); w.writeheader(); w.writerows(rows)
    tr = {r["track"]: r["races"] for r in rows}; have = {r["track"] for r in rows if r["banking_deg"]}
    print(f"\nwrote {OUT}: {len(rows)} rows for {len(tr)} tracks; {len(have)} tracks have banking, covering {sum(tr[t] for t in have)} of {sum(tr.values())} race-track pairs")


if __name__ == "__main__":
    main()
