#!/usr/bin/env python3
"""
Serve the dashboard folder on localhost, with the query builder's API (standard library only).

  python serve.py                 # http://127.0.0.1:8765/dashboard.html   and   http://127.0.0.1:8765/query/query.html
  python serve.py --port 9000 --dir /path/to/folder

Same as `python -m http.server`, plus a Cache-Control: no-cache header. dashboard.html carries the version
of manifest.js, so a browser that kept an old copy of the page would keep showing old data after a rebuild.
With no-cache the browser asks every time, and unchanged files still answer 304 (Not Modified) from their
modification time. Listens on 127.0.0.1 only, so other devices cannot reach it.

When the folder has a query/ directory the query API is served too (/api/catalog, /api/saved, /api/compile, /api/run, /api/save; see
query/serve_query.py), so the dashboard's "Open in query builder" link works from this one server. Build the database once with
`python query/build_db.py`. With --bind set to a LAN address the dashboard is reachable from other devices, but the API still answers
only requests whose Host is localhost or 127.0.0.1, because it can run SQL and save files. Without a query/ folder this is a plain
static server, as before.
"""
import argparse
import functools
import os
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))


class StaticHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()


def make_handler(root, db=None, catalog=None):
    """The request handler class for the folder `root`: static files, plus the query API when root/query/ has the query engine.
    Returns (handler class, query API available, database path)."""
    qdir = os.path.join(root, "query")
    if not all(os.path.exists(os.path.join(qdir, f)) for f in ("engine.py", "serve_query.py", "catalog_nascar.json")):
        return StaticHandler, False, None
    if qdir not in sys.path: sys.path.insert(0, qdir)
    import engine
    import serve_query
    db = db or os.path.join(root, "data", "query.db")
    cls = type("QueryHandler", (serve_query.Handler,), {"catalog": engine.load_catalog(catalog or os.path.join(qdir, "catalog_nascar.json")),
                                                         "db": db, "saved_dir": os.path.join(qdir, "saved")})
    return cls, True, db


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--bind", default="127.0.0.1")
    ap.add_argument("--dir", default=HERE)
    ap.add_argument("--db", default=None, help="the query database (default: data/query.db in --dir)")
    a = ap.parse_args()
    cls, has_query, db = make_handler(os.path.abspath(a.dir), a.db)
    with ThreadingHTTPServer((a.bind, a.port), functools.partial(cls, directory=a.dir)) as srv:
        base = f"http://{a.bind}:{a.port}"
        print(f"serving {a.dir}\n  dashboard:     {base}/dashboard.html")
        if has_query:
            print(f"  query builder: {base}/query/query.html   (database: {'ready' if os.path.exists(db) else 'NOT BUILT - run python query/build_db.py'})")
        print("Ctrl+C to stop")
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
