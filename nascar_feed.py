"""A small client for NASCAR's public JSON feed (cf.nascar.com/cacher), using only `requests`. The fetch_*.py scripts all use it.

The calls the exporters need:

    repo = HttpNascarRepo()
    repo.get_races(2024, 1)                          # the season's Cup events, as dicts (race_id, race_type_id, race_date, actual_laps, track_name, race_name, ...)
    repo.get_lap_times(2024, 1, race_id=5273)        # one dict per driver: full_name, number, manufacturer, driver_id, laps = [{lap, lap_time, lap_speed, position}]

The feed has lap-by-lap times from 2020; before that its lap-times files do not exist (a request is answered 403 Access Denied) and get_lap_times returns [].
Loop statistics (get_loop_stats) are patchier: 2015 and 2016 answer 200 with a JSON null, 2017 and 2018 are 403, and real data starts in 2019. Null, empty and missing are all None here.
Be polite: one request at a time with a pause, and a descriptive user agent."""
import re
import time

import requests

from webfetch import USER_AGENT

DOMAIN = "https://cf.nascar.com/cacher"


def clean_name(n):
    """'Kyle Larson (C)' -> 'Kyle Larson'"""
    return re.sub(r"\s*\(.*?\)\s*", " ", str(n or "")).strip()


def completed_points_races(races, race_type=1):
    """(all events, the completed points races in date order). The feed also lists the Clash, the Duels and other non-points events; the points races, numbered 1, 2, 3 ...
    in this order, line up with the Race column of nascaR.data."""
    rs = list(races)
    done = [r for r in rs if r.get("race_type_id") == race_type and (r.get("actual_laps") or 0) > 0]
    done.sort(key=lambda r: str(r.get("race_date") or r.get("date_scheduled") or ""))
    return rs, done


def _float(v):
    try:
        return None if v in (None, "") else float(v)
    except (TypeError, ValueError):
        return None


class HttpNascarRepo:
    def __init__(self, delay=0.3, session=None, retries=3, retry_wait=2.0):
        self.delay, self.retries, self.retry_wait = delay, retries, retry_wait
        self.session = session or requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self._last = 0.0

    def safe_get(self, url, timeout=(5, 60)):
        """The JSON at `url`, or None when the file does not exist (403 or 404). Other failures are retried, then raised."""
        for attempt in range(1, self.retries + 1):
            wait = self.delay - (time.time() - self._last)
            if wait > 0: time.sleep(wait)
            self._last = time.time()
            try:
                r = self.session.get(url, timeout=timeout)
                if r.status_code in (403, 404): return None
                r.raise_for_status()
                return r.json()
            except (requests.RequestException, ValueError):
                if attempt == self.retries: raise
                time.sleep(self.retry_wait)

    def get_races(self, year, series=1):
        data = self.safe_get(f"{DOMAIN}/{year}/race_list_basic.json")
        return (data or {}).get(f"series_{int(getattr(series, 'value', series))}", [])

    def get_loop_stats(self, year, series=1, race_id=None):
        """One race's loop statistics: {race_id, race_name, sch_laps, act_laps, drivers: [one dict per driver: driver_id, start_ps, mid_ps, ps, ...]}, or None when the feed has none."""
        data = self.safe_get(f"https://cf.nascar.com/loopstats/prod/{year}/{int(getattr(series, 'value', series))}/{race_id}.json")
        race = data[0] if isinstance(data, list) and data else None
        return race if isinstance(race, dict) and race.get("drivers") else None

    def get_lap_times(self, year, series=1, race_id=None):
        data = self.safe_get(f"{DOMAIN}/{year}/{int(getattr(series, 'value', series))}/{race_id}/lap-times.json")
        out = []
        for d in (data or {}).get("laps", []):
            out.append({
                "race_id": race_id, "number": d.get("Number"), "full_name": d.get("FullName"), "manufacturer": d.get("Manufacturer"),
                "driver_id": d.get("NASCARDriverID"),
                "laps": [{"lap": lp.get("Lap"), "lap_time": _float(lp.get("LapTime")), "lap_speed": _float(lp.get("LapSpeed")), "position": lp.get("RunningPos")}
                         for lp in d.get("Laps") or []],
            })
        return out
