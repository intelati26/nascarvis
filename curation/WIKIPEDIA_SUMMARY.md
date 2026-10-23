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

## Complete season table, 1949-1974

"Official" is the champion's total from Wikipedia's *List of NASCAR Cup Series champions*; "data" is that driver's summed
`Pts` after the curation in this folder (so 1949, 1950, 1972 and 1973 include the repo's derived values and reconcile
entries; the rest is the unmodified data file). Re-run `python curation/check_champions.py` to regenerate
`champion_check.csv`. The two sources in each row are the Wikipedia article and the Racing-Reference page that
Wikipedia cites for the totals; nothing is fetched from Racing-Reference. "Standings" says how much of the final
standings table the article has (CSV `final_standings_<season>.csv`).

| Season | Champion | Official | Data | Check | Blank rows after curation | Standings | Sources | Notes |
|---|---|---|---|---|---|---|---|---|
| 1949 | Red Byron | 842.5 | 842.5 | **match** | 0 of 210 | 79 drivers | [article](https://en.wikipedia.org/wiki/1949_NASCAR_Strictly_Stock_Series), [racing-reference](http://racing-reference.info/yeardet/1949/W) | Per-race points from the Reddit chart (`points_1949.csv`), checked against the article: 67 of 74 drivers identical, 7 differences explained by the chart's own notes; reconciled to the article (10 entries). |
| 1950 | Bill Rexford | 1,959 | 1,959 | **match** | 0 of 576 | 62 | [article](https://en.wikipedia.org/wiki/1950_NASCAR_Grand_National_Series), [racing-reference](http://racing-reference.info/yeardet/1950/W) | Derived from purses and the prize-money scale, reconciled to the article (49 entries; Petty -809 for an unsanctioned race, Byron and Dunaway all points deducted). |
| 1951 | Herb Thomas | 4,208.45 | 4,208.45 | **match** | 0 of 1286 | 75 drivers | [article](https://en.wikipedia.org/wiki/1951_NASCAR_Grand_National_Series), [racing-reference](http://racing-reference.info/yeardet/1951/W) | Derived per race from the 41 purses (rounded up from $350, flat 0.8% tail to 26th), reconciled to the article's 75-driver table (85 entries, incl. 12 zeroed drivers absent from it). Top 12 order matches. Three source zeros for race winners overridden. |
| 1952 | Tim Flock | 6,858.5 | 0 | no data | 927 of 938 | top 20 | [article](https://en.wikipedia.org/wiki/1952_NASCAR_Grand_National_Series), [racing-reference](http://racing-reference.info/yeardet/1952/W) | Purses for all 34 races are in the article (`race_purses_1952.csv`). Not derived: the top-25 scale with winner's points proportional to purse leaves errors of about 150 points (Tim Flock short by 650) against the 19 listed drivers, too few to fit a better rule. |
| 1953 | Herb Thomas | 8,460 | 0 | no data | 942 of 958 | top 20 | [article](https://en.wikipedia.org/wiki/1953_NASCAR_Grand_National_Series), [racing-reference](http://racing-reference.info/yeardet/1953/W) | Standings only. The article lists Turner (3373) at 10th behind Lewallen (3208), probably an article typo. |
| 1954 | Lee Petty | 8,649 | 0 | no data | 1125 of 1134 | 212 | [article](https://en.wikipedia.org/wiki/1954_NASCAR_Grand_National_Series), [racing-reference](http://racing-reference.info/yeardet/1954/W) | Full standings only. |
| 1955 | Tim Flock | 9,596 | 9,596 | **match** | 35 of 1179 | 52 | [article](https://en.wikipedia.org/wiki/1955_NASCAR_Grand_National_Series), [racing-reference](http://racing-reference.info/yeardet/1955/W) | Race 4 (Daytona Beach road course) had no points for any of its 48 drivers. Flock's win is his only blank row, so the winner's points are 9,596 - 9,246 = **350**; 12 of the 16 checkable drivers' totals then match exactly (`derive_points_1955.py`, `points_1955.csv`). Scale found in 1955: W x (26 - place) / 25, and every starter below 25th scores W / 25. |
| 1956 | Buck Baker | 9,272 | 0 | no data | 1503 of 1519 | none found | [article](https://en.wikipedia.org/wiki/1956_NASCAR_Grand_National_Series), [racing-reference](http://racing-reference.info/yeardet/1956/W) | No standings table in the article. Champion total from the champions list only. |
| 1957 | Buck Baker | 10,716 | 0 | no data | 1305 of 1313 | top 10 | [article](https://en.wikipedia.org/wiki/1957_NASCAR_Grand_National_Series), [racing-reference](http://racing-reference.info/yeardet/1957/W) | Purses of all 53 races (`race_purses_1957.csv`) and a 101-driver standings table (`final_standings_1957.csv`, Racing-Reference screenshot; top 10 equal Wikipedia's). Not derived: see "1957 findings" below. |
| 1958 | Lee Petty | 12,232 | 9,552 | differs | 499 of 1401 | none found | [article](https://en.wikipedia.org/wiki/1958_NASCAR_Grand_National_Series), [racing-reference](http://racing-reference.info/yeardet/1958/W) | No article for the season. Champion total from the champions list only. Data has blanks. |
| 1959 | Lee Petty | 11,792 | 9,032 | differs | 545 of 1187 | none found | [article](https://en.wikipedia.org/wiki/1959_NASCAR_Grand_National_Series), [racing-reference](http://racing-reference.info/yeardet/1959/W) | No standings table. Champion total from the champions list only. Data has blanks. |
| 1960 | Rex White | 21,164 | 21,164 | **match** | 113 of 1195 | 151 | [article](https://en.wikipedia.org/wiki/1960_NASCAR_Grand_National_Series), [racing-reference](http://racing-reference.info/yeardet/1960/W) | Match even with 113 blank rows (the champion's rows are complete). |
| 1961 | Ned Jarrett | 27,272 | 27,282 | differs | 16 of 1414 | none found | [article](https://en.wikipedia.org/wiki/1961_NASCAR_Grand_National_Series), [racing-reference](http://racing-reference.info/yeardet/1961/W) | Data is 10 above the official total (cause unknown). |
| 1962 | Joe Weatherly | 30,836 | 30,836 | **match** | 0 of 1359 | – | [article](https://en.wikipedia.org/wiki/1962_NASCAR_Grand_National_Series), [racing-reference](http://racing-reference.info/yeardet/1962/W) |  |
| 1963 | Joe Weatherly | 33,398 | 31,330 | differs | 0 of 1414 | – | [article](https://en.wikipedia.org/wiki/1963_NASCAR_Grand_National_Series), [racing-reference](http://racing-reference.info/yeardet/1963/W) | Data is 2,068 below the official total with no blanks (cause unknown). |
| 1964 | Richard Petty | 40,252 | 40,252 | **match** | 0 of 1641 | – | [article](https://en.wikipedia.org/wiki/1964_NASCAR_Grand_National_Series), [racing-reference](http://racing-reference.info/yeardet/1964/W) |  |
| 1965 | Ned Jarrett | 38,824 | 38,824 | **match** | 0 of 1495 | – | [article](https://en.wikipedia.org/wiki/1965_NASCAR_Grand_National_Series), [racing-reference](http://racing-reference.info/yeardet/1965/W) |  |
| 1966 | David Pearson | 35,638 | 35,638 | **match** | 0 of 1524 | – | [article](https://en.wikipedia.org/wiki/1966_NASCAR_Grand_National_Series), [racing-reference](http://racing-reference.info/yeardet/1966/W) |  |
| 1967 | Richard Petty | 42,472 | 42,362 | differs | 0 of 1479 | – | [article](https://en.wikipedia.org/wiki/1967_NASCAR_Grand_National_Series), [racing-reference](http://racing-reference.info/yeardet/1967/W) | Data is 110 below the official total with no blanks (cause unknown). |
| 1968 | David Pearson | 3,499 | 3,345 | differs | 0 of 1470 | – | [article](https://en.wikipedia.org/wiki/1968_NASCAR_Grand_National_Series), [racing-reference](http://racing-reference.info/yeardet/1968/W) | Data is 154 below the official total with no blanks (cause unknown). |
| 1969 | David Pearson | 4,170 | 4,170 | **match** | 0 of 1665 | – | [article](https://en.wikipedia.org/wiki/1969_NASCAR_Grand_National_Series), [racing-reference](http://racing-reference.info/yeardet/1969/W) |  |
| 1970 | Bobby Isaac | 3,911 | 3,911 | **match** | 0 of 1551 | – | [article](https://en.wikipedia.org/wiki/1970_NASCAR_Grand_National_Series), [racing-reference](http://racing-reference.info/yeardet/1970/W) |  |
| 1971 | Richard Petty | 4,435 | 4,435 | **match** | 0 of 1646 | – | [article](https://en.wikipedia.org/wiki/1971_NASCAR_Winston_Cup_Series), [racing-reference](https://www.espn.com/racing/standings/_/year/1971) |  |
| 1972 | Richard Petty | 8,701.4 | 8,701.4 | **match** | 0 of 1192 | 120 | [article](https://en.wikipedia.org/wiki/1972_NASCAR_Winston_Cup_Series), [racing-reference](http://racing-reference.info/yeardet/1972/W) | Data `Pts` hold rank points only; the official total adds distance points per lap. Rebuilt (`points_1972.csv`) and reconciled (43 entries). |
| 1973 | Benny Parsons | 7,173.8 | 7,173.8 | **match** | 0 of 1068 | 50 | [article](https://en.wikipedia.org/wiki/1973_NASCAR_Winston_Cup_Series), [racing-reference](http://racing-reference.info/yeardet/1973/W) | Same distance-points issue; rule fits less well (36 larger reconcile entries). |
| 1974 | Richard Petty | 5,037.75 | 0 | no data | 1073 of 1073 | 138 | [article](https://en.wikipedia.org/wiki/1974_NASCAR_Winston_Cup_Series), [racing-reference](http://racing-reference.info/yeardet/1974/W) | Scored by earnings, which the data does not have. |

**1975-2003:** all 29 seasons match exactly (champions list vs data sum). Sources: each season's Wikipedia article
and the Racing-Reference page it cites, both listed in `champions_points.csv`.

Totals for the table: 55 seasons (1949-2003): **43 match**, **6 have no usable data** (1952-54, 1956-57, 1974) and **6 differ**
(1958, 1959, 1961, 1963, 1967, 1968).

## Per-race Wikipedia articles

Wikipedia has individual articles for only a few races per season. Those linked from the 1949-1961 season articles number
about 46 (none for 1952 and 1958; 1-9 for the others: the Southern 500, Wilkes County, Virginia 500, Daytona 500 and similar).
Findings from reading all of them:

- **Per-driver points:** only three have a `Pts` column, and only one has it filled in: the **1957 Virginia 500** (500 for the winner,
  480, 460 ... 40 for 24th). That is exactly the 1952-67 top-25 scale, W x (26 - place) / 25, with W = 500. The 1956 Virginia 500
  and 1960 Daytona 500 have the column but no values. The 24 rows are kept as `per_race_points_wikipedia.csv`.
- **Purses:** a few state the race's total purse or winnings (for example the 1952 Southern 500, $23,855, which also appears in the
  1952 season table). Nothing systematic.
- **Winnings per driver:** some articles list each driver's winnings. That would matter for 1974 (earnings-based) but those
  articles do not exist for 1974's races.

So the per-race articles do not fill any season. They confirm the shape of the 1952-67 scale in one race. The data needed for the
purse-based seasons is the purse of every race: the 1950, 1951 and 1952 season articles provide it, and 1957's came from
Racing-Reference. Having purses is necessary but not sufficient: see the 1952 and 1957 rows.

## What each curation file contains

| File | Content | Source |
|---|---|---|
| `points_1949.csv` | Per-race points, all 8 races | Reddit chart by Diecast Charv (SOURCES.md) |
| `points_1950.csv`, `points_1951.csv`, `race_purses_1950.csv`, `race_purses_1951.csv` | Per-race points derived from purses (rules fitted per season; see `derive_points_prize.py`) | Wikipedia articles and points-systems page |
| `race_purses_1952.csv` | Purses of all 34 races | Wikipedia 1952 article |
| `race_purses_1957.csv` | Purses of all 53 races (4 renumbered to match the data's order for same-day races; `rr_race` keeps the original number) | Racing-Reference season list, screenshot supplied by the project owner |
| `per_race_points_wikipedia.csv` | Real per-driver points for the 1957 Virginia 500 | Wikipedia race article |
| `points_1972.csv`, `points_1973.csv` | Rank points plus distance points, rebuilt from laps and track length | Wikipedia points-systems page |
| `final_standings_<season>.csv` | Official final standings: 1949-1955, 1957, 1960, 1972-1974 (1951 has 75 drivers, the article's collapsed continuation table) | Wikipedia season articles |
| `champions_points.csv` | Champion, starts, wins, points, margin, 1949-2003 | Wikipedia champions list |
| `champion_check.csv` | The check above | generated |
| `fetch_wikipedia_standings.py`, `derive_points_prize.py`, `derive_points_1972_73.py`, `reconcile_1949.py`, `check_champions.py` | Reproducible scripts | |
| `adjustments.json` (repo root) | Reconcile entries: 1949 (10), 1950 (49), 1951 (85), 1972 (43), 1973 (36) | each entry's note says why |

The disagreements behind these rows are collected in `discrepancies.csv` (regenerate with
`python curation/save_discrepancies.py`).

## 1957 findings (what was learned, and why no per-race points were derived)

- The results data is right: Lee Petty's 41 finishes match Racing-Reference race for race, and average start and finish match for the
  twelve top drivers checked; starts, wins and poles match Wikipedia's table for nine of ten (Wikipedia's Petty row is wrong).
- Drivers with a single start pin the scale: the winner's points are **200** for purses up to $4,535 (Eubanks, Joslin, Yiskis, Dodd),
  and **500** for the $13,640 Daytona Beach race (Beauchamp 2nd = 480, Lutz 6th = 400). That, with the 1957 Virginia 500 ($12,240 = 500),
  confirms points = W x (26 - place) / 25.
- A monotone purse-to-W map fitted on 55 well-behaved drivers plus the top five gives 200 (to $4,550), 250 ($4,585-$4,910), 350
  ($6,625-$7,230), 500 ($12,240-$13,640), 750 ($14,250), 1,000 ($15,350-$18,415), 2,100 (Darlington $41,175). Median error 12 points.
- It still leaves large one-sided misses for about 40% of drivers: L. D. Austin, Brownie King and Jim Paschal are 600-1,100 points *below*
  their official totals, while Joe Weatherly, Possum Jones, Mel Larson and Gwyn Staley are 1,000-3,000 *above* (their official totals look
  like points were removed). A tail below 25th place does not explain it. Reconciling these with adjustments would hide a scheme I do not
  understand, so `points_1957.csv` was not created.

## 1955 findings

- Race 4, the Daytona Beach and road course race, has no points for any driver in nascaR.data, and Racing-Reference shows none either. It is
  the only 1955 race like that. Tim Flock won it and has no other blank row, so the winner's points follow from his official total:
  9,596 - 9,246 = 350. A $5,000 purse would give 250 at 5% of the purse; 350 corresponds to about $7,000, and the 1955 purse-to-points bands
  (about $4,000 = 200, $9,000-$10,600 = 600, $28,300 = 1,500) are not a flat 5%, so the actual purse should be read from Racing-Reference.
- 350 was checked against the other drivers' official totals: five drivers' gaps equal 350 x (26 - place) / 25 exactly (Flock 350, Petty 336,
  Turner 308, Eubanks 280, Simpson 28) and none equal the 250 value. Eight finishers from 26th to 44th each gap by exactly 14 = 350 / 25.
- That is the 1955 floor: in the 1955 races that do have points, 136 of 139 finishers 26th or lower scored exactly W / 25 (the other 3 scored zero).
- After deriving race 4 (`derive_points_1955.py`), 45 of the 52 drivers in the official standings match exactly, up from 31. Four of those
  who ran the race still do not (Buck Baker -762, Fonty Flock -8, Mack Hanbury and Jack Choquette); their other rows are nascaR.data as is.

## Findings worth knowing

- **Data and reference agree wherever both are complete.** For 1955 and 1960 every driver whose rows all have points sums to
  exactly the official total, and the 1949 chart agrees with the article for 67 of 74 drivers.
- **1972-73:** the data's `Pts` are rank points only (maximum 100, then 125 per race). The official totals add distance
  points (0.25 to 1.25 per lap by track length). With that rule Petty's 1972 total reproduces to the decimal.
- **Identity:** the data labels race 5 of 1949's 15th place "Bob Apperson"; the chart and Wikipedia both say "Bob Appleton".
- **Unexplained:** 1961 (+10), 1963 (-2,068), 1967 (-110) and 1968 (-154) differ from the official champion total without
  blank rows. The data or the official totals are off; the cause has not been found.

## Still missing

1. **1952-1954, 1956-1957 and 1974** have no per-race points. 1952 has all 34 purses but the scale does not fit yet (see its row);
   1953-57 have no purse table. 1952-67 followed the purse-based top-25 scale, so they would follow from purses the way 1950-51
   do. 1974 needs earnings.
2. **1958 and 1959** have large blank areas and no standings table, only the champion's total.
3. **1955 and 1960** have 83 and 113 blank rows. About 56 of them (one blank per driver) could be filled from the final
   standings; not done.
4. **Official standings below the champion** exist for 1949-1955, 1957, 1960, 1972-1974 only; 1956 and 1958-1959 and 1961-1971
   would need another source. (1952, 1953 and 1957 show only 10-20 drivers; continuation tables were checked.)
