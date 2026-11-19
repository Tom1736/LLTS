#!/usr/bin/env python3
"""Draw a square with the galvos: corners at 0 V and 5 V on both axes, at full I2C speed.

    python3 galvo_square.py

Same drawing method as galvo_text.py: the square is a fixed loop of points, already
encoded as I2C messages, sent back to back as fast as the 400 kHz bus allows. The square
is one closed line, so there is no jump and no return line.
  - --step: volts between points; smaller = more points = slower and brighter (Up/Down).
  - --size: side length as a fraction of 5 V, centered on 2.5 V (Left/Right). At 1.0
    (default) the corners are exactly (0,0) (5,0) (5,5) (0,5).
  - --dwell: extra points held at each corner so the mirrors reach it (sharper corners).

Keys (needs a terminal: ssh -t ...):
  Up / +      faster (bigger step)    Left / [    smaller (-5 %)
  Down / -    slower (smaller step)   Right / ]   bigger (+5 %)
  q / Ctrl-C  ramp down to 0 V and quit

Never above 5 V: every point goes through gp8403.volts_to_code() when the loop is built
and every message is checked again right before it is sent; the range register is held
at 0-5 V. No two consecutive points are more than --max-jump apart (also when starting,
stopping or changing speed/size). GPIO 27 (pin 13) is high during the first half of each
lap, for the scope.

usage: python3 galvo_square.py [--step 0.1] [--size 1] [--dwell 2] [--combined]
                               [--max-jump 1] [--duration 0] [--dry-run]
"""
import argparse
import signal
import sys
import time

import gp8403
from gp8403 import MAX_VOLTS, encode_xy
from galvo_circle import Keys
from galvo_text import DryWriter, line_points, max_jump, path_points, TRAVEL_STEP_MAX

MID = MAX_VOLTS / 2           # 2.5 V: center of the square


def square_points(size, step, dwell):
    """One lap, counter-clockwise from the lower left corner; the start is not repeated."""
    h = MID * size
    lo, hi = MID - h, MID + h
    corners = [(lo, lo), (hi, lo), (hi, hi), (lo, hi), (lo, lo)]
    pts = path_points(corners, step, dwell)        # starts and ends at (lo, lo)
    pts = [(*pts[0][:2], True)] * dwell + pts      # dwell at the first corner too
    while len(pts) > 1 and pts[-1][:2] == pts[0][:2]:
        pts.pop()                                  # it loops: don't repeat the start
    return pts


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--addr", type=lambda s: int(s, 0), default=gp8403.DEFAULT_ADDR)
    p.add_argument("--step", type=float, default=0.1,
                   help="V between points (default 0.1); smaller = slower, brighter")
    p.add_argument("--size", type=float, default=1.0,
                   help="side as a fraction of 5 V, centered on 2.5 V (default 1 = 0..5 V)")
    p.add_argument("--dwell", type=int, default=2, help="extra points at each corner (default 2)")
    p.add_argument("--max-jump", type=float, default=1.0,
                   help=f"largest change between two points in V (default 1, max {TRAVEL_STEP_MAX:g})")
    p.add_argument("--combined", action="store_true",
                   help="X and Y in one I2C message (faster; needs the DAC's register auto-increment)")
    p.add_argument("--duration", type=float, default=0.0, help="s, 0 = until q / Ctrl-C")
    p.add_argument("--marker", type=int, default=27, help="scope marker GPIO, -1 = off")
    p.add_argument("--dry-run", action="store_true",
                   help="no I2C/GPIO/keys; send 20000 points into a recorder instead")
    a = p.parse_args()

    if not 0 < a.size <= 1:
        p.error("--size must be > 0 and <= 1 (1 = 0..5 V)")
    if not 0 < a.max_jump <= TRAVEL_STEP_MAX:
        p.error(f"--max-jump must be > 0 and <= {TRAVEL_STEP_MAX:g}")
    if not 0 < a.step <= a.max_jump:
        p.error("--step must be > 0 and <= --max-jump")
    if a.dwell < 0 or a.duration < 0:
        p.error("--dwell, --duration must be >= 0")

    step, size = a.step, a.size

    def make_lap():
        pts = square_points(size, step, a.dwell)
        assert max_jump(pts + pts[:1]) <= a.max_jump + 1e-9     # incl. the wrap to the start
        return pts, [encode_xy(x, y, a.combined) for x, y, _ in pts]   # the cap applies here

    def approach(frm, to):
        return line_points(frm, to, a.max_jump) if frm != to else []

    pts, enc = make_lap()
    dac = DryWriter() if a.dry_run else gp8403.GP8403(a.addr)
    marker = gp8403.NoMarker() if a.dry_run else gp8403.make_marker(a.marker)
    keys = None if a.dry_run else Keys()

    stopping = False

    def request_stop(*_):
        nonlocal stopping
        stopping = True
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    lo, hi = MID - MID * size, MID + MID * size
    print(f"{'DRY RUN, nothing is written. ' if a.dry_run else ''}"
          f"square {lo:g}..{hi:g} V, {len(pts)} points per lap, step {step:g} V, dwell {a.dwell}, "
          f"{'1 message' if a.combined else '2 messages'} per point, cap {MAX_VOLTS} V.")
    if keys and keys.on:
        print("Up/Down or +/-: speed   Left/Right or [/]: size   q: quit")
    elif not a.dry_run:
        print("no terminal (use ssh -t for keys); fixed settings, Ctrl-C or --duration to stop")

    def send(seq):
        for x, y in seq:
            dac.write_encoded(encode_xy(x, y, a.combined))

    pos = (0.0, 0.0)                              # our scripts always leave the DAC at 0 V
    sent = laps = 0
    t0 = time.perf_counter()
    ok = False
    try:
        dac.write_encoded(encode_xy(0.0, 0.0, a.combined))
        send(approach(pos, pts[0][:2]))
        n, k = len(enc), 0
        win_pts, win_t = 0, time.perf_counter()
        while not stopping:
            dac.write_encoded(enc[k])
            pos = pts[k][:2]
            sent += 1
            k += 1
            if k >= n:
                k, laps = 0, laps + 1
            marker.set(k < n // 2)

            if sent & 255:                        # housekeeping every 256 points only
                continue
            dac.refresh_range()
            if a.dry_run:
                stopping = sent >= 20000
                continue
            now = time.perf_counter()
            if a.duration and now - t0 >= a.duration:
                stopping = True
            if now - win_t < 0.2:                 # keys + status ~5 times per second
                continue
            new_step, new_size = step, size
            for key in keys.read():
                if key in ("up", "+", "="):
                    new_step = min(new_step * 1.1, a.max_jump)
                elif key in ("down", "-", "_"):
                    new_step = max(new_step / 1.1, 0.005)
                elif key in ("right", "]"):
                    new_size = min(new_size + 0.05, 1.0)
                elif key in ("left", "["):
                    new_size = max(new_size - 0.05, 0.05)
                elif key in ("q", "Q"):
                    stopping = True
            ups = (sent - win_pts) / (now - win_t)
            sys.stdout.write(
                f"\rstep {step:6.3f} V  size {size * 100:3.0f} % ({MID - MID * size:4.2f}..{MID + MID * size:4.2f} V)  "
                f"{ups:5.0f} points/s  {n:5d} points/lap  {ups / n:6.1f} laps/s  retries {dac.retries}  ")
            sys.stdout.flush()
            win_pts, win_t = sent, now
            if (new_step, new_size) != (step, size) and not stopping:
                frac = k / max(n - 1, 1)          # continue at the same place on the lap
                step, size = new_step, new_size
                pts, enc = make_lap()
                n = len(enc)
                k = round(frac * (n - 1))
                send(approach(pos, pts[k][:2]))

        print()                                   # soft stop: back to 0 V in small steps
        send(approach(pos, (0.0, 0.0)))
        dac.write_encoded(encode_xy(0.0, 0.0, a.combined))
        ok = True
    finally:
        if keys:
            keys.close()                           # always give the terminal back
        if not ok:
            try:
                dac.write_encoded(encode_xy(0.0, 0.0, a.combined))
            except OSError:
                print("WARNING: could not set 0 V after an error; the DAC holds its last "
                      "value (<= 5 V)", file=sys.stderr)
        marker.close()
        dac.close()
        el = time.perf_counter() - t0
        print(f"outputs at 0 V. {sent} points" +
              ("" if a.dry_run else f" in {el:.1f} s ({sent / max(el, 1e-9):.0f}/s), "
               f"{laps} laps, {dac.retries} retried I2C writes"))
        if a.dry_run:
            assert dac.max_code <= gp8403.MAX_CODE_ALLOWED
            print(f"dry run OK: highest code sent would be {dac.max_code} "
                  f"(cap {gp8403.MAX_CODE_ALLOWED}), largest jump {max_jump(dac.trace):.3f} V")
            main.trace = dac.trace
            main.lap = pts


if __name__ == "__main__":
    sys.exit(main())
