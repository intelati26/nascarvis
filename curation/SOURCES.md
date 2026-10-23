# Curation sources

`points_*.csv` hand-entered per-race points for seasons where the nascaR.data `Pts` column is blank.
Columns: `season, race, finish, driver_in_source, pts`. Rows are matched to results by season, race and
finishing position (not name); `driver_in_source` is the spelling used by the source, kept for review.
`build_dashboard.py` fills only blank `Pts` and never overrides a value from the data file
(`--no-curation` ignores these files).

## points_1949.csv

- **Source:** "1949 NASCAR Strictly Stock Series Points", a race-by-race points chart by *Diecast Charv*
  (posted on Reddit, r/NASCAR, "1949 NASCAR points race by race breakdown (errors...)":
  <https://old.reddit.com/r/NASCAR/comments/gzxfz5/1949_nascar_points_race_by_race_breakdown_errors>;
  the image was provided by the project owner. The author has not been contacted and no reuse licence is stated
  in what we have. The points are factual figures, credit stays with Diecast Charv, and anyone reusing this file
  should check the thread and ask the author if in doubt.) Transcribed by hand from the image on 2026-10-23, 8 races, 208 rows. Race 8 positions
  21 and 22 are not on the chart; they are entered as 0 (below the last points position).
- **Checks:** finishing order matches nascaR.data in all 8 races. Red Byron sums to 842.5, his official 1949
  championship total. Eleven names differ in spelling (for example Skimp Jersey/Hersey) and three differ at a
  position (race 3 #28, race 4 #41, race 5 #15); positions were trusted.
- **Scoring (per the chart):** winner's points = race purse / 20. Places 1-10 earn W, 0.9W ... 0.1W. Places
  beyond 10 are not formula-based, and the chart records them as published. Purses are the chart's "accepted"
  amounts; it notes some "believed true" purses differ.
- **Chart's own caveats:** two recording errors at Langhorne (A. Bonnell, B. Flock), 84 points moved from Sam
  Smith to Glenn Dunaway for unknown reasons, Bill Blair penalised 45 points, Sara Christian lost the 8 points
  from Charlotte, Don Rogala lost the 20 from Heidelberg, and Bobby Greene's two points finishes could not be
  verified (totals may be off by -1 to +0.5). Season sums can therefore differ slightly from official standings.

## points_1950.csv (derived, not transcribed)

- **Inputs:** (1) race purses from the schedule table of Wikipedia's *1950 NASCAR Grand National Series*
  (`race_purses_1950.csv`); (2) the prize-money points scale from Wikipedia's *List of NASCAR points scoring systems*
  (winner = 50 points per $1,000, places 1-10 step down by a tenth, places 11-14 at 0.08/0.06/0.04/0.02 of the
  winner's points); (3) the official 1950 final standings table from the same season article, top 26 drivers
  (`final_standings_1950.csv`; the table image was supplied by the project owner). Wikipedia text is CC BY-SA.
- **Method:** `derive_points_1950.py` computes each result row's points from its purse and finishing position.
  Rounding the purse to the nearest $1,000 (a $5,500 purse down) fits the official totals best.
- **Reconciliation:** the rule alone gives Lee Petty 2336 points (official 1550). The official totals include
  deductions for taking part in non-NASCAR-sanctioned races (per the article) and points below 14th place that
  the rule does not model. `adjustments.json` therefore carries one "1950 reconcile" entry per driver in the
  official top 26, equal to the official total minus the rule-based sum (-786 for Petty, -594.5 for Tim Flock,
  -536 for Blair, up to +51.5 below-14th points for Hough). Per-race values are rule-based, so a driver's *path*
  through the season is approximate even though the final totals match.
- **Absent drivers:** Red Byron, Glenn Dunaway, Hershel McGriff and Otis Martin score above 57.5 by the rule but are
  not in the official top-65 table (everyone listed there has 57.5 or more). Their true totals are unknown and are
  zeroed as a placeholder (flagged in `adjustments.json`).
- **Not yet checked:** official drivers below 26th place (not transcribed), and the places-15-and-below scores.
- Two result rows in the data file hold a `0` where the rule gives points (Red Harvey's 2nd at Dayton, Jack Smith's 2nd
  at North Wilkesboro); those rows carry `override=1` in `points_1950.csv`.
