#!/usr/bin/env python3
"""Serve the dashboard folder plus the query API on localhost (standard library only).

  python query/build_db.py              # once: builds data/query.db
  python query/serve_query.py           # http://127.0.0.1:8765/query/query.html

  GET  /api/catalog                     the catalog (tables, columns, measures, parameters)
  GET  /api/saved                       saved queries (query/saved/*.query.json)
  POST /api/compile  {spec, params?}    -> {sql, params, columns}          (nothing is run)
  POST /api/run      {spec, params?}    -> {columns, rows, ...}  or  {sql, params?} for hand-edited "custom SQL"
  POST /api/save     {name, title, spec} writes query/saved/<name>.sql and <name>.query.json (the only write path)

The database is opened read-only with row and time limits. Listens on 127.0.0.1 only and rejects other Host headers.
"""
import argparse
import functools
import json
import os
import re
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import engine  # noqa: E402

MAX_BODY = 200_000
SAFE_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,59}$")


class Handler(SimpleHTTPRequestHandler):
    catalog = None
    db = None
    saved_dir = os.path.join(HERE, "saved")

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def log_message(self, fmt, *args):          # quieter console
        if "/api/" in (args[0] if args else ""): sys.stderr.write("%s\n" % (fmt % args))

    # ---- helpers
    def send_json(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def host_ok(self):
        return self.headers.get("Host", "").split(":")[0] in ("127.0.0.1", "localhost")

    def read_body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY: raise engine.SpecError("request too large")
        try: return json.loads(self.rfile.read(n) or b"{}")
        except ValueError: raise engine.SpecError("the request body is not valid JSON")

    # ---- routes
    def do_GET(self):
        if not self.path.startswith("/api/"): return super().do_GET()
        if not self.host_ok(): return self.send_json(403, {"error": "forbidden host"})
        if self.path == "/api/catalog":
            return self.send_json(200, {"catalog": self.catalog, "max_rows": engine.MAX_ROWS, "db_ready": os.path.exists(self.db)})
        if self.path == "/api/saved":
            out = []
            if os.path.isdir(self.saved_dir):
                for f in sorted(os.listdir(self.saved_dir)):
                    if f.endswith(".query.json"):
                        with open(os.path.join(self.saved_dir, f), encoding="utf-8") as fh: q = json.load(fh)
                        out.append({"name": f[:-len(".query.json")], "title": q.get("title", ""), "spec": q.get("spec")})
            return self.send_json(200, out)
        self.send_json(404, {"error": "unknown endpoint"})

    def do_POST(self):
        if not self.host_ok(): return self.send_json(403, {"error": "forbidden host"})
        try:
            body = self.read_body()
            if self.path == "/api/compile":
                sql, params, cols = engine.compile_spec(body.get("spec"), self.catalog, body.get("params"))
                return self.send_json(200, {"sql": sql, "params": params, "columns": cols})
            if self.path == "/api/run":
                if not os.path.exists(self.db):
                    return self.send_json(503, {"error": "no database yet: run  python query/build_db.py"})
                if body.get("sql") is not None:                       # hand-edited SQL
                    sql = engine.check_custom_sql(body["sql"])
                    params = {k: v for k, v in (body.get("params") or {}).items() if isinstance(v, (int, float, str, type(None)))}
                    cols, custom = None, True
                else:
                    sql, params, cols = engine.compile_spec(body.get("spec"), self.catalog, body.get("params"))
                    custom = False
                res = engine.run_sql(self.db, sql, params)
                if cols is not None and res["columns"] != cols:
                    raise engine.SpecError(f"result columns {res['columns']} differ from the compiled columns {cols}")
                res.update({"sql": sql, "params": params, "custom": custom})
                return self.send_json(200, res)
            if self.path == "/api/save":
                name = str(body.get("name", "")).strip().lower()
                if not SAFE_NAME.match(name): raise engine.SpecError("name: use a-z, 0-9, - and _ (up to 60 characters)")
                sql, params, cols = engine.compile_spec(body.get("spec"), self.catalog)
                os.makedirs(self.saved_dir, exist_ok=True)
                with open(os.path.join(self.saved_dir, name + ".sql"), "w", encoding="utf-8") as f: f.write(sql + "\n")
                meta = {"title": str(body.get("title", name))[:200], "database": "data/query.db", "parameters": params,
                        "output": {"columns": cols}, "spec": body["spec"]}
                with open(os.path.join(self.saved_dir, name + ".query.json"), "w", encoding="utf-8") as f:
                    json.dump(meta, f, indent=2); f.write("\n")
                return self.send_json(200, {"saved": name})
            self.send_json(404, {"error": "unknown endpoint"})
        except engine.SpecError as e:
            self.send_json(400, {"error": str(e)})
        except Exception as e:                                          # keep the server alive; show the cause
            self.send_json(500, {"error": f"{type(e).__name__}: {e}"})


def main():
    root = os.path.dirname(HERE)
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--db", default=os.path.join(root, "data", "query.db"))
    ap.add_argument("--catalog", default=os.path.join(HERE, "catalog_nascar.json"))
    ap.add_argument("--dir", default=root)
    a = ap.parse_args()
    Handler.catalog = engine.load_catalog(a.catalog)
    Handler.db = a.db
    handler = functools.partial(Handler, directory=a.dir)
    with ThreadingHTTPServer(("127.0.0.1", a.port), handler) as srv:
        print(f"query page: http://127.0.0.1:{a.port}/query/query.html   (database: {a.db}, "
              f"{'ready' if os.path.exists(a.db) else 'NOT BUILT - run python query/build_db.py'})   Ctrl+C to stop")
        try: srv.serve_forever()
        except KeyboardInterrupt: pass


if __name__ == "__main__":
    main()
