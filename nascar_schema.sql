-- NASCAR points database (SQLite). One file, no server.
--   sqlite3 nascar.db < nascar_schema.sql
PRAGMA foreign_keys = ON;

CREATE TABLE series (
  series_id   INTEGER PRIMARY KEY,
  name        TEXT NOT NULL UNIQUE          -- Cup, O'Reilly, Truck
);

CREATE TABLE drivers (
  driver_id   INTEGER PRIMARY KEY,
  name        TEXT NOT NULL,
  source_id   TEXT                          -- id from your data source, for matching
);

CREATE TABLE races (
  race_id     INTEGER PRIMARY KEY,
  series_id   INTEGER NOT NULL REFERENCES series,
  season      INTEGER NOT NULL,
  race_num    INTEGER NOT NULL,             -- points race number in the season
  name        TEXT,
  track       TEXT,
  race_date   TEXT,                         -- ISO yyyy-mm-dd
  scheduled_laps INTEGER,
  track_length REAL,                        -- miles
  surface     TEXT,                         -- Paved, Dirt, ...
  is_chase    INTEGER NOT NULL DEFAULT 0,   -- 1 = playoff race
  UNIQUE (series_id, season, race_num)
);

-- One row per driver per race. Raw facts only; totals are derived in views.
CREATE TABLE results (
  race_id       INTEGER NOT NULL REFERENCES races,
  driver_id     INTEGER NOT NULL REFERENCES drivers,
  car           TEXT,
  team          TEXT,
  manufacturer  TEXT,
  start_pos     INTEGER,
  finish_pos    INTEGER,
  status        TEXT,                       -- Running, Accident, Engine, ...
  laps_completed INTEGER,
  laps_led      INTEGER DEFAULT 0,
  led_most      INTEGER DEFAULT 0,          -- 1 if most laps led
  pole          INTEGER DEFAULT 0,
  stage1_pts    INTEGER DEFAULT 0,
  stage2_pts    INTEGER DEFAULT 0,
  stage3_pts    INTEGER DEFAULT 0,          -- Cup 2024+ only
  race_pts      INTEGER NOT NULL,           -- TOTAL points for the weekend
  playoff_pts   INTEGER DEFAULT 0,
  best_lap_pts  INTEGER DEFAULT 0,
  -- loop-data style stats (nullable; fill if your source has them)
  driver_rating REAL,
  avg_run_pos   REAL,
  fastest_laps  INTEGER,
  top15_laps    INTEGER,
  quality_passes INTEGER,
  green_flag_passes INTEGER,
  pass_diff     INTEGER,
  PRIMARY KEY (race_id, driver_id)
);

-- Stage finishes (top 10 score points)
CREATE TABLE stage_results (
  race_id    INTEGER NOT NULL REFERENCES races,
  driver_id  INTEGER NOT NULL REFERENCES drivers,
  stage      INTEGER NOT NULL,              -- 1, 2
  pos        INTEGER,
  points     INTEGER DEFAULT 0,
  PRIMARY KEY (race_id, driver_id, stage)
);

-- Penalties, playoff reset, bonuses: anything the race sums miss.
CREATE TABLE adjustments (
  adj_id     INTEGER PRIMARY KEY,
  race_id    INTEGER NOT NULL REFERENCES races,   -- applied from this race on
  driver_id  INTEGER NOT NULL REFERENCES drivers,
  points     INTEGER NOT NULL,
  note       TEXT
);

-- Official standings as published, to audit your computed totals.
CREATE TABLE official_standings (
  race_id    INTEGER NOT NULL REFERENCES races,
  driver_id  INTEGER NOT NULL REFERENCES drivers,
  rank       INTEGER,
  points     INTEGER,
  PRIMARY KEY (race_id, driver_id)
);

CREATE INDEX idx_results_driver ON results(driver_id);
CREATE INDEX idx_races_season   ON races(series_id, season, race_num);

-- Points after each race for each driver (computed).
CREATE VIEW v_points_after_race AS
SELECT r.race_id, r.series_id, r.season, r.race_num, d.driver_id,
       (SELECT COALESCE(SUM(x.race_pts),0)
          FROM results x JOIN races rx ON rx.race_id = x.race_id
         WHERE x.driver_id = d.driver_id AND rx.series_id = r.series_id
           AND rx.season = r.season AND rx.race_num <= r.race_num)
     + (SELECT COALESCE(SUM(a.points),0)
          FROM adjustments a JOIN races ra ON ra.race_id = a.race_id
         WHERE a.driver_id = d.driver_id AND ra.series_id = r.series_id
           AND ra.season = r.season AND ra.race_num <= r.race_num) AS points
FROM races r
JOIN drivers d ON EXISTS (
  SELECT 1 FROM results x JOIN races rx ON rx.race_id = x.race_id
   WHERE x.driver_id = d.driver_id AND rx.series_id = r.series_id
     AND rx.season = r.season AND rx.race_num <= r.race_num);

-- Ranked standings with gap to leader (computed).
CREATE VIEW v_standings AS
SELECT race_id, series_id, season, race_num, driver_id, points,
       RANK() OVER (PARTITION BY race_id ORDER BY points DESC) AS rank,
       points - MAX(points) OVER (PARTITION BY race_id)        AS behind
FROM v_points_after_race;

-- Computed vs official, to catch missing penalties.
CREATE VIEW v_audit AS
SELECT s.race_id, s.driver_id, s.points AS computed, o.points AS official,
       s.points - o.points AS diff
FROM v_standings s JOIN official_standings o USING (race_id, driver_id)
WHERE s.points <> o.points;

-- Season stat lines (per driver, through all loaded races).
CREATE VIEW v_season_stats AS
SELECT ra.series_id, ra.season, r.driver_id,
       COUNT(*)                                   AS races,
       SUM(r.finish_pos = 1)                      AS wins,
       SUM(r.finish_pos <= 5)                     AS top5,
       SUM(r.finish_pos <= 10)                    AS top10,
       SUM(r.finish_pos <= 20)                    AS top20,
       SUM(r.finish_pos >= 30)                    AS p30,
       SUM(r.status <> 'Running')                 AS dnfs,
       SUM(r.pole)                                AS poles,
       SUM(r.laps_led > 0)                        AS races_led,
       SUM(r.laps_led)                            AS laps_led,
       SUM(r.led_most)                            AS led_most,
       SUM(r.stage1_pts + r.stage2_pts + r.stage3_pts) AS stage_pts,
       MIN(r.finish_pos)                          AS best_finish,
       ROUND(AVG(r.finish_pos),1)                 AS avg_finish,
       ROUND(AVG(r.start_pos),1)                  AS avg_start,
       ROUND(AVG(r.driver_rating),1)              AS avg_rating,
       ROUND(AVG(r.avg_run_pos),1)                AS avg_run_pos
FROM results r JOIN races ra USING (race_id)
GROUP BY ra.series_id, ra.season, r.driver_id;

-- Driver rating per race plus a rolling average over the driver's last 5 rated starts.
CREATE VIEW v_rolling_rating AS
SELECT ra.series_id, ra.season, ra.race_num, r.driver_id, r.driver_rating,
       ROUND(AVG(r.driver_rating) OVER (
         PARTITION BY ra.series_id, ra.season, r.driver_id
         ORDER BY ra.race_num ROWS BETWEEN 4 PRECEDING AND CURRENT ROW), 1) AS rating_last5
FROM results r JOIN races ra USING (race_id)
WHERE r.driver_rating IS NOT NULL;
