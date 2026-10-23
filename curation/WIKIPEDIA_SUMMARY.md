# Early-season points: what Wikipedia provides, and what is in this repo

The nascaR.data `Pts` column is blank for most of 1949-1961 and all of 1974 (about 10,000 result rows; see
`python audit_points.py`). This note records what the matching Wikipedia season articles contain, what was added
under `curation/`, and what is still missing. Wikipedia text is CC BY-SA 4.0; every CSV names its article and fetch
date. Rebuild or extend the references with `python curation/fetch_wikipedia_standings.py <season> ...`.

## How points were awarded (from Wikipedia's "List of NASCAR points scoring systems")

| Seasons | System |
|---|---|
| 1949-1951 | By race purse: winner gets 50 points per $1,000. Top 14 score (places 1-10 step down by a tenth of the winner's points, 11-14 by 0.08/0.06/0.04/0.02), occasional points lower, half points common. The page says reported purses are inconsistent. |
| 1952-1967 | By purse, spread over the top 25 (a $4,000 purse: 200 for 1st, 8 fewer per place down to 8 for 25th). No general formula is given for other purses. |
| 1968-1971 | By race length (no gaps in the data). |
| 1972-1973 | Rank points plus distance points (no gaps). |
| 1974 | Earnings: race winnings multiplied by races started, divided by 1,000. |

The 1949-1967 systems depend on each race's purse, and 1974 on each driver's earnings. Neither is in the results data,
which is why the blanks cannot be recomputed from finishing positions alone.

## Season by season

Blank = result rows with no `Pts` in the data file. "Standings" is the article's final drivers' table.

| Season | Races | Blank rows | Article | Standings in article | Purses in article | Status in this repo |
|---|---|---|---|---|---|---|
| 1949 | 8 | 210 of 210 | not parsed | not used | no | **Filled** per race from the Reddit chart (`points_1949.csv`, see SOURCES.md); champion total checks out (Byron 842.5) |
| 1950 | 19 | 572 of 576 | yes | 62 drivers (`final_standings_1950.csv`) | yes, all 19 | **Derived** per race from purses and reconciled to the standings (`points_1950.csv`, adjustments) |
| 1951 | 41 | 1,283 of 1,286 | yes | top 10 (`final_standings_1951.csv`) | yes, all 41 | Reference only. The 1950 rule leaves residuals of hundreds of points under every rounding rule tried, so no per-race points were derived |
| 1952 | 34 | 927 of 938 | yes | top 20 (`final_standings_1952.csv`) | a few, in race summaries | Reference only |
| 1953 | 37 | 942 of 958 | yes | top 20 (`final_standings_1953.csv`) | no | Reference only. The article lists Turner (3373) at 10th behind Lewallen (3208) at 9th, probably an article typo, kept as published |
| 1954 | 37 | 1,125 of 1,134 | yes | 212 drivers (`final_standings_1954.csv`) | no | Reference only |
| 1955 | 45 | 83 of 1,179 | yes | 52 drivers (`final_standings_1955.csv`) | no | Reference only; data mostly present |
| 1956 | 56 | 1,503 of 1,519 | yes | **none found** | none per race | Nothing available from the article |
| 1957 | 53 | 1,305 of 1,313 | yes | top 10 with earnings (`final_standings_1957.csv`) | no | Reference only |
| 1958 | 51 | 499 of 1,401 | **no article** (the title redirects) | none | no | Nothing available |
| 1959 | 44 | 545 of 1,187 | yes | **none found** | no | Nothing available |
| 1960 | 44 | 113 of 1,195 | yes | 151 drivers (`final_standings_1960.csv`) | no | Reference only; data mostly present |
| 1961 | 52 | 16 of 1,414 | yes | **none found** | no | Nothing available |
| 1974 | 30 | 1,073 of 1,073 | yes | 138 drivers (`final_standings_1974.csv`) | no | Reference only; scoring needs earnings, which are not in the data |

## Checks

- **Parse check:** champions and top totals match what I know: Flock 6858.5 (1952), Thomas 8460 (1953), Petty 8649
  (1954), Flock 9596 (1955), Baker 10,716 (1957), White 21,164 (1960), Petty 5,037.75 (1974).
- **Data check:** for 1955 and 1960, every driver whose results rows all have points sums to exactly the official total.
  So the reference tables and the data agree wherever both exist; the differences come only from blank rows.
- **1951:** the article's totals include fractions (Thomas 4,208.45), so the scale was not a clean rounded table. Not reproduced.

## What could still be done

1. **Single-gap recovery.** Where a driver has exactly one blank row, it equals the official total minus the rest. About
   56 rows in 1955 and 1960 could be filled this way (roughly 40 pass a plausibility check against the same race's
   other finishers). Not done yet.
2. **Purses for 1951-1957 and 1960s.** Per-race purses would allow the 1950 method for 1951-1957 if the 1951 scale
   problem is understood. They need a source that permits reuse (Racing-Reference and Driver Averages restrict automated
   access; hand lookups are fine).
3. **1956, 1958, 1959, 1961.** Final standings are not on the Wikipedia pages checked; they would need another source.
4. **1974.** Needs per-driver race earnings.
