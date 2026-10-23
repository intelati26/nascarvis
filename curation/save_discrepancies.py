#!/usr/bin/env python3
"""Collect every discrepancy found while curating early-season points into curation/discrepancies.csv.
Run from the repo root:  python curation/save_discrepancies.py

Rows (kind): standings_vs_model (1957: official total minus the fitted purse model), champion_total (champion_check.csv),
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
    (1972, "source_error", "nascaR.data Pts column", "", "", "Pts hold rank points only (max 100 in 1972, 125 in 1973); official totals add distance points per lap. Rebuilt in points_1972.csv / points_1973.csv.", "cup_series.parquet; Wikipedia points-systems page"),
]
for m in manual: add(*m)

rows.sort(key=lambda r: (r[0], r[1], str(r[2])))
with open(os.path.join(HERE, "discrepancies.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["season", "kind", "subject", "expected", "found", "difference", "detail", "sources"]); w.writerows(rows)
print(len(rows), "rows;", dict(collections.Counter((r[1]) for r in rows)))
print("by season:", dict(sorted(collections.Counter(r[0] for r in rows).items())))
