#!/usr/bin/env python3
"""Compare two camsync recordings of the screen flash test (flash.html).

usage: flash_analyze.py DIR_A DIR_B        (A = Pi 3, B = Pi Zero)

1. Frame pairing. Both Pis timestamped the same reference edges, each in its own clock. Edges
   are matched by wall-clock time (NTP only has to be right to +-50 ms at 10 Hz), which gives one
   global frame number g = edge * N + frame-in-period on both cameras.
2. Optical offset. Each camera's brightness of the band (cells that change most) is normalised
   per flash. With exposure ~ one frame, a light step turns into a ramp over one frame, so the
   50 % crossing, interpolated between frames, gives the flash time in units of that camera's
   frames. offset = (c_A - c_B) * frame period = how much later camera B exposes than camera A.
   It uses only frame numbers, not timestamps, so it is independent of the edge timestamps.
3. Cross-check: the same offset as camsync measured it from the edges, e_B - e_A.
"""
import sys
import numpy as np


def load(d):
    meta = dict(l.strip().split('=', 1) for l in open(f'{d}/meta.txt') if '=' in l)
    fr = np.atleast_1d(np.genfromtxt(f'{d}/frames.csv', delimiter=',', names=True))
    ed = np.loadtxt(f'{d}/edges.csv', delimiter=',', skiprows=1, dtype=np.int64, ndmin=2)
    gx, gy = int(meta['gx']), int(meta['gy'])
    cells = np.fromfile(f'{d}/cells.u16', dtype='<u2').reshape(-1, gy, gx).astype(float)
    return meta, fr, ed, cells


CELL_MAX = 20 * 10 * 255  # 20 px x 10 sampled rows, all at 255


def band_signal(cells):
    """Sum of the cells that swing most between the flash's off and on states."""
    lo, hi = np.percentile(cells, 3, axis=0), np.percentile(cells, 97, axis=0)
    con = hi - lo
    mask = con >= 0.5 * con.max()
    full = CELL_MAX * 0.9  # a cell this bright is mostly clipped pixels
    return cells[:, mask].sum(axis=1), int(mask.sum()), int((hi[mask] >= full).sum())


def crossings(s, g):
    """50 % crossings of each flash edge: list of (direction, crossing in global frames, first frame past 50 %)."""
    lo, hi = np.percentile(s, 3), np.percentile(s, 97)
    b = s > (lo + hi) / 2
    out = []
    for i in np.nonzero(b[1:] != b[:-1])[0] + 1:
        if i < 10 or i + 10 > len(s): continue
        if b[i - 10:i].std() or b[i:i + 10].std(): continue          # another flash too close
        if np.any(np.diff(g[i - 10:i + 10]) != 1): continue          # dropped frame nearby
        pre, post = np.median(s[i - 10:i - 3]), np.median(s[i + 3:i + 10])
        y = (s - pre) / (post - pre)                                  # 0 -> 1 for rise and fall
        for j in range(i - 3, i + 2):
            if y[j] < 0.5 <= y[j + 1]:
                out.append((1 if b[i] else -1, g[j] + (0.5 - y[j]) / (y[j + 1] - y[j]), int(g[j + 1])))
                break
    return out


def main(da, db):
    ma, fa, ea, ca = load(da)
    mb, fb, eb, cb = load(db)
    N, fps, phz = int(ma['N']), float(ma['fps']), float(ma['pulse_hz'])
    assert (int(mb['N']), float(mb['fps'])) == (N, fps), 'both runs need the same -f and -p'
    T_us, Tp = 1e6 / fps, 1e9 / phz

    # Edge pairing by wall clock: ts_real_ns column 1, k column 2, used column 5.
    ea, eb = ea[ea[:, 5] == 1], eb[eb[:, 5] == 1]
    if not len(ea) or not len(eb): sys.exit('no reference edges in one of the runs: is the pulse wired and running?')
    j = np.clip(np.searchsorted(eb[:, 1], ea[:, 1]), 1, len(eb) - 1)
    j = np.where(np.abs(eb[j - 1, 1] - ea[:, 1]) < np.abs(eb[j, 1] - ea[:, 1]), j - 1, j)
    dreal = eb[j, 1] - ea[:, 1]
    ok = np.abs(dreal) < Tp / 2
    shifts, counts = np.unique(eb[j[ok], 2] - ea[ok, 2], return_counts=True)
    shift = int(shifts[counts.argmax()])
    print(f'{ok.sum()} common edges, edge index shift {shift}, wall clocks differ by {np.median(dreal[ok]) / 1e6:+.2f} ms '
          f'(NTP; only needs to be within +-{Tp / 2e6:.0f} ms)')

    out = {}
    for name, m, fr, ce, sh in (('A', ma, fa, ca, 0), ('B', mb, fb, cb, shift)):
        n = min(len(fr), len(ce))
        fr, ce = fr[:n], ce[:n]
        keep = fr['k'] >= 0
        g = ((fr['k'] - sh) * N + fr['m']).astype(np.int64)[keep]
        s, ncell, nsat = band_signal(ce[keep])
        ev = crossings(s, g)
        e_by_g = dict(zip(g.tolist(), fr['e_us'][keep].tolist()))
        lockd = fr['locked'][keep].mean() * 100
        print(f"{name} {m['host']:>10}: {n} frames, {int(m['drops'])} dropped, {lockd:.0f}% locked, "
              f"{'FREE-RUN' if m['freerun'] == '1' else 'locking'}, band = {ncell} cells, "
              f"contrast {np.percentile(s, 97) / np.percentile(s, 3):.1f}x, {len(ev)} flash edges")
        if nsat:
            print(f"  WARNING: {nsat} of {ncell} band cells are saturated: lower the band brightness (flash.html, down arrow)")
        out[name] = (ev, e_by_g)

    (eva, ega), (evb, egb) = out['A'], out['B']
    rows = []
    for d, c, f in eva:
        cand = [(abs(cb_ - c), cb_, fb_) for db_, cb_, fb_ in evb if db_ == d and abs(cb_ - c) < 3]
        if not cand: continue
        _, cb_, fb_ = min(cand)
        gi = int(np.floor(c))
        ee = [egb[x] - ega[x] for x in range(gi - 2, gi + 3) if x in ega and x in egb]
        rows.append((d, c, f, fb_, (c - cb_) * T_us, np.mean(ee) if ee else np.nan))
    if not rows: sys.exit('no flash seen by both cameras: check aim (snap.pgm) and that flash.html was flashing')

    print(f"\n{'edge':>5} {'global frame':>13} {'A first':>8} {'B first':>8} {'same':>5} {'optical B-A':>12} {'edges B-A':>10}")
    for d, c, fa_, fb_, dt, de in rows:
        print(f"{'rise' if d > 0 else 'fall':>5} {c:13.3f} {fa_:8d} {fb_:8d} {'yes' if fa_ == fb_ else 'NO':>5} "
              f"{dt:+10.1f}us {de:+8.1f}us")
    dt = np.array([r[4] for r in rows]); de = np.array([r[5] for r in rows])
    same = sum(r[2] == r[3] for r in rows)
    print(f"\n{len(rows)} flash edges seen by both: same first frame in {same}/{len(rows)}")
    for d, lab in ((1, 'rise'), (-1, 'fall'), (0, 'all ')):
        sel = np.array([d == 0 or r[0] == d for r in rows])
        if sel.sum():
            print(f"  optical offset B-A ({lab}): mean {dt[sel].mean():+7.1f} us, sd {dt[sel].std():6.1f} us, "
                  f"max |{np.abs(dt[sel]).max():.1f}| us  (n={sel.sum()})")
    if np.isfinite(de).any():
        print(f"  edge-measured   B-A      : mean {np.nanmean(de):+7.1f} us, sd {np.nanstd(de):6.1f} us")


if __name__ == '__main__':
    if len(sys.argv) != 3: sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
