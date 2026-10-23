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

- **Inputs, all from Wikipedia (text CC BY-SA):** (1) race purses from the schedule table of *1950 NASCAR Grand
  National Series* (`race_purses_1950.csv`); (2) the prize-money scale from *List of NASCAR points scoring systems*
  (winner = 50 points per $1,000, places 1-10 step down by a tenth, places 11-14 at 0.08/0.06/0.04/0.02 of the
  winner's points); (3) the season article's Drivers' championship table, 62 drivers (`final_standings_1950.csv`,
  parsed from the article text; the table image the project owner supplied matched it except one digit I misread).
- **Method:** `derive_points_1950.py` computes each result row's points from its purse and finishing position.
  Rounding the purse to the nearest $1,000 (a $5,500 purse down) fits the official totals best.
- **Reconciliation:** the rule alone gives Lee Petty 2336 points against his official 1590 (a 746-point gap). The article says
  NASCAR deducted 809 points from Petty for racing in a non-NASCAR-sanctioned event, and other drivers lost points the same way; the 63-point difference is consistent with points below 14th place.
  Official totals also include points below 14th place, which the rule does not model (the article says the last
  scoring place varied by race). `adjustments.json` therefore has a "1950 reconcile" entry per driver in the
  official table, equal to the official total minus the rule-based sum. Per-race values are rule-based, so a
  driver's *path* through the season is approximate even though the final totals match.
- **Drivers with no official points:** the article lists Red Byron and Glenn Dunaway as having all points deducted and
  Hershel McGriff as scoring none; they are zeroed. Otis Martin is simply absent from the top-65 table (under 57.5);
  his exact total is unknown and he is zeroed as a placeholder.
- **Not checked:** the points awarded below 14th place in individual races.
- Two result rows in the data file hold a `0` where the rule gives points (Red Harvey's 2nd at Dayton, Jack Smith's 2nd
  at North Wilkesboro); those rows carry `override=1` in `points_1950.csv`.
