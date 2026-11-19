#!/usr/bin/env python3
"""Move the galvos with the GP8403 DAC: oscillate between 0 V and 5 V, never above 5 V.

The galvos are damaged above 5 V. The cap is enforced in gp8403.py (range register held at
0-5 V, every value clamped and asserted, MAX_VOLTS fixed there). This script adds:
  - --low/--high must lie in [0, 5]; anything else is refused, not clamped silently.
  - Slew limit (--slew, V/ms): the output never jumps; even the square wave gets ramped
    edges. That protects the galvo from full-scale current spikes.
  - Soft start: the swing grows from 0 to full over --ramp-in seconds.
  - Soft stop: on Ctrl-C / SIGTERM / --duration the output ramps down to 0 V at the slew
    limit. On an I2C error it writes 0 V directly.
  - --dry-run: computes everything, writes nothing, and reports the highest code it
    would have sent.

Channel 0 = X galvo, channel 1 = Y galvo. Shapes:
  sine, triangle, square : 0 -> high -> 0 on --axis x, y or both (same signal on both)
  circle                 : X = cos, Y = sin around the middle of [low, high]
Marker GPIO 27 (pin 13, GND pin 14) is high during the first half of every period, so
the scope can trigger on the start of each cycle.

usage: python3 galvo_test.py [--shape sine|triangle|square|circle] [--axis x|y|both]
                             [--freq 1] [--low 0] [--high 5] [--slew 1] [--ramp-in 2]
                             [--duration 0] [--rate 1000] [--marker 27] [--dry-run]
"""
import argparse
import math
import signal
import sys
import time

import gp8403
from gp8403 import MAX_VOLTS, volts_to_code, code_to_volts


class DryDAC:
    """Stands in for GP8403 with --dry-run: no I2C, records the highest code."""
    def __init__(self):
        self.retries = 0
        self.max_code = 0

    def refresh_range(self):
        pass

    def set_xy(self, vx, vy, combined=False):
        cx, cy = volts_to_code(vx), volts_to_code(vy)
        self.max_code = max(self.max_code, cx, cy)
        return cx, cy

    def close(self):
        pass


def unit_wave(shape, phase):
    """0..1 waveform that starts at 0 for phase 0 (so the soft start begins at 0 V)."""
    if shape == "sine":
        return (1 - math.cos(2 * math.pi * phase)) / 2
    if shape == "triangle":
        return 2 * phase if phase < 0.5 else 2 * (1 - phase)
    if shape == "square":
        return 0.0 if phase < 0.5 else 1.0
    raise ValueError(shape)


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--addr", type=lambda s: int(s, 0), default=gp8403.DEFAULT_ADDR)
    p.add_argument("--shape", choices=["sine", "triangle", "square", "circle"], default="sine")
    p.add_argument("--axis", choices=["x", "y", "both"], default="x",
                   help="which galvo moves (ignored for circle); the other stays at 0 V")
    p.add_argument("--freq", type=float, default=1.0, help="Hz (default 1, start slow)")
    p.add_argument("--low", type=float, default=0.0, help="lower voltage, 0..5")
    p.add_argument("--high", type=float, default=MAX_VOLTS, help="upper voltage, 0..5")
    p.add_argument("--slew", type=float, default=1.0,
                   help="max change in V per ms (default 1 = full 5 V swing in 5 ms); "
                        "set it from the galvo datasheet")
    p.add_argument("--ramp-in", type=float, default=2.0, help="soft start in s (default 2)")
    p.add_argument("--duration", type=float, default=0.0, help="s, 0 = until Ctrl-C")
    p.add_argument("--rate", type=float, default=1000.0, help="DAC updates per s (default 1000)")
    p.add_argument("--marker", type=int, default=27, help="scope marker GPIO, -1 = off")
    p.add_argument("--dry-run", action="store_true", help="no I2C/GPIO, just check the values")
    a = p.parse_args()

    for name in ("low", "high"):
        v = getattr(a, name)
        if not 0.0 <= v <= MAX_VOLTS:
            p.error(f"--{name} must be between 0 and {MAX_VOLTS} V (the galvo is damaged above 5 V)")
    if a.low >= a.high:
        p.error("--low must be below --high")
    if a.freq <= 0 or a.slew <= 0 or a.rate <= 0 or a.ramp_in < 0 or a.duration < 0:
        p.error("--freq, --slew, --rate must be > 0; --ramp-in, --duration >= 0")

    dac = DryDAC() if a.dry_run else gp8403.GP8403(a.addr)
    marker = gp8403.NoMarker() if a.dry_run else gp8403.make_marker(a.marker)

    stopping = False

    def request_stop(*_):
        nonlocal stopping
        stopping = True
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    span = a.high - a.low
    mid = (a.low + a.high) / 2
    period = 1.0 / a.freq
    dt_target = 1.0 / a.rate

    def target(t):
        """Where the output should be at time t: soft start, then the waveform."""
        grow = 1.0 if a.ramp_in == 0 else min(t / a.ramp_in, 1.0)
        phase = (t % period) / period
        if a.shape == "circle":
            r = span / 2 * grow
            return mid + r * math.cos(2 * math.pi * phase), mid + r * math.sin(2 * math.pi * phase), phase
        v = a.low + span * grow * unit_wave(a.shape, phase)
        vx = v if a.axis in ("x", "both") else 0.0
        vy = v if a.axis in ("y", "both") else 0.0
        return vx, vy, phase

    def step_toward(cur, goal, max_step):
        d = goal - cur
        return goal if abs(d) <= max_step else cur + math.copysign(max_step, d)

    print(f"{'DRY RUN, nothing is written. ' if a.dry_run else ''}"
          f"{a.shape} {a.low:g}..{a.high:g} V at {a.freq:g} Hz"
          + ("" if a.shape == "circle" else f" on {a.axis}")
          + f", slew {a.slew:g} V/ms, soft start {a.ramp_in:g} s, {a.rate:g} updates/s, "
          f"cap {MAX_VOLTS} V (code <= {gp8403.MAX_CODE_ALLOWED}). Ctrl-C ramps down to 0 V.",
          flush=True)

    x = y = 0.0                                   # our scripts always leave the DAC at 0 V
    updates, wmax, cmax = 0, 0.0, 0
    sim_t = 0.0                                   # dry run: simulated clock, no sleeping
    t0 = time.perf_counter()
    last = t0
    ok = False
    try:
        dac.set_xy(0.0, 0.0)
        while True:
            if a.dry_run:
                sim_t += dt_target
                t, dt = sim_t, dt_target
                if (a.duration or 10.0) <= t:     # dry run defaults to 10 simulated s
                    break
            else:
                now = time.perf_counter()
                t, dt = now - t0, now - last
                last = now
                if stopping or (a.duration and t >= a.duration):
                    break
            gx, gy, phase = target(t)
            # V allowed since the last update; a stall doesn't earn a bigger jump
            max_step = a.slew * min(dt, 2 * dt_target) * 1e3
            x, y = step_toward(x, gx, max_step), step_toward(y, gy, max_step)
            marker.set(phase < 0.5)
            w0 = time.perf_counter()
            cx, cy = dac.set_xy(x, y)
            wmax = max(wmax, time.perf_counter() - w0)
            cmax = max(cmax, cx, cy)
            updates += 1
            dac.refresh_range()
            if not a.dry_run:
                rest = (last + dt_target) - time.perf_counter()
                if rest > 0:
                    time.sleep(rest)
        # soft stop: ramp both channels down to 0 V at the slew limit
        stop_last = time.perf_counter()
        while x > 0 or y > 0:
            if a.dry_run:
                dt = dt_target
            else:
                time.sleep(dt_target)
                now = time.perf_counter()
                dt, stop_last = now - stop_last, now
            max_step = a.slew * min(dt, 2 * dt_target) * 1e3
            x, y = step_toward(x, 0.0, max_step), step_toward(y, 0.0, max_step)
            dac.set_xy(x, y)
        ok = True
    finally:
        if not ok:                                # error path: get to 0 V directly
            try:
                dac.set_xy(0.0, 0.0)
            except OSError:
                print("WARNING: could not set 0 V after an error; the DAC holds its last "
                      "value (<= 5 V)", file=sys.stderr)
        marker.close()
        dac.close()
        elapsed = time.perf_counter() - t0
        print(f"outputs at 0 V. {updates} updates"
              + ("" if a.dry_run else f" in {elapsed:.1f} s ({updates / max(elapsed, 1e-9):.0f}/s), "
                 f"slowest write {wmax * 1e3:.2f} ms, {dac.retries} retried I2C writes")
              + f", highest code {cmax} = {code_to_volts(cmax):.3f} V")
        if a.dry_run:
            assert dac.max_code <= gp8403.MAX_CODE_ALLOWED
            print(f"dry run OK: highest code sent would be {dac.max_code} "
                  f"(cap {gp8403.MAX_CODE_ALLOWED})")


if __name__ == "__main__":
    sys.exit(main())
