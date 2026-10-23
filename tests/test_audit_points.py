#!/usr/bin/env python3
"""python tests/test_audit_points.py   (needs pyarrow)
Runs audit_points.py on a small synthetic file with known problems and checks what it reports."""
import csv, json, os, subprocess, sys, tempfile
import pyarrow as pa, pyarrow.parquet as pq

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TABLE = {1: 175, 2: 170, 3: 165, 4: 160}
rows = []      # Season, Race, Driver, Finish, Pts
# 1990: one fixed table; race 2 has a +5 bonus, race 3 a +10 bonus, race 4 a -20 penalty on 4th, race 5 an empty Pts
for race in range(1, 7):
    for fin, drv in enumerate(["A", "B", "C", "D"], 1):
        pts = TABLE[fin]
        if race == 2 and fin == 2: pts += 5
        if race == 3 and fin == 1: pts += 10
        if race == 4 and fin == 4: pts -= 20
        if race == 5 and fin == 3: pts = None
        rows.append((1990, race, drv, fin, pts))
# 1955: points scale with the race (winner 100, 150, 120, 200), same order inside each race;
# in race 3 the winner has far fewer points than the runner-up
for race, scale in enumerate([100, 150, 120, 200], 1):
    for fin, drv in enumerate(["A", "B", "C"], 1):
        pts = scale - 10 * (fin - 1)
        if race == 3 and fin == 1: pts = 60
        rows.append((1955, race, drv, fin, pts))

with tempfile.TemporaryDirectory() as tmp:
    src, off, out = os.path.join(tmp, "c.parquet"), os.path.join(tmp, "official.json"), os.path.join(tmp, "out")
    pq.write_table(pa.table({"Season": [r[0] for r in rows], "Race": [r[1] for r in rows], "Driver": [r[2] for r in rows],
                             "Finish": [r[3] for r in rows], "Pts": pa.array([r[4] for r in rows], pa.float64())}), src)
    # official 1990 totals: A really has 1060 + 10 (bonus) = 1060? compute below; B is deliberately 1 point off
    json.dump({"1990": [[1, "A", 175 * 6 + 10], [2, "B", 170 * 6 + 5 + 1]]}, open(off, "w"))
    r = subprocess.run([sys.executable, os.path.join(root, "audit_points.py"), src, "--official", off, "--out", out],
                       capture_output=True, text=True)
    if r.returncode: sys.exit(r.stdout + r.stderr)
    print(r.stdout)
    seasons = {int(x["season"]): x for x in csv.DictReader(open(os.path.join(out, "points_audit_seasons.csv")))}
    odd = list(csv.DictReader(open(os.path.join(out, "points_audit_rows.csv"))))
    s90, s55 = seasons[1990], seasons[1955]
    assert s90["missing_pts"] == "1" and s90["negative_pts"] == "0"
    assert s90["win_pts_distinct"] == "2" and s90["win_pts"] == "175-185"          # fixed table + a +10 bonus
    assert s90["odd_rows"] == "1", s90                                              # only the -20 penalty on 4th
    pen = [o for o in odd if o["season"] == "1990"]
    assert len(pen) == 1 and pen[0]["driver"] == "D" and pen[0]["race"] == "4" and pen[0]["pts"] == "140", pen
    assert s90["vs_official"] == "1 of 2 differ" and s90["official_diffs"].startswith("b:"), s90
    assert s55["table_fit"].startswith("n/a") and s55["win_pts_distinct"] == "4", s55    # points vary by race
    bad = [o for o in odd if o["season"] == "1955"]
    assert len(bad) == 1 and bad[0]["race"] == "3" and bad[0]["driver"] == "A", bad       # winner trails the runner-up
    print("audit_points OK")
