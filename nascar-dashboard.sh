#!/data/data/com.termux/files/usr/bin/bash
# One-tap NASCAR dashboard: update data, rebuild, serve on localhost, open in the browser.
# Termux:Widget runs this from ~/.shortcuts/ (see install-termux-widget.sh).
#   Flags: --no-update  skip the download/rebuild, just serve and open   --stop  stop the server
PORT=8765
DIR="$(dirname "$(readlink -f "$0")")"
cd "$DIR" || exit 1
PIDFILE="$DIR/.server.pid"

if [ "$1" = "--stop" ]; then
  [ -f "$PIDFILE" ] && kill "$(cat "$PIDFILE")" 2>/dev/null; rm -f "$PIDFILE"; echo "server stopped"; exit 0
fi

if [ "$1" != "--no-update" ]; then
  echo "Updating data and rebuilding..."
  if ! python build_dashboard.py --update; then
    echo "Update failed (offline?); trying the existing data."
    [ -f dashboard.html ] || python build_dashboard.py || { echo "Build failed."; sleep 5; exit 1; }
  fi
fi
[ -f dashboard.html ] || { echo "No dashboard.html."; sleep 5; exit 1; }

if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "Server already running."
else
  nohup python -m http.server "$PORT" --bind 127.0.0.1 >/dev/null 2>&1 &
  echo $! > "$PIDFILE"
  sleep 1
fi

URL="http://localhost:$PORT/dashboard.html"
echo "Opening $URL"
if command -v termux-open-url >/dev/null; then termux-open-url "$URL"
else echo "termux-open-url not found: pkg install termux-api (and install the Termux:API app)"; fi
sleep 2
