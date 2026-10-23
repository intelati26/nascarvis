#!/usr/bin/env python3
"""Collect every discrepancy found while curating early-season points into curation/discrepancies.csv.
Run from the repo root:  python curation/save_discrepancies.py

Rows (kind): standings_vs_model (1957: official total minus the fitted purse model), standings_vs_data (1955 and 1960: every driver
whose data total differs from the official standings; 1955, 1960, 1966, 1970, 1971 and 1975-2003), champion_total (champion_check.csv),
chart_vs_wikipedia (1949), reconcile_adjustment (1950/51/72/73 entries over a size threshold, plus zeroed drivers),
identity (names/counts that differ between sources), source_error (a source disagreeing with the others).
difference = found - expected, so a positive number means the second source/model is higher."""
import collections, csv, json, os, re
import pyarrow.parquet as pq

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
norm = lambda s: re.sub(r"[^a-z]", "", s.lower())
rows = []
def diff(a, b):
    try: return round(float(b) - float(a), 2)
    except (TypeError, ValueError): return ""
add = lambda season, kind, subject, expected, found, detail, sources: rows.append(
    [season, kind, subject, expected, found, diff(expected, found), detail, sources])

# ---- 1957: official standings (Racing-Reference) minus the fitted purse model
t = pq.read_table(os.path.join(ROOT, "cup_series.parquet")).to_pydict()
res = collections.defaultdict(dict)
for i, s in enumerate(t["Season"]):
    if s == 1957: res[norm(t["Driver"][i])][t["Race"][i]] = t["Finish"][i]
W = {r: 200 for r in range(1, 54)}
W.update({4: 500, 17: 500, 12: 250, 32: 250, 37: 250, 41: 250, 10: 350, 1: 350, 28: 1000, 31: 750, 40: 2100, 45: 1000, 49: 1000})
lin = lambda f: (26 - f) / 25 if f <= 25 else 0
for r in csv.DictReader(open(os.path.join(HERE, "final_standings_1957.csv"))):
    k = norm(r["driver"]); off = float(r["pts"]); n = int(r["races"])
    if k not in res:
        add(1957, "identity", r["driver"], n, 0, "listed in the Racing-Reference standings but not found in the data by name (probably a spelling variant)", "final_standings_1957.csv; cup_series.parquet"); continue
    model = sum(lin(f) * W[x] for x, f in res[k].items()); d = off - model
    note = ""
    if len(res[k]) != n: note = f"starts differ: standings {n}, data {len(res[k])}; "
    if abs(d) >= 150: note += "official total is " + ("HIGHER" if d > 0 else "LOWER") + " than the results support (cause unknown)"
    if abs(d) >= 150 or note:
        add(1957, "standings_vs_model", r["driver"], round(model, 1), off, note.strip("; ") + f" [pos {r['pos']}, {n} starts]", "final_standings_1957.csv; race_purses_1957.csv; fitted tier map in this script")
# (difference here = official - model; the generic column above is found - expected with expected=model, found=official)

# ---- champion check (1949-2003) misses
for r in csv.DictReader(open(os.path.join(HERE, "champion_check.csv"))):
    if r["status"] != "match":
        add(int(r["season"]), "champion_total", r["champion"], float(r["official_pts"]), float(r["data_sum"]),
            f"{r['status']}; blank Pts rows after curation: {r['blank_rows']}", "champions_points.csv (Wikipedia); data + curation")

# Causes established by hand for single drivers: (season, driver) -> text that replaces the generic "cause unknown"
KNOWN = {
    (2000, "Jeff Gordon"): "EXPLAINED: all 34 points races match a results page supplied by the project owner (finish and points) and sum to 4,461; the official total is exactly 100 lower because of a penalty. Jayski, 13 Sep 2000, \"Gordon's engine problem update 6: the penalty, the appeal, the reactions\" https://www.jayski.com/2000/09/13/gordons-engine-problem-update-6-the-penalty-the-appeal-the-reactions/ says (text quoted by the project owner; the page itself was not fetched, the site returned 403): in addition to the fine, driver Jeff Gordon (#24) loses 100 driver points and 100 owner points are taken from team owner Rick Hendrick. The race it concerns and the appeal result are not recorded here; the official total shows the deduction stood. Added to adjustments.json from race 26, the first race after the announcement",
    (2000, "Jeff Burton"): "EXPLAINED (reported by the project owner; source and race still to be recorded): all 34 points races match a results page supplied by the project owner (finish and points), sum to 4,836, and every row also equals the 2000 formula (base points by finish + 5 for leading a lap + 5 for most laps led); the official total is exactly 5 higher. The project owner reports references to a scoring error that was corrected later; that fits a 5-point credit (such as a lead-lap bonus) added after the race rows were published. Source and race not yet recorded; the +5 is in adjustments.json at the last race (34) because the race is unknown",
    (2002, "Dale Jarrett"): "EXPLAINED: 25-point penalty, #88, crew chief Todd Parrott, New Hampshire 21 Jul (race 19), 1/8th of an inch too low, $25,000 fine; the Gainesville Sun headline of 23 Jul 2002 reads \"Quarter-inch costs Jarrett 25 points\" (the table says 1/8th). Source: Jayski 2002 penalties table (https://www.jayski.com/nascar-cup-series/2002-nascar-penalties/, pasted by the project owner; page not fetched). The official total is exactly 25 below the race rows. In adjustments.json from race 20, the first race after the announcement",
    (2002, "Jimmie Johnson"): "EXPLAINED: 25-point penalty, #48, crew chief Chad Knaus, Daytona 6 Jul (race 17), offset mounting bolts (NASCAR did not approve the location of some bolts), $25,000 fine; announced in the same Gainesville Sun article as Jarrett's, 23 Jul 2002. Source: Jayski 2002 penalties table (https://www.jayski.com/nascar-cup-series/2002-nascar-penalties/, pasted by the project owner; page not fetched). The official total is exactly 25 below the race rows. In adjustments.json from race 20, the first race after the announcement",
    (2002, "Jeff Green"): "EXPLAINED: 25-point penalty, #30, crew chief Todd Berrier, Richmond 7 Sep (race 26), unapproved left front spring, $5,000 fine. Source: Jayski 2002 penalties table (https://www.jayski.com/nascar-cup-series/2002-nascar-penalties/, pasted by the project owner; page not fetched). The official total is exactly 25 below the race rows. In adjustments.json from race 27, the first race after the announcement",
    (2002, "Rusty Wallace"): "EXPLAINED: 25-point penalty, #2, crew chief Billy Wilburn, Talladega 6 Oct (race 30), unapproved spoiler, $25,000 fine. Source: Jayski 2002 penalties table (https://www.jayski.com/nascar-cup-series/2002-nascar-penalties/, pasted by the project owner; page not fetched). The official total is exactly 25 below the race rows. In adjustments.json from race 31, the first race after the announcement",
    (2002, "Ward Burton"): "EXPLAINED: 25-point penalty, #22, crew chief Frank Stoddard, Martinsville 20 Oct (race 32), unapproved front springs, $10,000 fine. Source: Jayski 2002 penalties table (https://www.jayski.com/nascar-cup-series/2002-nascar-penalties/, pasted by the project owner; page not fetched). The official total is exactly 25 below the race rows. In adjustments.json from race 33, the first race after the announcement",
}

# ---- full field: every driver in the official standings whose data total differs (seasons where nascaR.data is mostly present)
import importlib.util, difflib
spec = importlib.util.spec_from_file_location("bd", os.path.join(ROOT, "build_dashboard.py")); bd = importlib.util.module_from_spec(spec); spec.loader.exec_module(bd)
tt = pq.read_table(os.path.join(ROOT, "cup_series.parquet")).to_pydict(); bd.apply_curation(tt, HERE)
nan = lambda v: v is None or v != v
# 1955 scale: places 1-25 score W x (26 - place) / 25, below 25th W / 25, with W the winner's points (350 for the Daytona race derived in curation/)
scale55, w55 = collections.defaultdict(list), {}
for i, sn in enumerate(tt["Season"]):
    if sn == 1955 and tt["Finish"][i] == 1 and not nan(tt["Pts"][i]) and tt["Pts"][i]: w55[tt["Race"][i]] = tt["Pts"][i]
for i, sn in enumerate(tt["Season"]):
    if sn == 1955 and tt["Race"][i] in w55 and not nan(tt["Pts"][i]):
        f, W = tt["Finish"][i], w55[tt["Race"][i]]
        scale55[norm(tt["Driver"][i])].append((tt["Race"][i], f, tt["Pts"][i], W * (26 - f) / 25 if f <= 25 else W / 25))
for season in (1955, 1960, 1966, 1970, 1971, *range(1975, 2004)):
    totals, blanks, names = collections.defaultdict(float), collections.Counter(), {}
    for i, sn in enumerate(tt["Season"]):
        if sn != season: continue
        k = norm(tt["Driver"][i]); names[k] = tt["Driver"][i]
        if nan(tt["Pts"][i]): blanks[k] += 1
        else: totals[k] += tt["Pts"][i]
    for r in csv.DictReader(open(os.path.join(HERE, f"final_standings_{season}.csv"))):
        o = norm(r["driver"]); k = o if o in names else next(iter(difflib.get_close_matches(o, list(names), n=1, cutoff=0.9)), None)
        if k is None: continue
        d = totals[k] - float(r["pts"])
        if abs(d) < 1e-6: continue
        b = blanks[k]
        why = (f"{b} blank Pts row{'s' if b != 1 else ''} in the data" + ("; the gap is recoverable if it is the only missing value" if b == 1 else "")) if b else "no blank rows: the data total differs from the official one (cause unknown)"
        if season == 1955 and not b:                                    # 1955 has a verified scale, so rows can be tested against it
            bad = [x for x in scale55.get(k, []) if abs(x[2] - x[3]) > 1e-6]
            if float(r["pts"]) <= 1: why = "official total is 1: the driver's points appear to have been removed (same pattern as 1950 Byron and Dunaway)"
            elif bad: why = "data row(s) off the 1955 scale: " + "; ".join(f"race {x[0]} finish {x[1]} data {x[2]:g}, scale {x[3]:g}" for x in bad)
            elif abs(abs(d) - round(abs(d), -2)) < 1e-6: why = f"no data row breaks the 1955 scale; the official total is exactly {abs(d):g} {'lower' if d > 0 else 'higher'}: looks like a points deduction"
        if (season, names[k]) in KNOWN: why = KNOWN[(season, names[k])]
        add(season, "standings_vs_data", names[k], float(r["pts"]), round(totals[k], 2), why + f" [official pos {r['pos']}]", "final_standings_%d.csv (Wikipedia); data + curation" % season)

# ---- 1949 chart vs Wikipedia (reconcile entries)
adj = json.load(open(os.path.join(ROOT, "adjustments.json")))
for a in adj:
    if a["season"] == 1949 and a["note"].startswith("1949 reconcile"):
        m = re.search(r"Wikipedia final total ([\d.]+) vs chart sum ([\d.]+)", a["note"])
        wiki, chart = (float(m.group(1)), float(m.group(2))) if m else ("", "")
        add(1949, "chart_vs_wikipedia", a["driver"], wiki, chart, "expected = Wikipedia total, found = chart total (chart's own notes flag Langhorne errors, an 84-point Rice/Dunaway transfer and penalties)", "points_1949.csv (Reddit chart); final_standings_1949.csv (Wikipedia)")
# ---- large reconcile entries and zeroed drivers
for a in adj:
    n = a["note"]
    if n.startswith(("1950 reconcile", "1951 reconcile")) and (abs(a["pts"]) >= 100 or "zeroed" in n or "all points deducted" in n or "no points" in n):
        add(a["season"], "reconcile_adjustment", a["driver"], "", "", f"{a['pts']:+g}: " + n.split(": ", 1)[1], "adjustments.json; derive_points_prize.py")
    if n.endswith("(1972-73 reconcile)") and abs(a["pts"]) >= 50:
        add(a["season"], "reconcile_adjustment", a["driver"], "", "", f"{a['pts']:+g}: " + n, "adjustments.json; derive_points_1972_73.py")

# ---- identity / source errors found by hand
manual = [
    (1949, "identity", "Bob Apperson / Bob Appleton", 3, 0, "data labels race 5's 15th place 'Bob Apperson'; chart and Wikipedia both say 'Bob Appleton' (3 points). Adjustment -3 on Apperson.", "cup_series.parquet; points_1949.csv; final_standings_1949.csv"),
    (1949, "identity", "Sam Rice / Glenn Dunaway", 84, 0, "84 points sit with Dunaway in Wikipedia but with Rice in the chart (the chart's notes call it an unexplained transfer).", "points_1949.csv; final_standings_1949.csv"),
    (1957, "source_error", "Lee Petty (Wikipedia 1957 table)", "41/4/3", "38/2/4", "Wikipedia gives races/wins/poles 38/2/4 (identical to Speedy Thompson's row); Racing-Reference and the data give 41 starts, 4 wins, 3 poles. Wikipedia looks wrong.", "Wikipedia 1957 NASCAR Grand National Series; Racing-Reference screenshots; data"),
    (1953, "source_error", "Curtis Turner / Jimmie Lewallen (Wikipedia 1953 table)", "", "", "10th place Turner (3,373) has more points than 9th place Lewallen (3,208); probably a typo in the article. Kept as published.", "final_standings_1953.csv"),
    (1951, "identity", "12 drivers absent from the standings table", "", "", "Teague, McGriff, Turner, Sales, Byron, Norton, Burke, Sprague, Tippett, Adams, Snow, Moffitt score above the table's lowest total under the rule but are not listed; zeroed as placeholders.", "adjustments.json; final_standings_1951.csv"),
    (1950, "identity", "Red Byron, Glenn Dunaway, Hershel McGriff, Otis Martin", "", "", "Byron and Dunaway: all points deducted; McGriff: listed as scoring none (article); Martin: simply absent (under 57.5), zeroed as a placeholder.", "Wikipedia 1950 article; adjustments.json"),
    (1957, "identity", "Lucky Long", 2, 1, "standings list 2 starts, the data has 1 (finishing 27th in race 22).", "final_standings_1957.csv; cup_series.parquet"),
    (2002, "source_error", "Mark Martin (Rockingham, race 34)", 180, 155, "nascaR.data already has his 25-point penalty (unapproved left front spring, Rockingham 3 Nov) inside the race row: 155 where the 2002 formula gives 180. The other five 2002 penalties are not in the race rows, so the data treats the same kind of penalty two ways. No adjustment needed for Martin (his total already matches).", "cup_series.parquet; penalties_2002.csv (Jayski table)"),
    (1972, "source_error", "nascaR.data Pts column", "", "", "Pts hold rank points only (max 100 in 1972, 125 in 1973); official totals add distance points per lap. Rebuilt in points_1972.csv / points_1973.csv.", "cup_series.parquet; Wikipedia points-systems page"),
]
for m in manual: add(*m)

rows.sort(key=lambda r: (r[0], r[1], str(r[2])))
with open(os.path.join(HERE, "discrepancies.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["season", "kind", "subject", "expected", "found", "difference", "detail", "sources"]); w.writerows(rows)
print(len(rows), "rows;", dict(collections.Counter((r[1]) for r in rows)))
print("by season:", dict(sorted(collections.Counter(r[0] for r in rows).items())))
