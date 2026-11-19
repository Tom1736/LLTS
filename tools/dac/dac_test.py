#!/usr/bin/env python3
"""Oscillate a DFRobot Gravity 2-channel I2C DAC (GP8403) between 0 V and 5 V.

The output never goes above 5 V: the cap (range register held at 0-5 V, every value
clamped and asserted, MAX_VOLTS fixed) lives in gp8403.py, shared with galvo_test.py.
On exit (Ctrl-C, SIGTERM, error) both channels are set to 0 V.
This script switches hard (square wave = full-scale steps). For the galvos, use
galvo_test.py instead: it limits the slew rate.

Wiring (Gravity -> Pi 3B header): + pin 1 (3.3 V), - pin 6 (GND), C pin 5 (SCL), D pin 3 (SDA).
Needs I2C enabled (dtparam=i2c_arm=on, or raspi-config) and access to /dev/i2c-1.
No Python packages needed: talks to /dev/i2c-1 directly.

Latency: GPIO 27 (header pin 13, GND next to it on pin 14) goes high right before each
high write and low right before each low write. Trigger the scope on it and measure to
the DAC output edge. --marker -1 turns it off.

usage: python3 dac_test.py [--addr 0x5f] [--channel 0|1|both] [--period 0.02]
                           [--shape square|triangle] [--high 5.0] [--cycles N] [--marker 27]
"""
import argparse
import signal
import sys
import time

import gp8403
from gp8403 import MAX_VOLTS, RANGE_REFRESH_S, GP8403, make_marker


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--addr", type=lambda s: int(s, 0), default=gp8403.DEFAULT_ADDR,
                   help="I2C address (default 0x5F, as found on the Pi 3B; module range 0x58-0x5F)")
    p.add_argument("--channel", choices=["0", "1", "both"], default="both")
    p.add_argument("--period", type=float, default=0.02,
                   help="seconds per full 0->5->0 cycle (default 0.02 = 50 Hz, for a scope; "
                        "use 2 for a multimeter)")
    p.add_argument("--shape", choices=["square", "triangle"], default="square")
    p.add_argument("--high", type=float, default=MAX_VOLTS, help="upper voltage, 0..5 (default 5)")
    p.add_argument("--cycles", type=int, default=0, help="stop after N cycles (0 = until Ctrl-C)")
    p.add_argument("--marker", type=int, default=27,
                   help="GPIO for the scope marker (default 27 = header pin 13, GND on pin 14); "
                        "goes high right before the high write, low right before the low write; "
                        "-1 = off")
    a = p.parse_args()

    if not 0.0 <= a.high <= MAX_VOLTS:
        p.error(f"--high must be between 0 and {MAX_VOLTS} V")
    if a.period <= 0:
        p.error("--period must be > 0")
    channels = [0, 1] if a.channel == "both" else [int(a.channel)]

    dac = GP8403(a.addr)
    marker = make_marker(a.marker)

    def stop(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)

    verbose = a.period >= 0.5                  # print every edge only when it's slow enough to read
    print(f"GP8403 @ 0x{a.addr:02x}, channel(s) {channels}, range 0-5 V, "
          f"{a.shape} 0 <-> {a.high:.3f} V, period {a.period * 1e3:g} ms "
          f"({1 / a.period:g} Hz), marker "
          + ("off" if a.marker < 0 else f"GPIO{a.marker}")
          + ". Ctrl-C stops (outputs go to 0 V).", flush=True)
    writes, wsum, wmax, late = 0, 0.0, 0.0, 0

    def write(volts):
        nonlocal writes, wsum, wmax
        w0 = time.perf_counter()
        code = dac.set_volts(volts, channels)
        dt = time.perf_counter() - w0
        writes += 1
        wsum += dt
        wmax = max(wmax, dt)
        return code

    def wait_until(t_abs):
        # sleep most of the way, spin the last 1 ms: time.sleep alone overshoots by ~0.1-1 ms.
        # The range refresh (~0.3 ms at 100 kHz) only runs with > 3 ms to go, so it never
        # delays an edge.
        while True:
            rest = t_abs - time.perf_counter()
            if rest <= 0:
                return
            if rest > 0.003:
                dac.refresh_range()
                rest = t_abs - time.perf_counter()
            if rest > 0.0015:
                time.sleep(min(rest - 0.001, RANGE_REFRESH_S / 2))

    t0 = None
    try:
        write(0.0)
        t0 = time.perf_counter()
        if a.shape == "square":
            # edges on an absolute schedule (no drift): low for half a period, then high
            half = a.period / 2
            k = 0
            while not (a.cycles and k >= 2 * a.cycles):
                wait_until(t0 + k * half)
                if time.perf_counter() - (t0 + k * half) > half / 4:
                    late += 1
                high = k % 2 == 1
                marker.high() if high else marker.low()        # scope trigger, then the write
                code = write(a.high if high else 0.0)
                if verbose:
                    print(f"cycle {k // 2:4d}  {a.high if high else 0.0:5.3f} V  code {code:4d}",
                          flush=True)
                k += 1
        else:
            # triangle 0 -> high -> 0: one update per I2C write, as fast as the bus allows
            while True:
                t = time.perf_counter() - t0
                if a.cycles and t >= a.cycles * a.period:
                    break
                phase = (t % a.period) / a.period
                marker.high() if phase < 0.5 else marker.low()  # high while ramping up
                write(a.high * (2 * phase if phase < 0.5 else 2 * (1 - phase)))
                dac.refresh_range()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            dac.set_volts(0.0, channels)
            print("outputs set to 0 V")
        finally:
            dac.close()
            marker.close()
        if writes:
            print(f"{writes} updates, I2C write time avg {wsum / writes * 1e3:.2f} ms, "
                  f"max {wmax * 1e3:.2f} ms, {dac.retries} retried I2C writes"
                  + (f", {late} late edges" if late else ""))
            if t0 is not None and a.shape == "triangle":
                elapsed = time.perf_counter() - t0
                print(f"triangle: {writes / elapsed:.0f} updates/s, "
                      f"{writes / elapsed * a.period:.0f} steps per period")


if __name__ == "__main__":
    sys.exit(main())
