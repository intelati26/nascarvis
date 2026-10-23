#!/usr/bin/env python3
"""Compare each remaining gap driver's season points on his own Wikipedia article with the season-table total and the data.  python curation/check_driver_pages.py [season driver ...]
For every driver in gap_explanations_1975_2003.csv (or the season/driver pairs given), finds the article (search, first result whose title starts with the name), reads the Cup results table row for
the season (the Pts column) and writes driver_page_points.csv: season, driver, article, page_pts, season_table_total, data_total, and which of the two the article agrees with.
One request per article at most (cached in the session scratchpad, not in the repo), a project user-agent, 0.8 s between requests. Nothing is changed in the data; the article's figure is a third reading."""
import csv, json, os, re, sys, time, urllib.parse, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__))
UA = "nascarvis/1.0 (https://github.com/intelati26/nascarvis; personal research)"
CACHE = os.environ.get("DRIVER_PAGE_CACHE", "/tmp/nascarvis_driver_pages"); os.makedirs(CACHE, exist_ok=True)
norm = lambda s: re.sub(r"[^a-z]", "", s.lower())
_last = [0.0]


def get(url):
    wait = 0.8 - (time.time() - _last[0])
    if wait > 0: time.sleep(wait)
    _last[0] = time.time()
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=60).read().decode("utf-8", "replace")


def find_article(name):
    path = os.path.join(CACHE, "title_" + norm(name) + ".json")
    if os.path.exists(path): return json.load(open(path))["title"]
    q = urllib.parse.urlencode({"action": "query", "list": "search", "srsearch": f"{name} NASCAR driver", "srlimit": 5, "format": "json"})
    title = next((h["title"] for h in json.loads(get("https://en.wikipedia.org/w/api.php?" + q))["query"]["search"] if norm(h["title"]).startswith(norm(name))), None)
    json.dump({"title": title}, open(path, "w")); return title


def wikitext(title):
    path = os.path.join(CACHE, "page_" + norm(title) + ".txt")
    if os.path.exists(path): return open(path, encoding="utf-8").read()
    txt = get("https://en.wikipedia.org/w/index.php?title=" + urllib.parse.quote(title) + "&action=raw")
    open(path, "w", encoding="utf-8").write(txt); return txt


def cells(block):
    out = []
    for l in block.split("\n"):
        l = l.strip()
        if l and l[0] in "!|" and not l.startswith(("{|", "|}", "|+", "|-")):
            for part in re.split(r"\|\||!!", l[1:]): out.append(re.sub(r"^\s*(?:[a-z]+=[^|]*\|)(?!\|)", "", part).strip())
    return out


def page_points(text, season):
    """Pts for `season` from the Cup results table(s) of an article, or None. The Pts column is found from the header row and counted from the end of each row."""
    for table in re.split(r"\n\{\|", text)[1:]:
        table = table.split("\n|}")[0]
        rows = re.split(r"\n\|-", table)
        head = next((cells(r) for r in rows if "Pts" in r and "NWCC" in r.replace("NSCC", "NWCC") + "NWCC"), None)
        if not head: continue
        tail = [re.sub(r"[\[\]'{}|]|<[^>]*>", "", c).strip() for c in head][-4:]
        if "Pts" not in tail: continue
        back = len(tail) - tail.index("Pts")
        for r in rows:
            c = cells(r)
            if c and re.search(rf"\[\[{season} NASCAR[^\]|]*(?:Cup|Winston)[^\]|]*", c[0]) or (c and c[0].strip("[]| ") == str(season) and "Cup" in table[:400]):
                v = re.sub(r"<[^>]*>|\[\[[^\]|]*\|?|\]\]|[,'*]", "", c[-back]).strip() if len(c) >= back else ""
                m = re.match(r"^\d+(\.\d+)?", v)
                return float(m.group()) if m else "-"                     # the season's row is there but lists no points ("-")
    return None


def main():
    gaps = list(csv.DictReader(open(os.path.join(HERE, "gap_explanations_1975_2003.csv"), encoding="utf-8")))
    want = [(int(g["season"]), g["driver"], float(g["wikipedia_total"]), float(g["data_total"])) for g in gaps]
    if sys.argv[1:]:
        pick = {(int(a), b) for a, b in zip(sys.argv[1::2], sys.argv[2::2])}
        want = [w for w in want if (w[0], w[1]) in pick]
    out = []
    for season, driver, wiki, data in want:
        try:
            title = find_article(driver); pts = page_points(wikitext(title), season) if title else None
        except Exception as e:
            title, pts = (None, None); print("  error", driver, e)
        agree = ("no article" if not title else "season row not found" if pts is None else "page lists no points" if pts == "-" else "agrees with data" if pts == data else "agrees with season table" if pts == wiki else "neither")
        out.append([season, driver, title or "", "" if pts in (None, "-") else pts, wiki, data, agree]); print(f"{season} {driver:20s} article={title or '-':28s} page={pts} table={wiki:g} data={data:g}  {agree}")
    with open(os.path.join(HERE, "driver_page_points.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["season", "driver", "article", "page_pts", "season_table_total", "data_total", "agrees_with"]); w.writerows(out)


if __name__ == "__main__": main()


def review_csv():
    """driver_page_review.csv: one row per remaining gap driver with the three readings side by side, what explain_gaps.py found, and the Racing-Reference check columns, filled from rr_checks.csv."""
    pages = {(int(r["season"]), r["driver"]): r for r in csv.DictReader(open(os.path.join(HERE, "driver_page_points.csv"), encoding="utf-8"))}
    checks = {}                                               # the project owner's Racing-Reference checks, kept in rr_checks.csv so a rebuild does not wipe them
    if os.path.exists(os.path.join(HERE, "rr_checks.csv")):
        checks = {(int(r["season"]), r["driver"]): r for r in csv.DictReader(open(os.path.join(HERE, "rr_checks.csv"), encoding="utf-8"))}
    rr_id = lambda n: (lambda p: re.sub(r"[^a-z]", "", p[-1].lower())[:5] + re.sub(r"[^a-z]", "", p[0].lower())[:2] + "01")([x for x in re.sub(r"\b(Jr|Sr|II|III)\.?$", "", n).split() if x])
    out = []
    for g in csv.DictReader(open(os.path.join(HERE, "gap_explanations_1975_2003.csv"), encoding="utf-8")):
        s = int(g["season"]); p = pages.get((s, g["driver"]), {})
        out.append([s, g["driver"], g["wikipedia_total"], p.get("page_pts", ""), g["data_total"], g["gap_wikipedia_minus_data"], p.get("agrees_with", ""), g["fits"], g["rows"], g["noted"],
                    "https://en.wikipedia.org/wiki/" + p["article"].replace(" ", "_") if p.get("article") else "",
                    f"https://www.racing-reference.info/driver-season-stats/{rr_id(g['driver'])}/{s}/W",
                    checks.get((s, g["driver"]), {}).get("rr_total_checked", ""), checks.get((s, g["driver"]), {}).get("rr_agrees_with", ""), checks.get((s, g["driver"]), {}).get("notes", "")])
    with open(os.path.join(HERE, "driver_page_review.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["season", "driver", "wikipedia_season_table", "wikipedia_driver_page", "data_total", "gap_table_minus_data", "driver_page_agrees_with", "explain_gaps_fits", "explain_gaps_rows", "noted",
                    "wikipedia_article", "racing_reference_url_guess", "rr_total_checked", "rr_agrees_with", "notes"])
        w.writerows(sorted(out)); print("driver_page_review.csv:", len(out), "rows")


if __name__ == "__main__" and not sys.argv[1:] and os.path.exists(os.path.join(HERE, "driver_page_points.csv")): review_csv()
