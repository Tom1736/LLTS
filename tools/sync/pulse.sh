#!/bin/sh
# Reference pulse for camsync, Pi 3 only: hardware PWM0 on GPIO18 (header pin 12).
# The PWM runs from the Pi's crystal and needs no CPU, so the edges have no software jitter.
# usage: sudo ./pulse.sh [hz] [high_us]   start (default 10 Hz, 1000 us high)
#        sudo ./pulse.sh stop
# Loads the pwm overlay at runtime, nothing is written to config.txt (gone after a reboot).
set -e
HZ=${1:-10}
HIGH_US=${2:-1000}

chip() { for c in /sys/class/pwm/pwmchip*; do [ -e "$c" ] && echo "$c" && return; done; }

if [ "$1" = stop ]; then
    C=$(chip)
    [ -n "$C" ] && [ -e "$C/pwm0" ] && echo 0 > "$C/pwm0/enable" && echo 0 > "$C/unexport"
    dtoverlay -r pwm 2>/dev/null || true
    echo "pulse stopped"
    exit 0
fi

dtoverlay -l | grep -q ' pwm ' || dtoverlay pwm pin=18 func=2
sleep 0.5
C=$(chip)
[ -n "$C" ] || { echo "no pwm chip after loading the overlay" >&2; exit 1; }
[ -e "$C/pwm0" ] || echo 0 > "$C/export"
sleep 0.2
P=$(awk "BEGIN { printf \"%d\", 1e9 / $HZ }")
D=$((HIGH_US * 1000))
echo 0 > "$C/pwm0/enable"
# period must stay >= duty_cycle at every step
if [ "$(cat "$C/pwm0/period")" -lt "$D" ]; then echo "$P" > "$C/pwm0/period"; echo "$D" > "$C/pwm0/duty_cycle"
else echo "$D" > "$C/pwm0/duty_cycle"; echo "$P" > "$C/pwm0/period"; fi
echo normal > "$C/pwm0/polarity" 2>/dev/null || true
echo 1 > "$C/pwm0/enable"
echo "pulse on GPIO18: period $(cat "$C/pwm0/period") ns, high $(cat "$C/pwm0/duty_cycle") ns"
