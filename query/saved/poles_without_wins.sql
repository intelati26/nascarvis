SELECT
  r.driver AS "driver",
  COUNT(*) AS "starts",
  SUM(r.start = 1) AS "poles",
  SUM(r.finish = 1) AS "wins",
  SUM(CASE WHEN r.start >= :v1 THEN 1 ELSE 0 END) AS "starts_20th_or_worse"
FROM results r LEFT JOIN season_info si ON si.season = r.season
GROUP BY r.driver
HAVING SUM(r.finish = 1) = :v2
  AND SUM(r.start = 1) >= :v3
ORDER BY "poles" DESC, "starts" DESC
LIMIT :limit
