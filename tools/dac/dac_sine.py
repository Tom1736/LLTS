#!/usr/bin/env python3
"""Put a sine wave on the GP8403 DAC: 50 Hz between 0 V and 10 V by default.

    python3 dac_sine.py                      # 50 Hz, 0..10 V on channel 0
    python3 dac_sine.py --freq 20 --high 5   # 20 Hz, 0..5 V
    python3 dac_sine.py --channel both       # same sine on both channels

Uses the DAC's 0-10 V range (--range 10, the default since the hardware upgrade of
2026-11-18). --range 5 uses the 0-5 V range with finer steps (1.2 mV instead of 2.4 mV).

How it runs: the loop writes as fast as the 400 kHz I2C bus allows and computes each
value from the clock, v = low + (high - low) * (1 - cos(2 pi f t)) / 2, so the frequency
is exact even when single writes are late. One channel = one 3-byte message per update
(about 6000 updates/s, roughly 120 points per 50 Hz period); both channels take two
messages per update unless --combined. The status line shows the real numbers.

Never above the range's cap (10 V, or 5 V with --range 5): every value goes through
gp8403.volts_to_code() for that range, every message is checked again before it is
sent, and the range register is held at the chosen range. --low/--high outside the range
are refused. Soft start: the swing grows from 0 over --ramp-in seconds. No two consecutive
values differ by more than --max-jump volts (also when a write was late, and when
stopping). Ctrl-C / SIGTERM / --duration ramp the output down to 0 V.
GPIO 27 (pin 13, GND pin 14) is high during the first half of every period: trigger the
scope on it.

usage: python3 dac_sine.py [--freq 50] [--low 0] [--high 10] [--range 10|5]
                           [--channel 0|1|both] [--combined] [--ramp-in 1] [--max-jump 1]
                           [--duration 0] [--marker 27] [--dry-run]
"""
import argparse
import math
import signal
import sys
import time

import gp8403
from gp8403 import RANGES, code_to_volts, decode_payload, encode_ch, encode_xy


class DryWriter:
    """Stands in for GP8403 with --dry-run: no I2C, checks and records what would be sent."""
    def __init__(self, range_volts):
        self.range_volts = range_volts
        self.retries = 0
        self.max_code = 0
        self.trace = []

    def write_encoded(self, group):
        for msg in group:
            gp8403.check_payload(msg, self.range_volts)
        codes = dict(decode_payload(group))
        self.max_code = max(self.max_code, *codes.values())
        self.trace.append({reg: code_to_volts(c, self.range_volts) for reg, c in codes.items()})

    def refresh_range(self):
        pass

    def close(self):
        pass


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--addr", type=lambda s: int(s, 0), default=gp8403.DEFAULT_ADDR)
    p.add_argument("--freq", type=float, default=50.0, help="Hz (default 50)")
    p.add_argument("--low", type=float, default=0.0, help="lowest voltage (default 0)")
    p.add_argument("--high", type=float, default=None,
                   help="highest voltage (default: the range's cap, 10 V)")
    p.add_argument("--range", type=int, choices=sorted(RANGES), default=10,
                   help="DAC output range in V (default 10)")
    p.add_argument("--channel", choices=["0", "1", "both"], default="0")
    p.add_argument("--combined", action="store_true",
                   help="with --channel both: one I2C message for both (needs the DAC's "
                        "register auto-increment)")
    p.add_argument("--ramp-in", type=float, default=1.0, help="soft start in s (default 1)")
    p.add_argument("--max-jump", type=float, default=1.0,
                   help="largest change between two updates in V (default 1)")
    p.add_argument("--duration", type=float, default=0.0, help="s, 0 = until Ctrl-C")
    p.add_argument("--marker", type=int, default=27, help="scope marker GPIO, -1 = off")
    p.add_argument("--dry-run", action="store_true",
                   help="no I2C/GPIO; simulate 3 s at 6000 updates/s and check the values")
    a = p.parse_args()

    cap = RANGES[a.range][1]
    high = cap if a.high is None else a.high
    for name, v in (("low", a.low), ("high", high)):
        if not 0.0 <= v <= cap:
            p.error(f"--{name} must be between 0 and {cap:g} V for --range {a.range}")
    if a.low >= high:
        p.error("--low must be below --high")
    if a.freq <= 0 or a.max_jump <= 0 or a.ramp_in < 0 or a.duration < 0:
        p.error("--freq, --max-jump must be > 0; --ramp-in, --duration >= 0")
    channels = [0, 1] if a.channel == "both" else [int(a.channel)]
    rv = a.range

    def encode(v):
        if len(channels) == 1:
            return encode_ch(v, channels[0], rv)
        return encode_xy(v, v, a.combined, rv)

    dac = DryWriter(rv) if a.dry_run else gp8403.GP8403(a.addr, range_volts=rv)
    marker = gp8403.NoMarker() if a.dry_run else gp8403.make_marker(a.marker)

    stopping = False

    def request_stop(*_):
        nonlocal stopping
        stopping = True
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    span = high - a.low
    print(f"{'DRY RUN, nothing is written. ' if a.dry_run else ''}"
          f"sine {a.freq:g} Hz, {a.low:g}..{high:g} V on channel {a.channel}, DAC range 0-{rv} V "
          f"(cap {cap:g} V, code <= {RANGES[rv][3]}), soft start {a.ramp_in:g} s. "
          f"Ctrl-C ramps down to 0 V.", flush=True)

    def step_toward(cur, goal):
        d = goal - cur
        return goal if abs(d) <= a.max_jump else cur + math.copysign(a.max_jump, d)

    v = 0.0                                       # our scripts always leave the DAC at 0 V
    sent = 0
    dt_sim = 1 / 6000
    t0 = time.perf_counter()
    win_n, win_t = 0, t0
    show = sys.stdout.isatty() and not a.dry_run
    ok = False
    try:
        dac.write_encoded(encode(0.0))
        while not stopping:
            t = sent * dt_sim if a.dry_run else time.perf_counter() - t0
            phase = (t * a.freq) % 1.0
            grow = 1.0 if a.ramp_in == 0 else min(t / a.ramp_in, 1.0)
            v = step_toward(v, a.low + span * grow * (1 - math.cos(2 * math.pi * phase)) / 2)
            marker.set(phase < 0.5)
            dac.write_encoded(encode(v))
            sent += 1

            if sent & 255:                        # housekeeping every 256 updates only
                continue
            dac.refresh_range()
            if a.dry_run:
                stopping = t >= (a.duration or 3.0)
                continue
            now = time.perf_counter()
            if a.duration and now - t0 >= a.duration:
                stopping = True
            if show and now - win_t >= 0.5:
                ups = (sent - win_n) / (now - win_t)
                sys.stdout.write(f"\r{ups:6.0f} updates/s  {ups / a.freq:5.0f} points per period  "
                                 f"{t:7.1f} s  retries {dac.retries}  ")
                sys.stdout.flush()
                win_n, win_t = sent, now

        if show:
            print()
        while v > 0:                              # soft stop: down to 0 V in --max-jump steps
            v = step_toward(v, 0.0)
            dac.write_encoded(encode(v))
        ok = True
    finally:
        if not ok:
            try:
                dac.write_encoded(encode(0.0))
            except OSError:
                print(f"WARNING: could not set 0 V after an error; the DAC holds its last "
                      f"value (<= {cap:g} V)", file=sys.stderr)
        marker.close()
        dac.close()
        el = time.perf_counter() - t0
        print(f"outputs at 0 V. {sent} updates" +
              ("" if a.dry_run else f" in {el:.1f} s ({sent / max(el, 1e-9):.0f}/s, "
               f"{sent / max(el, 1e-9) / a.freq:.0f} points per period), "
               f"{dac.retries} retried I2C writes"))
        if a.dry_run:
            assert dac.max_code <= RANGES[rv][3]
            print(f"dry run OK: highest code {dac.max_code} = "
                  f"{code_to_volts(dac.max_code, rv):.3f} V (cap {RANGES[rv][3]})")
            main.trace = dac.trace


if __name__ == "__main__":
    sys.exit(main())
