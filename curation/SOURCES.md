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
- **Method:** `derive_points_prize.py` computes each result row's points from its purse and finishing position.
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

## final_standings_<season>.csv and WIKIPEDIA_SUMMARY.md

Final drivers' standings parsed from the Wikipedia season articles for 1950-1955, 1957, 1960 and 1974 by
`fetch_wikipedia_standings.py` (CC BY-SA 4.0; each row names the article section and fetch date). They are
reference totals for checking, not used to fill `Pts`, except for 1950 where they feed the reconcile adjustments.
See `WIKIPEDIA_SUMMARY.md` for what each season's article provides and what is still missing.

## 1949 cross-check, 1972-73 and champions

- `reconcile_1949.py`: the Reddit chart totals were compared with the 1949 Wikipedia article (a second, independent
  source): 67 of 74 drivers identical. The seven differences match the chart's own notes (an 84-point Rice/Dunaway transfer,
  Langhorne recording errors, penalties). Ten "1949 reconcile" entries in `adjustments.json` bring totals to the article.
- `points_1972.csv`, `points_1973.csv`: nascaR.data `Pts` holds only rank points in those years; rank plus distance points
  (rates from Wikipedia's *List of NASCAR points scoring systems*) reproduces Petty's 1972 total exactly. Rows carry override=1.
  Reconcile entries (1972: 43, 1973: 36) use `final_standings_1972.csv` and `final_standings_1973.csv`.
- `champions_points.csv` is from Wikipedia's *List of NASCAR Cup Series champions* (CC BY-SA 4.0); the Racing-Reference URL
  in each row is the page Wikipedia cites. It was not fetched; it is recorded for hand checking.

## points_1951.csv (derived)

- **Inputs, all from Wikipedia (CC BY-SA 4.0):** the 41 race purses in the schedule table of *1951 NASCAR Grand National Series*
  (`race_purses_1951.csv`), the prize-money scale (as for 1950), and the article's Drivers' championship (top 10) plus its
  collapsed continuation table (places 11-75): 75 drivers in `final_standings_1951.csv`.
- **Method:** `derive_points_prize.py 1951`. The rule was found by fitting: with all 41 winner-point values free, the
  winner's points land on 200 for the typical $3,300-3,900 purse (the points-systems page says most races were worth 200),
  and one parameter (round the purse up from $350) reproduces that almost as well as 41 free values. The tail below 14th
  place (0.8% of the winner's points down to 26th) was fitted too. Because these parameters were fitted on the same totals
  they are checked against, the per-race values are approximate (mean error about 15 points per driver) and every listed
  driver gets a reconcile entry in `adjustments.json`.
- **Zeroed placeholders:** twelve drivers the rule scores above the table's lowest listed total (120) are missing from it, among
  them Marshall Teague, Hershel McGriff, Curtis Turner, Leon Sales and Red Byron. The article does not say why. They are
  zeroed (flagged in `adjustments.json`) until real totals are found.
- Three race winners had `Pts` of 0 in the data file; those rows carry `override=1`.

## race_purses_1952.csv and per_race_points_wikipedia.csv

- `race_purses_1952.csv`: the Purse column of the race table in Wikipedia's *1952 NASCAR Grand National Series* (CC BY-SA 4.0).
  Race 33's purse ($3,820) sits on a wrapped line in the article source.
- `per_race_points_wikipedia.csv`: the results table of Wikipedia's *1957 Virginia 500* (finish, driver, points, winnings), the only
  per-race article from 1949-1961 with a filled points column. See WIKIPEDIA_SUMMARY.md.

## race_purses_1957.csv

Transcribed by hand from a screenshot of Racing-Reference's 1957 season race list (all 53 races: date, site, winner, purse),
supplied by the project owner; the site blocks automated access and nothing was fetched from it. Race 17 (Martinsville,
$12,240) equals the sum of winnings in Wikipedia's *1957 Virginia 500* table, whose winner scored 500 points, so the purse
column is the figure the points were based on. Races 19/20 and 30/31 were run on the same day and are numbered in the opposite
order in nascaR.data; this file uses the data's numbering and keeps the original in `rr_race`. Winners match the data in all 53.

## final_standings_1957.csv

101 drivers' final points and starts, transcribed by hand from screenshots of Racing-Reference's 1957 standings page (supplied by the
project owner; nothing fetched). Points are all multiples of 4 except Billy Myers (4,682); the top ten equal Wikipedia's table; order is
strictly non-increasing. Six listed drivers were not found in the data by name (Chuck Hanson, Bud Erma, Lenny Page, Mike McGreevy,
Lemoin Frey, Bill Jarick), probably spelling variants, and Lucky Long has 2 starts here against 1 in the data.

## discrepancies.csv

Every disagreement found while curating, in one file (`python curation/save_discrepancies.py` regenerates it): 1957 official
totals versus the fitted purse model (37 drivers off by 150+ points, plus name and start-count differences), champion totals that do not
match (13 seasons), the 1949 chart versus Wikipedia (10 drivers), large reconcile entries and zeroed drivers for 1950/51/72/73, and
identity or source errors. `difference` is found minus expected; for 1957 expected is the model and found is the official total.
