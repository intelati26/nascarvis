#!/usr/bin/env python3
"""Collect every discrepancy found while curating early-season points into curation/discrepancies.csv.
Run from the repo root:  python curation/save_discrepancies.py

Rows (kind): standings_vs_model (1957: Wikipedia's total minus the fitted purse model), standings_vs_data (1955 and 1960: every driver
whose data total differs from Wikipedia's standings; 1955, 1960, 1966, 1970, 1971 and 1975-2003), champion_total (champion_check.csv),
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
    if abs(d) >= 150: note += "Wikipedia's total is " + ("HIGHER" if d > 0 else "LOWER") + " than the results support (cause unknown)"
    if abs(d) >= 150 or note:
        add(1957, "standings_vs_model", r["driver"], round(model, 1), off, note.strip("; ") + f" [pos {r['pos']}, {n} starts]", "final_standings_1957.csv; race_purses_1957.csv; fitted tier map in this script")
# (difference here = official - model; the generic column above is found - expected with expected=model, found=official)

# ---- champion check (1949-2003) misses
for r in csv.DictReader(open(os.path.join(HERE, "champion_check.csv"))):
    if r["status"] != "match":
        add(int(r["season"]), "champion_total", r["champion"], float(r["official_pts"]), float(r["data_sum"]),
            f"{r['status']}; blank Pts rows after curation: {r['blank_rows']}", "champions_points.csv (Wikipedia); data + curation")

# Jayski's 1984 standings table (pasted by the project owner): its points column equals the data, its ranking order follows Wikipedia's totals
JAYSKI84 = {}
_jp = os.path.join(HERE, "final_standings_1984_jayski.csv")
if os.path.exists(_jp):
    for _r in csv.DictReader(open(_jp, encoding="utf-8")): JAYSKI84[norm(_r["driver"])] = (int(_r["pts"]), int(_r["pos"]))

# Causes established by hand for single drivers: (season, driver) -> text that replaces the generic "cause unknown"
KNOWN = {
    (1983, "Dick Brooks"): "EXPLAINED: Daytona 500 (race 1, 5th) and Richmond (race 2, 13th) are 0 in nascaR.data; Jayski shows 160 and 124 (reported by the project owner; page not fetched). Both equal the scoring formula, and with them the data total equals Wikipedia's. Restored in points_1983.csv",
    (1989, "Terry Fisher"): "EXPLAINED (cause of the 4 unknown): Sonoma, 11 Jun 1989 (race 12), finished 25th with 0 in nascaR.data (Driver Averages results page supplied by the project owner); the scoring formula gives 88 for 25th, restored. Wikipedia's final total is 84, so a -4 standings adjustment is in adjustments.json (race and reason not known; the Wikipedia figure may itself be a typo)",
    (2000, "Jeff Gordon"): "EXPLAINED: all 34 points races match a Driver Averages results page supplied by the project owner (finish and points) and sum to 4,461; Wikipedia's total is exactly 100 lower because of a penalty. Jayski, 13 Sep 2000, \"Gordon's engine problem update 6: the penalty, the appeal, the reactions\" https://www.jayski.com/2000/09/13/gordons-engine-problem-update-6-the-penalty-the-appeal-the-reactions/ says (text quoted by the project owner; the page itself was not fetched, the site returned 403): in addition to the fine, driver Jeff Gordon (#24) loses 100 driver points and 100 owner points are taken from team owner Rick Hendrick. The race it concerns and the appeal result are not recorded here; Wikipedia's total shows the deduction stood. Added to adjustments.json from race 26, the first race after the announcement",
    (2000, "Jeff Burton"): "EXPLAINED (reported by the project owner; source and race still to be recorded): all 34 points races match a Driver Averages results page supplied by the project owner (finish and points), sum to 4,836, and every row also equals the 2000 formula (base points by finish + 5 for leading a lap + 5 for most laps led); Wikipedia's total is exactly 5 higher. The project owner reports references to a scoring error that was corrected later; that fits a 5-point credit (such as a lead-lap bonus) added after the race rows were published. Source and race not yet recorded; the +5 is in adjustments.json at the last race (34) because the race is unknown",
    (2002, "Dale Jarrett"): "EXPLAINED: 25-point penalty, #88, crew chief Todd Parrott, New Hampshire 21 Jul (race 19), 1/8th of an inch too low, $25,000 fine; the Gainesville Sun headline of 23 Jul 2002 reads \"Quarter-inch costs Jarrett 25 points\" (the table says 1/8th). Source: Jayski 2002 penalties table (https://www.jayski.com/nascar-cup-series/2002-nascar-penalties/, pasted by the project owner; page not fetched). Wikipedia's total is exactly 25 below the race rows. In adjustments.json from race 20, the first race after the announcement",
    (2002, "Jimmie Johnson"): "EXPLAINED: 25-point penalty, #48, crew chief Chad Knaus, Daytona 6 Jul (race 17), offset mounting bolts (NASCAR did not approve the location of some bolts), $25,000 fine; announced in the same Gainesville Sun article as Jarrett's, 23 Jul 2002. Source: Jayski 2002 penalties table (https://www.jayski.com/nascar-cup-series/2002-nascar-penalties/, pasted by the project owner; page not fetched). Wikipedia's total is exactly 25 below the race rows. In adjustments.json from race 20, the first race after the announcement",
    (2002, "Jeff Green"): "EXPLAINED: 25-point penalty, #30, crew chief Todd Berrier, Richmond 7 Sep (race 26), unapproved left front spring, $5,000 fine. Source: Jayski 2002 penalties table (https://www.jayski.com/nascar-cup-series/2002-nascar-penalties/, pasted by the project owner; page not fetched). Wikipedia's total is exactly 25 below the race rows. In adjustments.json from race 27, the first race after the announcement",
    (2002, "Rusty Wallace"): "EXPLAINED: 25-point penalty, #2, crew chief Billy Wilburn, Talladega 6 Oct (race 30), unapproved spoiler, $25,000 fine. Source: Jayski 2002 penalties table (https://www.jayski.com/nascar-cup-series/2002-nascar-penalties/, pasted by the project owner; page not fetched). Wikipedia's total is exactly 25 below the race rows. In adjustments.json from race 31, the first race after the announcement",
    (2002, "Ward Burton"): "EXPLAINED: 25-point penalty, #22, crew chief Frank Stoddard, Martinsville 20 Oct (race 32), unapproved front springs, $10,000 fine. Source: Jayski 2002 penalties table (https://www.jayski.com/nascar-cup-series/2002-nascar-penalties/, pasted by the project owner; page not fetched). Wikipedia's total is exactly 25 below the race rows. In adjustments.json from race 33, the first race after the announcement",
    (1999, "Ron Fellows"): "EXPLAINED, source error: his only 1999 points race was Watkins Glen, 15 Aug (race 21): 2nd place, 3 laps led, 175 points on a Driver Averages results page supplied by the project owner. 175 = 170 for 2nd + 5 for leading a lap, which is what the data has; Wikipedia's standings table gives 174, which does not fit the scoring (likely a typo). No adjustment",
    (1993, "Trevor Boys"): "EXPLAINED, source error: his only 1993 start was Pocono, 13 Jun (race 13, Champion Spark Plug 500): 35th, 1 lap led. Driver Averages shows 63 points (per the project owner), the same as the data: 63 = 58 for 35th + 5 for leading a lap. Wikipedia's table gives 58, the total without the lead-lap bonus, which looks like an error in the table. No adjustment",
    (1993, "Ken Schrader"): "NARROWED, cause open: the Driver Averages page supplied by the project owner (30 points races) matches the data race for race and sums to 3,715, and every one of his rows follows the 1993 scoring formula (so does every row of 1993). Wikipedia's table gives 3,714, one point lower, which no race row can produce; a table error is likely, but no adjustment",
}

_NOTE_1981 = ("PROBABLE SOURCE ERROR in Wikipedia's total, consistent with a race 30 scoring error but not shown to be one (no running total seen; cause unknown): the data total is exactly 3 above Wikipedia's, one finishing place on the scale below 12th. "
              "In race 30 (Atlanta Journal 500) all 12 drivers who finished 12th or better match Wikipedia's totals exactly, and 23 of the 24 who finished 13th or lower and scored points are exactly 3 over (McDuffie 4 over; Chuck Bown, 15th, is the one exact match, unexplained). "
              "A results page supplied by the project owner scores the race as the data does (Brooks 13th = 124, Speed 14th = 121, and so on), so Wikipedia's table is the outlier, and the pattern is what it would look like if it scored 13th and lower one place down. Race 31 is ruled out (7 of the 22 never ran it). The single-race reading is an inference from this pattern; a season-wide cause is not excluded. "
              "Finishing positions are trusted over the site's season totals (the running totals do not add up on the site's own driver pages, per the project owner). The page also shows formula points for Anderson, Wallace, Bodine and Bailey, who have 0 in the standings (Wallace and Bodine's Wikipedia's totals equal the data without race 30). Data left as is")
KNOWN.update({(1981, n): _NOTE_1981 for n in ['Benny Parsons', 'Buddy Arrington', 'D.K. Ulrich', 'Dale Earnhardt', 'Dave Marcis', 'Delma Cowart', 'Dick Brooks', 'Gary Balough', 'Harry Gant', 'James Hylton', 'Jimmy Means', 'Joe Ruttman', 'Johnny Rutherford', 'Lake Speed', 'Morgan Shepherd', 'Richard Petty', 'Ricky Rudd', 'Ron Bouchard', 'Tim Richmond', 'Tommy Ellis', 'Tommy Gale', 'Travis Tiller']})
KNOWN[(1993, "Ken Bouchard")] = ("EXPLAINED: the data's race 22 row (Mountain Dew Southern 500, 40th, status did not start, 0 laps) scores 43 points, but Racing-Reference's 1993 season page for Bouchard lists only races 9, 16 and 17 "
    "(43 + 76 + 88 = 207, Wikipedia's total) and does not list race 22 at all, not even as a DNQ (its DNQ/withdrawn list is races 11, 12, 15 and 20): https://www.racing-reference.info/driver-season-stats/bouchke01/1993/W (screenshot supplied by the project owner; page not fetched). "
    "The row is a phantom and is set to 0 in points_1993.csv")
KNOWN[(1993, "Mike Skinner")] = ("EXPLAINED (Wikipedia error, probably a typo): one start, Mountain Dew Southern 50 (Darlington), 35th, which the scoring formula scores 58, the data's value. "
    "Wikipedia's table has 55. The project owner reports 58 in several other places and that 55 is explainable as a fat-finger slip of 58 (5 sits below 8 on a keypad). The data is kept")
KNOWN[(1981, "J.D. McDuffie")] = _NOTE_1981 + ". McDuffie is 4 over, not 3: the extra 1 is not explained"
KNOWN[(1981, "Dick Brooks")] = (_NOTE_1981 + ". Brooks in detail: Driver Averages shows 297 (reported by the project owner; the same source as the data, so not independent) against Wikipedia's 294. "
    "His Daytona 500 (16th, formula 120) and Rockingham American 500 (21st, formula 100) are 0 in both and are not in Wikipedia's total either, so they stay zero. "
    "294 = 118 + 55 + 121, 121 being the formula score for 14th at Atlanta, but the results page and Jayski score him 124 there as 13th")

# ---- full field: every driver in Wikipedia's standings whose data total differs (seasons where nascaR.data is mostly present)
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
        why = (f"{b} blank Pts row{'s' if b != 1 else ''} in the data" + ("; the gap is recoverable if it is the only missing value" if b == 1 else "")) if b else "no blank rows: the data total differs from Wikipedia's (cause unknown)"
        if season == 1955 and not b:                                    # 1955 has a verified scale, so rows can be tested against it
            bad = [x for x in scale55.get(k, []) if abs(x[2] - x[3]) > 1e-6]
            if float(r["pts"]) <= 1: why = "Wikipedia's total is 1: the driver's points appear to have been removed (same pattern as 1950 Byron and Dunaway)"
            elif bad: why = "data row(s) off the 1955 scale: " + "; ".join(f"race {x[0]} finish {x[1]} data {x[2]:g}, scale {x[3]:g}" for x in bad)
            elif abs(abs(d) - round(abs(d), -2)) < 1e-6: why = f"no data row breaks the 1955 scale; Wikipedia's total is exactly {abs(d):g} {'lower' if d > 0 else 'higher'}: looks like a points deduction"
        if season == 1984 and norm(names[k]) in JAYSKI84:
            why += f"; Jayski's standings list {JAYSKI84[norm(names[k])][0]} (equal to the data) at position {JAYSKI84[norm(names[k])][1]}"
        if (season, names[k]) in KNOWN: why = KNOWN[(season, names[k])]
        add(season, "standings_vs_data", names[k], float(r["pts"]), round(totals[k], 2), why + f" [Wikipedia pos {r['pos']}]", "final_standings_%d.csv (Wikipedia); data + curation" % season)

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
    (1999, "source_error", "Ron Fellows (Wikipedia 1999 standings)", 175, 174, "Wikipedia's table gave 174; his single points race (Watkins Glen, 2nd, 3 laps led) scores 175 = 170 + 5 under the 1999 rules, and a Driver Averages results page supplied by the project owner shows 175. CORRECTED: the project owner fixed the Wikipedia table; a re-fetch (23 Oct 2026) shows 175 and final_standings_1999.csv was refreshed.", "final_standings_1999.csv; Driver Averages results page supplied by the project owner"),
    (1984, "source_error", "Mike Alexander (Richmond, 26 Feb 1984, race 2)", 100, 0, "nascaR.data and a Driver Averages results page supplied by the project owner show 0 points for his 21st place (394 laps, running); Jayski's race page for the Miller High Life 400 at Richmond has the points as expected, 100 (reported by the project owner; the page was not fetched, Jayski refuses automated requests). His Wikipedia's total (1,862) is exactly 100 higher than the data. Restored to 100 in points_1984.csv.", "points_1984.csv; https://www.jayski.com/race-results/1984-nascar-winston-cup-series/miller-high-life-400-richmond/; final_standings_1984.csv"),
    (1984, "identity", "Jimmy Hensley (four 1984 starts: races 2, 8, 23, 25)", 394, 0, "NOT restored, by decision: the Pts column shows championship points as they count in the standings. Jayski's race pages show the finishing-position score for him (97, 103, 97, 97; reported by the project owner) but Jayski's 1984 standings list him at 0, like the other drivers not running for championship points (Gene Coyle, Laurent Rioux and about a dozen more), so nascaR.data's zeros are right for the standings. A zero in Pts can therefore mean \"does not count\", not a missing score.", "cup_series.parquet; final_standings_1984_jayski.csv; Jayski race pages (not fetched)"),
    (1993, "source_error", "Trevor Boys (Wikipedia 1993 standings)", 63, 58, "Wikipedia's table gives 58; Driver Averages shows 63 for his one start (35th + 5 for the lap led), as does the data. Open on Wikipedia: if it is corrected, re-run fetch_wikipedia_standings.py 1993 and the checks.", "final_standings_1993.csv; Driver Averages Driver Averages results page supplied by the project owner"),
    (1972, "source_error", "nascaR.data Pts column", "", "", "Pts hold rank points only (max 100 in 1972, 125 in 1973); Wikipedia's totals add distance points per lap. Rebuilt in points_1972.csv / points_1973.csv.", "cup_series.parquet; Wikipedia points-systems page"),
]
for m in manual: add(*m)

rows.sort(key=lambda r: (r[0], r[1], str(r[2])))
with open(os.path.join(HERE, "discrepancies.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["season", "kind", "subject", "expected", "found", "difference", "detail", "sources"]); w.writerows(rows)
print(len(rows), "rows;", dict(collections.Counter((r[1]) for r in rows)))
print("by season:", dict(sorted(collections.Counter(r[0] for r in rows).items())))

# The hand-written notes, one row per driver, for write_points_edits.py (a closed gap no longer has a row in discrepancies.csv).
with open(os.path.join(HERE, "known_notes.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["season", "driver", "note"])
    for (s, d), why in sorted(KNOWN.items()): w.writerow([s, d, why])
