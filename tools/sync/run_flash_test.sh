#!/bin/bash
# Screen flash test, run from the laptop: records on both Pis at once, fetches, analyses.
# Open flash.html on the laptop first, aim both cameras at the band, click to start flashing.
# usage: ./run_flash_test.sh [seconds] [extra camsync args, e.g. -u for free-run or -g 64]
# Hosts are the ssh aliases pi3 and pizero (~/.ssh/config).
set -e
cd "$(dirname "$0")"
SECS=${1:-30}; shift || true
TAG=flash_$(date +%Y%m%d_%H%M%S)
OUT=results/$TAG
mkdir -p "$OUT"

ssh pi3 'sudo -n ~/sync/pulse.sh 10 1000'
ssh pi3    "cd ~/sync && sudo -n ./camsync -t $SECS -d $TAG $*" > "$OUT/pi3.log" 2>&1 &
ssh pizero "cd ~/sync && sudo -n ./camsync -t $SECS -d $TAG $*" > "$OUT/zero.log" 2>&1 &
wait
tail -n 3 "$OUT/pi3.log" "$OUT/zero.log"
scp -q -r "pi3:sync/$TAG" "$OUT/pi3"
scp -q -r "pizero:sync/$TAG" "$OUT/zero"
python3 flash_analyze.py "$OUT/pi3" "$OUT/zero" | tee "$OUT/result.txt"
