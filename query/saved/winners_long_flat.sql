SELECT
  r.driver AS "driver",
  SUM(r.finish = 1) AS "wins",
  COUNT(*) AS "starts",
  ROUND(1.0 * SUM(r.finish = 1) / COUNT(*), 3) AS "win_rate",
  MIN(r.season) AS "first_season",
  MAX(r.season) AS "last_season"
FROM results r LEFT JOIN season_info si ON si.season = r.season
WHERE r.series = :series
  AND r.track_type = :v1
  AND r.banking = :v2
GROUP BY r.driver
HAVING SUM(r.finish = 1) >= :wins
ORDER BY "wins" DESC, "starts" ASC
LIMIT :limit
