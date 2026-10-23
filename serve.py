#!/usr/bin/env python3
"""
Serve the dashboard folder on localhost (standard library only).

  python serve.py                 # http://127.0.0.1:8765/dashboard.html, serving the folder this file is in
  python serve.py --port 9000 --dir /path/to/folder

Same as `python -m http.server`, plus a Cache-Control: no-cache header. dashboard.html carries the version
of manifest.js, so a browser that kept an old copy of the page would keep showing old data after a rebuild.
With no-cache the browser asks every time, and unchanged files still answer 304 (Not Modified) from their
modification time. Listens on 127.0.0.1 only, so other devices cannot reach it.
"""
import argparse
import functools
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--bind", default="127.0.0.1")
    ap.add_argument("--dir", default=os.path.dirname(os.path.abspath(__file__)))
    a = ap.parse_args()
    handler = functools.partial(Handler, directory=a.dir)
    with ThreadingHTTPServer((a.bind, a.port), handler) as srv:
        print(f"serving {a.dir} at http://{a.bind}:{a.port}/dashboard.html  (Ctrl+C to stop)")
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
