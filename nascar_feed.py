"""A small client for NASCAR's public JSON feed (cf.nascar.com/cacher), using only `requests`.

It has the two calls the lap exporters need, with the same names as the nascar-api package's HistoricNascarRepo, so fetch_lap_times.py runs the same way with or without that package:

    repo = HttpNascarRepo()
    repo.get_races(2024, 1)                          # the season's Cup events, as dicts (race_id, race_type_id, race_date, actual_laps, track_name, race_name, ...)
    repo.get_lap_times(2024, 1, race_id=5273)        # one dict per driver: full_name, number, manufacturer, driver_id, laps = [{lap, lap_time, lap_speed, position}]

The feed has lap-by-lap times from 2020; before that its lap-times files do not exist (a request is answered 403 Access Denied) and get_lap_times returns [].
Be polite: one request at a time with a pause, and a descriptive user agent."""
import time

import requests

DOMAIN = "https://cf.nascar.com/cacher"
USER_AGENT = "nascarvis/1.0 (https://github.com/intelati26/nascarvis; personal research)"


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
