# Curation sources

`points_*.csv` hand-entered per-race points for seasons where the nascaR.data `Pts` column is blank.
Columns: `season, race, finish, driver_in_source, pts`. Rows are matched to results by season, race and
finishing position (not name); `driver_in_source` is the spelling used by the source, kept for review.
`build_dashboard.py` fills only blank `Pts` and never overrides a value from the data file
(`--no-curation` ignores these files).

## points_1949.csv

- **Source:** "1949 NASCAR Strictly Stock Series Points", a race-by-race points chart by *Diecast Charv*
  (provided by the project owner as an image; original URL and licence not recorded. **TODO: add the link and
  confirm reuse terms.**) Transcribed by hand from the image on 2026-10-23, 8 races, 208 rows. Race 8 positions
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
