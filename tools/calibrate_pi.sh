#!/usr/bin/env bash
# Intrinsic calibration of one OV9281 camera, run from the PC (Git Bash).
#
#   tools/calibrate_pi.sh <pi-ip> <name> [target-views]
#   e.g. tools/calibrate_pi.sh 192.168.1.94 pi3b-2026-11-03
#
# 1. copies tools/live.py to the Pi (~/t) and starts the live view on port 8000
# 2. runs the auto capture into calib/<name>/ until you press Ctrl+C
#    (resumes if calib/<name>/ already has views)
# 3. calibrates (calib_solve.py) and checks stability (stability.py)
# Env: PI_USER (default tom), PYTHON (default python, needs tools/requirements.txt)
set -euo pipefail
IP=${1:?pi ip}; NAME=${2:?name, e.g. pi3b-2026-11-03}; TARGET=${3:-60}
PI_USER=${PI_USER:-tom}
PY=${PYTHON:-python}
HERE=$(cd "$(dirname "$0")" && pwd)
OUT="$HERE/../calib/$NAME"
export PYTHONIOENCODING=utf-8

"$PY" -c "import cv2, numpy" 2>/dev/null || { echo "Fehlt: $PY -m pip install -r tools/requirements.txt"; exit 1; }

echo "== 1/4 live.py auf $PI_USER@$IP starten"
ssh "$PI_USER@$IP" 'mkdir -p ~/t'
scp -q "$HERE/live.py" "$PI_USER@$IP:t/live.py"
ssh "$PI_USER@$IP" 'cd ~/t; pkill -f live.py; pkill rpicam-vid; sleep 1
  setsid nohup timeout 10800 python3 live.py 1280 800 10 > live.log 2>&1 < /dev/null &
  exit 0'
for _ in $(seq 30); do
  curl -s -m 3 -o /dev/null "http://$IP:8000/frame.jpg" && break
  sleep 2
done || true
curl -s -m 3 -o /dev/null "http://$IP:8000/frame.jpg" || { echo "Kein Bild von $IP:8000 – ~/t/live.log auf dem Pi prüfen"; exit 1; }

echo "== 2/4 Aufnahme nach calib/$NAME"
echo "   Livebild:   http://$IP:8000"
echo "   Tablet:     http://$IP:8000/board  (antippen = Vollbild)"
echo "   Strg+C beendet die Aufnahme, sobald die Seite FERTIG meldet."
trap 'echo' INT
"$PY" "$HERE/calib_capture.py" "$IP" "$OUT" "$TARGET" || true
trap - INT

echo "== 3/4 Kalibrierung"
"$PY" "$HERE/calib_solve.py" "$OUT"

echo "== 4/4 Stabilität"
"$PY" "$HERE/stability.py" "$OUT"

echo
echo "Livebild läuft weiter (stoppt nach 3 h). Sofort beenden:"
echo "  ssh $PI_USER@$IP 'pkill -f live.py; pkill rpicam-vid'"
