SELECT
  r.driver AS "driver",
  r.season AS "season",
  COUNT(*) AS "starts",
  SUM(r.finish = 1) AS "wins",
  SUM(r.finish <= 5) AS "top5",
  ROUND(1.0 * SUM(r.finish <= 5) / COUNT(*), 3) AS "top5_rate",
  SUM(r.finish <= 10) AS "top10",
  MAX(si.is_partial) AS "is_partial"
FROM results r LEFT JOIN season_info si ON si.season = r.season
WHERE r.series = :series
GROUP BY r.driver, r.season
HAVING SUM(r.finish = 1) = :wins
ORDER BY "top5" DESC, "top5_rate" DESC, "top10" DESC
LIMIT :limit
