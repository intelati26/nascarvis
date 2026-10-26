"""Polite, cached access to web pages for the scripts that read them (Wikipedia, mainly). Standard library only.

    wiki = Wikipedia(cache_dir="/tmp/some_cache")      # 0.8 s between requests, a project user agent, pages cached as files
    wiki.raw("Darlington Raceway")                     # the page's wikitext, '' if there is no such page
    wiki.page("Dover International Speedway")          # (final title, wikitext), following a #REDIRECT
    wiki.search("Dick Brooks NASCAR driver")           # titles of the best search hits

Wikipedia text is CC BY-SA 4.0: the scripts keep only short excerpts, the angle, the totals and the article link.
fetch_lap_times.py and the other NASCAR feed scripts use nascar_feed.py instead (JSON, with retries); both send the same user agent."""
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = "nascarvis/1.0 (https://github.com/intelati26/nascarvis; personal research)"


class PoliteClient:
    def __init__(self, delay=0.8, cache_dir=None, user_agent=USER_AGENT):
        self.delay, self.user_agent, self.cache_dir, self._last = delay, user_agent, cache_dir, 0.0
        if cache_dir: os.makedirs(cache_dir, exist_ok=True)

    def get(self, url, timeout=60):
        """The page at `url` as text, at least `delay` seconds after the previous request. Raises urllib.error.HTTPError on an error status."""
        wait = self.delay - (time.time() - self._last)
        if wait > 0: time.sleep(wait)
        self._last = time.time()
        req = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        return urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "replace")

    def cached(self, name, fn):
        """fn()'s text, kept in cache_dir/name so a second run makes no request."""
        p = os.path.join(self.cache_dir, name)
        if os.path.exists(p): return open(p, encoding="utf-8").read()
        v = fn(); open(p, "w", encoding="utf-8").write(v); return v


class Wikipedia(PoliteClient):
    API = "https://en.wikipedia.org/w/api.php"
    INDEX = "https://en.wikipedia.org/w/index.php"

    def __init__(self, delay=0.8, cache_dir=None, page_name=None):
        """page_name: title -> the cache file name for that page (None = pages are not cached)."""
        super().__init__(delay, cache_dir)
        self.page_name = page_name

    def raw(self, title, strict=False):
        """The page's wikitext (action=raw). A missing page gives '' unless strict, which raises urllib.error.HTTPError."""
        url = f"{self.INDEX}?title={urllib.parse.quote(title)}&action=raw"
        try:
            return self.cached(self.page_name(title), lambda: self.get(url)) if self.page_name else self.get(url)
        except urllib.error.HTTPError:
            if strict: raise
            return ""

    def page(self, title, depth=0):
        """(final title, wikitext) of a page, following a #REDIRECT up to three times."""
        txt = self.raw(title)
        m = re.match(r"\s*#redirect\s*\[\[([^\]|#]+)", txt, re.I)
        return self.page(m.group(1), depth + 1) if m and depth < 3 else (title, txt)

    def search(self, query, limit=5, cache_name=None):
        """Titles of the best hits for `query`, best first (the raw answer is cached under cache_name when given)."""
        url = self.API + "?" + urllib.parse.urlencode({"action": "query", "list": "search", "srsearch": query, "srlimit": limit, "format": "json"})
        text = self.cached(cache_name, lambda: self.get(url)) if cache_name else self.get(url)
        return [h["title"] for h in json.loads(text)["query"]["search"]]
