SELECT
  r.driver AS "driver",
  COUNT(*) AS "starts",
  SUM(r.finish = 1) AS "wins",
  SUM(r.finish <= 5) AS "top5",
  ROUND(AVG(r.finish), 2) AS "avg_finish",
  MIN(r.season) AS "first_season",
  MAX(r.season) AS "last_season"
FROM results r LEFT JOIN season_info si ON si.season = r.season
WHERE r.track LIKE :track
GROUP BY r.driver
HAVING SUM(r.finish = 1) >= :v1
ORDER BY "wins" DESC, "avg_finish" ASC
LIMIT :limit
