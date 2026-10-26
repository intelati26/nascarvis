#!/usr/bin/env python3
"""Tests for serve.py: one server for the dashboard and the query API.  python tests/test_serve.py   (standard library only)"""
import functools
import http.client
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import serve  # noqa: E402


def start(root):
    cls, has_query, db = serve.make_handler(root)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(cls, directory=root))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, has_query, db


def request(srv, method, path, body=None, host=None):
    conn = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=10)
    headers = {"Host": host} if host else {}
    data = None
    if body is not None:
        data = json.dumps(body).encode(); headers["Content-Type"] = "application/json"
    conn.request(method, path, body=data, headers=headers)
    r = conn.getresponse(); out = (r.status, r.read(), dict(r.getheaders())); conn.close()
    return out


def main():
    tmp = tempfile.mkdtemp()
    full = os.path.join(tmp, "full")                       # a folder like the repository: dashboard, query/ and a database
    os.makedirs(os.path.join(full, "data"))
    open(os.path.join(full, "dashboard.html"), "w").write("<html>dashboard</html>")
    shutil.copytree(os.path.join(ROOT, "query"), os.path.join(full, "query"), ignore=shutil.ignore_patterns("__pycache__", "saved"))
    os.makedirs(os.path.join(full, "query", "saved"))
    con = sqlite3.connect(os.path.join(full, "data", "query.db"))
    con.execute("CREATE TABLE results (season INT, driver TEXT)"); con.execute("INSERT INTO results VALUES (2024, 'A')"); con.commit(); con.close()

    srv, has_query, db = start(full)
    assert has_query and db == os.path.join(full, "data", "query.db"), "the query folder is found and the database is data/query.db"
    st, body, h = request(srv, "GET", "/dashboard.html")
    assert st == 200 and b"dashboard" in body and h.get("Cache-Control") == "no-cache", "the dashboard is served, never cached"
    st, body, _ = request(srv, "GET", "/query/query.html")
    assert st == 200 and b"query" in body.lower(), "the builder page is served from the same server"
    st, body, _ = request(srv, "GET", "/api/catalog")
    j = json.loads(body)
    assert st == 200 and "driver_race" in j["catalog"]["subjects"] and j["db_ready"] is True, "the API answers on the same port"
    st, body, _ = request(srv, "POST", "/api/run", {"sql": "SELECT COUNT(*) AS n FROM results"})
    assert st == 200 and json.loads(body)["rows"] == [[1]], "custom SQL runs against the database"
    st, body, _ = request(srv, "POST", "/api/run", {"sql": "DELETE FROM results"})
    assert st == 400, "only SELECT is allowed"
    print("one server: dashboard, builder page, API, SELECT-only OK")

    # the API only answers local Host headers (it can run SQL and save files); the dashboard itself stays open to other devices (--bind)
    st, _, _ = request(srv, "GET", "/api/catalog", host="192.168.1.5:8765")
    assert st == 403, "the API refuses a LAN Host"
    st, _, _ = request(srv, "POST", "/api/run", {"sql": "SELECT 1"}, host="192.168.1.5:8765")
    assert st == 403, "and so does the SQL runner"
    st, body, _ = request(srv, "GET", "/dashboard.html", host="192.168.1.5:8765")
    assert st == 200 and b"dashboard" in body, "the dashboard is still served to a phone on the LAN"
    srv.shutdown()
    print("API is localhost-only; the dashboard is not restricted OK")

    # no query/ folder: the plain static server it always was
    plain = os.path.join(tmp, "plain")
    os.makedirs(plain)
    open(os.path.join(plain, "dashboard.html"), "w").write("<html>plain</html>")
    srv, has_query, db = start(plain)
    assert not has_query and db is None
    st, body, h = request(srv, "GET", "/dashboard.html")
    assert st == 200 and b"plain" in body and h.get("Cache-Control") == "no-cache"
    assert request(srv, "GET", "/api/catalog")[0] in (404, 501), "no API without a query/ folder"
    srv.shutdown()
    print("without query/: a plain static server OK")


if __name__ == "__main__":
    main()
