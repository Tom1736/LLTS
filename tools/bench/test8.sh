#!/usr/bin/env bash
# Test 8: can the Pi Zero W keep up as camera node B? Runs on the Pi, needs sudo.
#
#   copy roi_test.c, track.c and this script to ~/t on the Pi, then:
#   cd ~/t && sudo bash test8.sh [parts] 2>&1 | tee test8.log
#
# A. raw V4L2 sweep, 640x400 R8, no processing (same as section 4 of test-results-2026-10-29.md)
# B. 640x400 full frame + copy + threshold/centroid (track.c, SCHED_FIFO)
# C. sensor crop (ROI) + copy + per-pixel pass + moving ROI (roi_test.c, SCHED_FIFO)
# parts: any of A, B, C (default ABC). Takes about 5 minutes. Stops live.py / rpicam first.
#
# On the single core a SCHED_FIFO loop that can't keep up never sleeps and starves everything
# else, including a plain `timeout` and sshd. So the timeouts run at a higher FIFO priority
# (WD) than the loops (track 50, roi_test 80); the loops lower themselves after the fork.
set -u
cd "$(dirname "$0")"
PARTS=${1:-ABC}
V=/dev/video0
S=/dev/v4l-subdev0
WD="chrt -f 90 timeout"
[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 1; }

echo "== system"
cat /proc/device-tree/model; echo
uname -a
vcgencmd get_throttled; vcgencmd measure_temp; vcgencmd measure_clock arm
free -m | head -2
echo "sched_rt_runtime_us $(cat /proc/sys/kernel/sched_rt_runtime_us)"

pkill -f live.py; pkill rpicam; sleep 1
for p in gcc:gcc v4l2-ctl:v4l-utils python3:python3; do
  command -v "${p%%:*}" > /dev/null || { echo "installing ${p#*:}"; apt-get install -y "${p#*:}" > /dev/null; }
done
[ -e /dev/i2c-10 ] || modprobe i2c-dev
echo "== camera nodes"
v4l2-ctl --list-devices
ls /dev/i2c-*
v4l2-ctl -d $S --list-ctrls | grep -E "blanking|exposure"

echo "== build"
gcc -O2 -o roi_test roi_test.c -lm || exit 1
gcc -O3 -Wall -o track track.c -lm || exit 1

# fps, seq gaps and interval jitter from a v4l2-ctl --verbose log
analyze() {
  python3 - "$1" <<'EOF'
import re, statistics, sys
s, t = [], []
for l in open(sys.argv[1]):
    m = re.search(r"seq:\s+(\d+) bytesused: \d+ ts: ([\d.]+)", l)
    if m:
        s.append(int(m.group(1))); t.append(float(m.group(2)) * 1e3)
s, t = s[10:], t[10:]  # skip start-up
if len(s) < 20:
    print("  only %d frames, stream hung?" % (len(s) + 10)); sys.exit()
gaps = sum(b - a - 1 for a, b in zip(s, s[1:]))
per = (t[-1] - t[0]) / (s[-1] - s[0])
iv = [b - a for a, b, sa, sb in zip(t, t[1:], s, s[1:]) if sb == sa + 1]
print("  %.2f fps, seq gaps %d / %d, jitter sd %.1f us" % (1000 / per, gaps, s[-1] - s[0], statistics.pstdev(iv) * 1e3))
EOF
}

if [[ $PARTS == *A* ]]; then
  echo "== A. raw V4L2 640x400 R8, 3 mmap buffers, 2000 frames, no RT"
  v4l2-ctl -d $S --set-subdev-fmt pad=0,width=640,height=400,code=0x2001
  v4l2-ctl -d $V --set-fmt-video=width=640,height=400,pixelformat=GREY
  for vb in 300 144 100 60 56 40 34; do
    v4l2-ctl -d $S -c horizontal_blanking=890,vertical_blanking=$vb,exposure=20
    echo "vblank $vb"
    timeout 30 v4l2-ctl -d $V --stream-mmap=3 --stream-count=2000 --stream-to=/dev/null --verbose > /dev/shm/a.txt 2>&1
    analyze /dev/shm/a.txt
  done
fi

if [[ $PARTS == *B* ]]; then
  echo "== B. 640x400 + copy + threshold/centroid (track.c), 10 s each"
  for f in 150 200 250; do
    echo "fps $f"
    $WD -s INT 10 ./track -f $f -t 0 -n 10 -o /dev/shm/rec | grep -E "^640x400|frames,|no frame|fps too high"
  done
fi

if [[ $PARTS == *C* ]]; then
  echo "== C. 1280x800 mode cropped over I2C (roi_test.c), vblank 56, ROI jump every 40 frames"
  echo "   (k+N histogram is only meaningful if the two windows differ in brightness)"
  v4l2-ctl -d $S --set-subdev-fmt pad=0,width=1280,height=800,code=0x2001
  v4l2-ctl -d $V --set-fmt-video=width=1280,height=800,pixelformat=GREY
  for run in "200 320" "128 320" "128 640" "128 1280" "64 320" "16 320"; do
    set -- $run
    h=$1 w=$2 vts=$(($1 + 56))
    v4l2-ctl -d $S -c horizontal_blanking=250,vertical_blanking=110,exposure=$((vts - 30))
    echo "-- rows $h, width $w, vts $vts"
    $WD 30 ./roi_test $h $vts 200 500 5000 40 $w
    vcgencmd measure_temp
  done
fi

echo "== after"
vcgencmd get_throttled; vcgencmd measure_temp
dmesg | grep -iE "unicam|ov9281|voltage" | tail -10
