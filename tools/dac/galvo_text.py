#!/usr/bin/env python3
"""Write a text with the galvos at full I2C speed, adjustable live from the keyboard.

    python3 galvo_text.py "HELLO"

How it draws: the text becomes a fixed list of points, already encoded as I2C messages.
The loop just sends them back to back, as fast as the 400 kHz bus allows; nothing waits.
On the lines, points are --step volts apart: smaller step = more points per letter =
slower and brighter. That is the speed setting (Up/Down). --dwell extra points at
corners keep them sharp.

Fonts (--font):
  connected (default)  connected_font.py: the whole text is ONE unbroken line, letters
                       joined like handwriting, so the beam never jumps. A-Z, 0-9 and
                       space; Ä Ö Ü ß become AE OE UE SS, other characters are dropped.
  strokes              stroke_font.py: separate strokes with more characters
                       (- + = _ . , : ! ? ' / * < > ( ), Ä Ö Ü). The moves between strokes
                       are single jumps (--travel-step), held for --settle points at both
                       ends; strokes are reordered so the moves stay short.

Getting from the end of the text back to its start (--mode):
  bounce (default)     every second frame runs backwards through the same line, so the
                       beam never leaves the text.
  underline            the return is drawn as a line under the text (end -> down ->
                       left under the text -> up to the start), then the next frame runs
                       forwards again.

Keys (needs a terminal: ssh -t ...):
  Up / +      faster (bigger step)    Left / [    smaller (-5 %)
  Down / -    slower (smaller step)   Right / ]   bigger (+5 %)
  q / Ctrl-C  ramp down to 0 V and quit

The image is mirrored top/bottom by default (--flip-y, matches the galvo setup);
--no-flip-y turns that off, --flip-x mirrors left/right. There is no laser on/off control
yet; with --laser-gpio N, GPIO N is high while drawing and low during moves (strokes font).

Never above 5 V: every point goes through gp8403.volts_to_code() when the list is built,
and every message is checked again right before it is sent (no range writes, no code
above the cap); the range register is held at 0-5 V. The text is fitted inside
[--low, --high]. No two consecutive points are more than --travel-step apart (also when
starting, stopping, or changing speed/size), so the galvo never gets a bigger jump.

usage: python3 galvo_text.py TEXT [--font connected|strokes] [--mode bounce|underline]
                             [--step 0.1] [--size 1] [--dwell 1] [--combined]
                             [--flip-x] [--no-flip-y] [--travel-step 1] [--settle 2]
                             [--laser-gpio N] [--duration 0] [--dry-run]
"""
import argparse
import math
import signal
import sys
import time

import connected_font
import gp8403
import stroke_font
from gp8403 import MAX_VOLTS, code_to_volts, encode_xy, decode_payload
from galvo_circle import Keys

TRAVEL_STEP_MAX = 5.0         # V per point; even a whole-range jump is at most this
UNDERLINE_GAP = 1.5           # font units between the lowest point of the text and the underline


def path_points(path, step, dwell):
    """One unbroken polyline -> points (x, y, True), <= step apart, `dwell` extra at corners."""
    pts = [(*path[0], True)]
    for p, q in zip(path, path[1:]):
        if math.hypot(q[0] - p[0], q[1] - p[1]) <= 1e-12:
            continue
        pts += [(x, y, True) for x, y in line_points(p, q, step)]
        pts += [(*q, True)] * dwell
    return pts


def underline_for(groups):
    """Underline in font units, right to left, UNDERLINE_GAP below everything in groups."""
    xs = [x for g in groups for x, _ in g]
    yu = min(y for g in groups for _, y in g) - UNDERLINE_GAP
    return [(max(xs), yu), (min(xs), yu)]


def to_volts(strokes, lo, hi, size, flip_x, flip_y):
    """Font-unit strokes -> strokes in volts, centered and fitted inside [lo, hi]."""
    xs = [x for s in strokes for x, _ in s]
    ys = [y for s in strokes for _, y in s]
    w, h = max(max(xs) - min(xs), 1e-9), max(max(ys) - min(ys), 1e-9)
    scale = size * min((hi - lo) / w, (hi - lo) / h)
    cx, cy, mid = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2, (lo + hi) / 2

    def tv(p):
        x = mid + (p[0] - cx) * scale * (-1 if flip_x else 1)
        y = mid + (p[1] - cy) * scale * (-1 if flip_y else 1)
        return min(max(x, lo), hi), min(max(y, lo), hi)
    return [[tv(p) for p in s] for s in strokes]


def order_strokes(strokes):
    """Greedy nearest-neighbour order (strokes may be reversed) to keep the moves short.
    Starts at the leftmost point, so the frame runs roughly left to right."""
    left = min(range(len(strokes)), key=lambda k: min(p[0] for p in strokes[k]))
    s0 = strokes[left]
    out = [s0 if s0[0][0] <= s0[-1][0] else s0[::-1]]
    rest = strokes[:left] + strokes[left + 1:]
    while rest:
        px, py = out[-1][-1]
        best, rev, bd = 0, False, float("inf")
        for k, s in enumerate(rest):
            for r, (qx, qy) in ((False, s[0]), (True, s[-1])):
                d = (qx - px) ** 2 + (qy - py) ** 2
                if d < bd:
                    best, rev, bd = k, r, d
        s = rest.pop(best)
        out.append(s[::-1] if rev else s)
    return out


def line_points(p, q, spacing):
    """Points from p (exclusive) to q (inclusive), at most `spacing` apart."""
    n = max(1, math.ceil(math.hypot(q[0] - p[0], q[1] - p[1]) / spacing - 1e-9))
    return [(p[0] + (q[0] - p[0]) * k / n, p[1] + (q[1] - p[1]) * k / n) for k in range(1, n + 1)]


def build_frame(strokes_v, step, travel_step, dwell, settle):
    """One frame: list of (x, y, laser_on). Consecutive points are <= travel_step apart."""
    pts = []
    pos = None
    for stroke in strokes_v:
        start = stroke[0]
        if pos is None:
            pts += [(*start, False)] * settle
        elif math.hypot(start[0] - pos[0], start[1] - pos[1]) > 1e-9:
            pts += [(*pos, True)] * settle                     # let the mirrors reach the end
            pts += [(x, y, False) for x, y in line_points(pos, start, travel_step)]
            pts += [(*start, False)] * settle                  # ... and the next start
        for p, q in zip(stroke, stroke[1:]):
            pts += [(x, y, True) for x, y in line_points(p, q, step)]
            pts += [(*q, True)] * dwell                        # corner
        pos = stroke[-1]
    pts += [(*pos, True)] * settle
    return pts


def max_jump(points):
    return max((max(abs(a[0] - b[0]), abs(a[1] - b[1])) for a, b in zip(points, points[1:])),
               default=0.0)


class DryWriter:
    """Stands in for GP8403 with --dry-run: decodes and records what would be sent."""
    def __init__(self):
        self.retries = 0
        self.max_code = 0
        self.trace = []

    def write_encoded(self, group):
        for msg in group:
            gp8403.check_payload(msg)
        codes = dict(decode_payload(group))
        self.max_code = max(self.max_code, *codes.values())
        self.trace.append((code_to_volts(codes[2]), code_to_volts(codes[4])))

    def refresh_range(self):
        pass

    def close(self):
        pass


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("text", help='text to draw, e.g. "HELLO" (quote it if it has spaces)')
    p.add_argument("--addr", type=lambda s: int(s, 0), default=gp8403.DEFAULT_ADDR)
    p.add_argument("--font", choices=["connected", "strokes"], default="connected",
                   help="connected = one unbroken line (default), strokes = separate strokes")
    p.add_argument("--mode", choices=["bounce", "underline"], default="bounce",
                   help="back to the start: bounce = run backwards through the text (default), "
                        "underline = draw a line under the text")
    p.add_argument("--step", type=float, default=0.1,
                   help="V between points on the letters (default 0.1); smaller = slower, brighter")
    p.add_argument("--travel-step", type=float, default=1.0,
                   help=f"V between points on moves between strokes, and the largest change "
                        f"between any two points (default 1, max {TRAVEL_STEP_MAX:g})")
    p.add_argument("--dwell", type=int, default=1, help="extra points at corners (default 1)")
    p.add_argument("--settle", type=int, default=2,
                   help="points held before and after each move (default 2)")
    p.add_argument("--size", type=float, default=1.0, help="fraction of the area, 0..1")
    p.add_argument("--low", type=float, default=0.0, help="lower edge of the drawing area, 0..5")
    p.add_argument("--high", type=float, default=MAX_VOLTS, help="upper edge of the drawing area, 0..5")
    p.add_argument("--combined", action="store_true",
                   help="X and Y in one I2C message (faster; needs the DAC's register "
                        "auto-increment: if the text collapses into a line, leave it off)")
    p.add_argument("--flip-x", action="store_true", help="mirror left/right")
    p.add_argument("--flip-y", action=argparse.BooleanOptionalAction, default=True,
                   help="mirror up/down (default on, matches the galvo setup; --no-flip-y = off)")
    p.add_argument("--laser-gpio", type=int, default=-1,
                   help="GPIO high while drawing, low during moves (default -1 = none)")
    p.add_argument("--duration", type=float, default=0.0, help="s, 0 = until q / Ctrl-C")
    p.add_argument("--marker", type=int, default=27,
                   help="scope marker GPIO, high during forward frames; -1 = off")
    p.add_argument("--dry-run", action="store_true",
                   help="no I2C/GPIO/keys; send 20000 points into a recorder instead")
    a = p.parse_args()

    for name in ("low", "high"):
        if not 0.0 <= getattr(a, name) <= MAX_VOLTS:
            p.error(f"--{name} must be between 0 and {MAX_VOLTS} V (the galvo is damaged above 5 V)")
    if a.low >= a.high:
        p.error("--low must be below --high")
    if not 0 < a.size <= 1:
        p.error("--size must be > 0 and <= 1")
    if not 0 < a.travel_step <= TRAVEL_STEP_MAX:
        p.error(f"--travel-step must be > 0 and <= {TRAVEL_STEP_MAX:g}")
    if not 0 < a.step <= a.travel_step:
        p.error("--step must be > 0 and <= --travel-step")
    if a.dwell < 0 or a.settle < 0 or a.duration < 0:
        p.error("--dwell, --settle, --duration must be >= 0")
    if a.laser_gpio >= 0 and a.laser_gpio == a.marker:
        p.error("--laser-gpio and --marker must be different pins")

    if a.font == "connected":
        text, bad = connected_font.normalize(a.text)
        if bad:
            print(f"dropped {' '.join(map(repr, bad))} (connected font: "
                  f"{connected_font.SUPPORTED.strip()} and space)", file=sys.stderr)
        groups = [connected_font.layout(text)] if text else []
    else:
        text, bad = stroke_font.normalize(a.text)
        if bad:
            print(f"no glyph for {' '.join(map(repr, bad))}, drawn as '?'. "
                  f"Supported: {stroke_font.SUPPORTED}", file=sys.stderr)
        groups = stroke_font.layout(text)
    if not groups:
        p.error("nothing to draw")
    if a.mode == "underline":
        groups = groups + [underline_for(groups)]   # last group = underline, scaled with the text

    step, size = a.step, a.size

    def make_frame():
        gv = to_volts(groups, a.low, a.high, size, a.flip_x, a.flip_y)
        uv = gv.pop() if a.mode == "underline" else None
        if a.font == "connected":
            pts = path_points(gv[0], step, a.dwell)
        else:
            pts = build_frame(order_strokes(gv), step, a.travel_step, a.dwell, a.settle)
        if uv is not None:
            # the way back is drawn: end of text -> down -> left under the text -> up to start
            back = path_points([pts[-1][:2], uv[0], uv[1], pts[0][:2]], step, a.dwell)
            pts += back[1:]
            while len(pts) > 1 and pts[-1][:2] == pts[0][:2]:
                pts.pop()                          # the frame loops: don't repeat the start
        assert max_jump(pts) <= a.travel_step + 1e-9
        assert max_jump([pts[-1], pts[0]]) <= a.travel_step + 1e-9 or a.mode == "bounce"
        enc = [encode_xy(x, y, a.combined) for x, y, _ in pts]   # the cap applies here
        return pts, enc

    def approach(frm, to):
        """Points from frm to to, never more than travel_step apart (laser off)."""
        return [(x, y, False) for x, y in line_points(frm, to, a.travel_step)] \
            if math.hypot(to[0] - frm[0], to[1] - frm[1]) > 1e-9 else []

    pts, enc = make_frame()
    draw_pts = sum(1 for q in pts if q[2])

    dac = DryWriter() if a.dry_run else gp8403.GP8403(a.addr)
    marker = gp8403.NoMarker() if a.dry_run else gp8403.make_marker(a.marker)
    laser = gp8403.NoMarker() if a.dry_run else gp8403.make_marker(a.laser_gpio)
    keys = None if a.dry_run else Keys()

    stopping = False

    def request_stop(*_):
        nonlocal stopping
        stopping = True
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    print(f"{'DRY RUN, nothing is written. ' if a.dry_run else ''}"
          f'"{text}": {a.font} font, {a.mode}, {len(pts)} points per frame '
          f"({draw_pts} drawing, {len(pts) - draw_pts} moving/settling), step {step:g} V, "
          f"{'1 message' if a.combined else '2 messages'} per point, "
          f"{'flip y, ' if a.flip_y else ''}{'flip x, ' if a.flip_x else ''}cap {MAX_VOLTS} V.")
    if keys and keys.on:
        print("Up/Down or +/-: speed   Left/Right or [/]: size   q: quit")
    elif not a.dry_run:
        print("no terminal (use ssh -t for keys); fixed settings, Ctrl-C or --duration to stop")

    def send_points(seq):
        """Send (x, y, on) points without pre-encoding (start, stop, transitions)."""
        for x, y, on in seq:
            laser.set(on)
            dac.write_encoded(encode_xy(x, y, a.combined))

    pos = (0.0, 0.0)                              # our scripts always leave the DAC at 0 V
    sent = frames = 0
    t0 = time.perf_counter()
    ok = False
    try:
        dac.write_encoded(encode_xy(0.0, 0.0, a.combined))
        send_points(approach(pos, pts[0][:2]))    # start: move to the first point, laser off
        n = len(enc)
        k, forward = 0, True                      # bounce: 0 -> n-1 -> 0 -> ..., no return line
        loop = a.mode == "underline"              # underline: 0 -> n-1, 0 -> n-1, ... (closed path)
        marker.set(True)
        win_pts, win_t = 0, time.perf_counter()
        while not stopping:
            laser.set(pts[k][2])
            dac.write_encoded(enc[k])
            pos = pts[k][:2]
            sent += 1
            if loop:
                k += 1
                if k >= n:
                    k, frames = 0, frames + 1
                marker.set(k < n // 2)
            elif forward:
                if k >= n - 1:
                    forward, frames = False, frames + 1
                    marker.set(False)
                    k = max(n - 2, 0)
                else:
                    k += 1
            else:
                if k <= 0:
                    forward, frames = True, frames + 1
                    marker.set(True)
                    k = min(1, n - 1)
                else:
                    k -= 1

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
                    new_step = min(new_step * 1.1, a.travel_step)
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
                f"\rstep {step:6.3f} V  size {size * 100:3.0f} %  {ups:5.0f} points/s  "
                f"{n:5d} points/frame  {ups / n:5.1f} fps  "
                f"= {step * ups / 1e3:4.2f} V/ms on letters  retries {dac.retries}  ")
            sys.stdout.flush()
            win_pts, win_t = sent, now
            if (new_step, new_size) != (step, size) and not stopping:
                # same path at a new spacing/scale: continue at the same place and direction
                frac = k / max(n - 1, 1)
                step, size = new_step, new_size
                pts, enc = make_frame()
                n = len(enc)
                k = round(frac * (n - 1))
                send_points(approach(pos, pts[k][:2]))

        # soft stop: laser off, back to 0 V in steps no bigger than --travel-step
        print()
        laser.low()
        send_points(approach(pos, (0.0, 0.0)))
        dac.write_encoded(encode_xy(0.0, 0.0, a.combined))
        ok = True
    finally:
        if keys:
            keys.close()                           # always give the terminal back
        laser.close()                              # laser pin low, back to input
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
               f"{frames} frames, {dac.retries} retried I2C writes"))
        if a.dry_run:
            assert dac.max_code <= gp8403.MAX_CODE_ALLOWED
            print(f"dry run OK: highest code sent would be {dac.max_code} "
                  f"(cap {gp8403.MAX_CODE_ALLOWED}), largest jump {max_jump(dac.trace):.3f} V")
            main.trace = dac.trace
            main.frame = pts


if __name__ == "__main__":
    sys.exit(main())
