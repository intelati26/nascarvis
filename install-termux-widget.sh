#!/data/data/com.termux/files/usr/bin/bash
# Run once in Termux. Installs dependencies and puts shortcuts on the Termux:Widget list.
# Also install the Termux:API and Termux:Widget apps (same source as Termux, e.g. F-Droid).
set -e
DIR="$(dirname "$(readlink -f "$0")")"
pkg install -y python python-pyarrow termux-api
mkdir -p ~/.shortcuts
chmod +x "$DIR/nascar-dashboard.sh"
cat > ~/.shortcuts/NASCAR <<EOF
#!/data/data/com.termux/files/usr/bin/bash
exec "$DIR/nascar-dashboard.sh"
EOF
cat > ~/.shortcuts/"NASCAR (no update)" <<EOF
#!/data/data/com.termux/files/usr/bin/bash
exec "$DIR/nascar-dashboard.sh" --no-update
EOF
cat > ~/.shortcuts/"NASCAR stop" <<EOF
#!/data/data/com.termux/files/usr/bin/bash
exec "$DIR/nascar-dashboard.sh" --stop
EOF
chmod +x ~/.shortcuts/NASCAR ~/.shortcuts/"NASCAR (no update)" ~/.shortcuts/"NASCAR stop"
echo "Done. Add a Termux:Widget to your home screen and tap NASCAR."
