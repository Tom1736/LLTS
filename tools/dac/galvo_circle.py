#!/usr/bin/env python3
"""Draw a circle with the galvos, speed and size adjustable live from the keyboard.

Turn it up until the laser dot blurs into a closed circle (persistence of vision starts
at roughly 25-50 revolutions per second).

Keys (needs a terminal: ssh -t ...):
  Up / +      faster (x1.1)          Left / [    smaller (-5 %)
  Down / -    slower (/1.1)          Right / ]   bigger (+5 %)
  q / Ctrl-C  ramp down to 0 V and quit

Never above 5 V: the cap lives in gp8403.py (range held at 0-5 V, every value clamped and
asserted). The circle is centered in [--low, --high] (default 2.5 V) with at most half
that span as radius, so even at full size it stays inside 0..5 V. Also:
  - Slew limit (--slew V/ms) on every update. If the circle needs more than that, it
    shrinks/distorts instead of jumping, and the status line says SLEW-LIMITED.
  - Speed is capped at --max-freq (default 100 Hz) to protect the galvos; raise it only
    if the galvo datasheet allows that speed at this size.
  - Phase is integrated, so changing speed never makes the dot jump.
  - Soft start (radius grows over --ramp-in) and soft stop (ramp to 0 V).
GPIO 27 (pin 13) is high during the first half of every revolution: trigger the scope on
it to see the X/Y lag of the galvos.

usage: python3 galvo_circle.py [--freq 5] [--size 1.0] [--max-freq 100] [--slew 1]
                               [--low 0] [--high 5] [--rate 0] [--duration 0] [--dry-run]
"""
import argparse
import math
import os
import select
import signal
import sys
import time

import gp8403
from gp8403 import MAX_VOLTS, code_to_volts
from galvo_test import DryDAC


class Keys:
    """Non-blocking single keys from a terminal; does nothing without one."""
    def __init__(self):
        self.on = sys.stdin.isatty()
        if self.on:
            import termios
            import tty
            self.termios = termios
            self.fd = sys.stdin.fileno()
            self.saved = termios.tcgetattr(self.fd)
            tty.setcbreak(self.fd)

    def read(self):
        if not self.on or not select.select([self.fd], [], [], 0)[0]:
            return []
        data = os.read(self.fd, 64).decode(errors="ignore")
        keys, i = [], 0
        while i < len(data):
            if data[i] == "\x1b" and data[i + 1:i + 2] == "[" and i + 2 < len(data):
                keys.append({"A": "up", "B": "down", "C": "right", "D": "left"}.get(data[i + 2], ""))
                i += 3
            else:
                keys.append(data[i])
                i += 1
        return keys

    def close(self):
        if self.on:
            self.termios.tcsetattr(self.fd, self.termios.TCSADRAIN, self.saved)


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--addr", type=lambda s: int(s, 0), default=gp8403.DEFAULT_ADDR)
    p.add_argument("--freq", type=float, default=5.0, help="start speed in revolutions/s (default 5)")
    p.add_argument("--size", type=float, default=1.0, help="start radius as a fraction of the max, 0..1")
    p.add_argument("--max-freq", type=float, default=100.0,
                   help="speed limit in Hz (default 100); keys can't go above it")
    p.add_argument("--slew", type=float, default=1.0, help="max change in V per ms (default 1)")
    p.add_argument("--low", type=float, default=0.0, help="lower edge of the drawing area, 0..5")
    p.add_argument("--high", type=float, default=MAX_VOLTS, help="upper edge of the drawing area, 0..5")
    p.add_argument("--ramp-in", type=float, default=1.0, help="soft start in s (default 1)")
    p.add_argument("--rate", type=float, default=0.0,
                   help="DAC updates per s, 0 = as fast as the bus allows (default)")
    p.add_argument("--duration", type=float, default=0.0, help="s, 0 = until q / Ctrl-C")
    p.add_argument("--marker", type=int, default=27, help="scope marker GPIO, -1 = off")
    p.add_argument("--dry-run", action="store_true", help="no I2C/GPIO/keys, simulate 10 s")
    a = p.parse_args()

    for name in ("low", "high"):
        if not 0.0 <= getattr(a, name) <= MAX_VOLTS:
            p.error(f"--{name} must be between 0 and {MAX_VOLTS} V (the galvo is damaged above 5 V)")
    if a.low >= a.high:
        p.error("--low must be below --high")
    if not 0 < a.freq <= a.max_freq:
        p.error("--freq must be > 0 and <= --max-freq")
    if not 0 <= a.size <= 1:
        p.error("--size must be between 0 and 1")
    if a.slew <= 0 or a.rate < 0 or a.ramp_in < 0 or a.duration < 0:
        p.error("--slew must be > 0; --rate, --ramp-in, --duration >= 0")

    dac = DryDAC() if a.dry_run else gp8403.GP8403(a.addr)
    marker = gp8403.NoMarker() if a.dry_run else gp8403.make_marker(a.marker)
    keys = Keys() if not a.dry_run else None

    stopping = False

    def request_stop(*_):
        nonlocal stopping
        stopping = True
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    mid = (a.low + a.high) / 2
    r_max = (a.high - a.low) / 2                  # center +- r_max stays inside [low, high]
    freq, size = a.freq, a.size
    dt_sim = 1 / 3000                             # dry run: ~ the real update rate at 400 kHz
    dt_cap = 2 / a.rate if a.rate else 0.002      # a stall doesn't earn a bigger step

    def step_toward(cur, goal, max_step):
        d = goal - cur
        return goal if abs(d) <= max_step else cur + math.copysign(max_step, d)

    print(f"{'DRY RUN, nothing is written. ' if a.dry_run else ''}"
          f"circle around {mid:g} V, radius up to {r_max:g} V, slew {a.slew:g} V/ms, "
          f"max {a.max_freq:g} Hz, cap {MAX_VOLTS} V.")
    if keys and keys.on:
        print("Up/Down or +/-: speed   Left/Right or [/]: size   q: quit")
    elif not a.dry_run:
        print("no terminal (use ssh -t for keys); fixed speed, Ctrl-C or --duration to stop")

    x = y = 0.0                                   # our scripts always leave the DAC at 0 V
    phase = 0.0
    updates = win_updates = 0
    cmax = 0
    t0 = last = time.perf_counter()
    sim_t = 0.0
    next_ui = ui_last = t0
    ok = False
    try:
        dac.set_xy(0.0, 0.0)
        while not stopping:
            if a.dry_run:
                sim_t += dt_sim
                t, dt = sim_t, dt_sim
                if t >= (a.duration or 10.0):
                    break
                if abs(t - 5.0) < dt_sim / 2:     # simulate pressing "faster" at 5 s
                    freq = min(freq * 4, a.max_freq)
            else:
                now = time.perf_counter()
                t, dt = now - t0, now - last
                last = now
                if a.duration and t >= a.duration:
                    break

            phase = (phase + freq * dt) % 1.0      # integrated: speed changes are smooth
            grow = 1.0 if a.ramp_in == 0 else min(t / a.ramp_in, 1.0)
            r = r_max * size * grow
            gx = mid + r * math.cos(2 * math.pi * phase)
            gy = mid + r * math.sin(2 * math.pi * phase)
            max_step = a.slew * min(dt, dt_cap) * 1e3
            x, y = step_toward(x, gx, max_step), step_toward(y, gy, max_step)
            marker.set(phase < 0.5)
            cx, cy = dac.set_xy(x, y)
            cmax = max(cmax, cx, cy)
            dac.refresh_range()
            updates += 1
            win_updates += 1

            if not a.dry_run:
                now = time.perf_counter()
                if now >= next_ui:                 # keys + status ~5 times per second
                    for k in keys.read():
                        if k in ("up", "+", "="):
                            freq = min(freq * 1.1, a.max_freq)
                        elif k in ("down", "-", "_"):
                            freq = max(freq / 1.1, 0.1)
                        elif k in ("right", "]"):
                            size = min(size + 0.05, 1.0)
                        elif k in ("left", "["):
                            size = max(size - 0.05, 0.0)
                        elif k in ("q", "Q"):
                            stopping = True
                    span = now - ui_last
                    ups = win_updates / span if span > 0 else 0
                    need = 2 * math.pi * freq * r_max * size / 1e3        # V/ms the circle needs
                    sys.stdout.write(
                        f"\r{freq:6.1f} rev/s  size {size * 100:3.0f} %  {ups:5.0f} updates/s  "
                        f"{ups / freq:5.0f} points/rev  "
                        + ("SLEW-LIMITED " if need > a.slew else "             ")
                        + f"retries {dac.retries}  ")
                    sys.stdout.flush()
                    win_updates = 0
                    ui_last, next_ui = now, now + 0.2
                if a.rate:
                    rest = last + 1 / a.rate - time.perf_counter()
                    if rest > 0:
                        time.sleep(rest)

        # soft stop: ramp both channels down to 0 V at the slew limit
        print()
        stop_last = time.perf_counter()
        while x > 0 or y > 0:
            if a.dry_run:
                dt = dt_sim
            else:
                time.sleep(0.001)
                now = time.perf_counter()
                dt, stop_last = now - stop_last, now
            max_step = a.slew * min(dt, 0.002) * 1e3
            x, y = step_toward(x, 0.0, max_step), step_toward(y, 0.0, max_step)
            dac.set_xy(x, y)
        ok = True
    finally:
        if keys:
            keys.close()                           # always give the terminal back
        if not ok:
            try:
                dac.set_xy(0.0, 0.0)
            except OSError:
                print("WARNING: could not set 0 V after an error; the DAC holds its last "
                      "value (<= 5 V)", file=sys.stderr)
        marker.close()
        dac.close()
        print(f"outputs at 0 V. {updates} updates, highest code {cmax} = "
              f"{code_to_volts(cmax):.3f} V, {dac.retries} retried I2C writes")
        if a.dry_run:
            assert dac.max_code <= gp8403.MAX_CODE_ALLOWED
            print(f"dry run OK: highest code sent would be {dac.max_code} "
                  f"(cap {gp8403.MAX_CODE_ALLOWED})")


if __name__ == "__main__":
    sys.exit(main())
