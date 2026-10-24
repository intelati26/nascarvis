SELECT
  r.driver AS "driver",
  COUNT(*) AS "starts",
  SUM(r.finish = 1) AS "wins",
  ROUND(AVG(r.finish), 2) AS "avg_finish",
  ROUND(1.0 * SUM(r.finish <= 10) / COUNT(*), 3) AS "top10_rate",
  MIN(r.season) AS "first_season",
  MAX(r.season) AS "last_season"
FROM results r LEFT JOIN season_info si ON si.season = r.season
GROUP BY r.driver
HAVING COUNT(*) >= :min_starts
ORDER BY "avg_finish" ASC
LIMIT :limit
