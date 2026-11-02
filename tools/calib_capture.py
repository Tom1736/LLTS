"""Grab calibration views from the live server automatically.

Saves a frame only when the 9x6 board is found, has not moved since the previous
frame (no motion blur from hand-holding), and differs enough from every saved
view (position, size, tilt, rotation). Status is posted back to the Pi's page.
Usage: python calib_capture.py <pi-ip> <outdir> [target]
"""
import json, math, os, sys, time, urllib.request
import cv2
import numpy as np

PI, OUT = sys.argv[1], sys.argv[2]
TARGET = int(sys.argv[3]) if len(sys.argv) > 3 else 40
PAT = (9, 6)
STILL_PX = 1.0                     # max corner motion between frames
EDGE_X, EDGE_Y = 160, 120          # border band that counts as "at the edge"
CLOSE = 0.25                       # board scale (sqrt of area share) that counts as "close";
                                   # much closer than ~0.7 m is out of the fixed focus
ZONES = [["oben-links", "oben", "oben-rechts"], ["links", "NAH", "rechts"],
         ["unten-links", "unten", "unten-rechts"]]


def cells_of(poly, w, h, scale):
    """3x3 grid: outer cells = a corner point lies in that border band, centre = close view."""
    cells = np.zeros((3, 3), int)
    for x, y in poly:
        gx = 0 if x < EDGE_X else 2 if x > w - EDGE_X else 1
        gy = 0 if y < EDGE_Y else 2 if y > h - EDGE_Y else 1
        if (gx, gy) != (1, 1):
            cells[gy, gx] = 1
    cells[1, 1] = int(scale > CLOSE)
    return cells
os.makedirs(OUT, exist_ok=True)


def fetch():
    with urllib.request.urlopen(f"http://{PI}:8000/frame.jpg", timeout=5) as r:
        return r.read()


def post(**s):
    try:
        req = urllib.request.Request(f"http://{PI}:8000/status", json.dumps(s).encode(),
                                     {"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=2).read()
    except OSError:
        pass


def features(c, w, h):
    g = c.reshape(PAT[1], PAT[0], 2)
    top, bot = np.linalg.norm(g[0, -1] - g[0, 0]), np.linalg.norm(g[-1, -1] - g[-1, 0])
    lef, rig = np.linalg.norm(g[-1, 0] - g[0, 0]), np.linalg.norm(g[-1, -1] - g[0, -1])
    hull = cv2.convexHull(c.reshape(-1, 2))
    v = g[0, -1] - g[0, 0]
    return dict(cx=float(c[..., 0].mean() / w), cy=float(c[..., 1].mean() / h),
                scale=float(math.sqrt(cv2.contourArea(hull) / (w * h))),
                tx=float((rig - lef) / (rig + lef)), ty=float((bot - top) / (bot + top)),
                ang=float(math.atan2(v[1], v[0]) % math.pi))


def distance(a, b):
    da = abs(a["ang"] - b["ang"]); da = min(da, math.pi - da)
    return max(math.hypot(a["cx"] - b["cx"], a["cy"] - b["cy"]) / 0.08,
               abs(math.log(a["scale"] / b["scale"])) / 0.2,
               abs(a["tx"] - b["tx"]) / 0.05, abs(a["ty"] - b["ty"]) / 0.05, da / 0.2)


saved, prev, grid = [], None, np.zeros((3, 3), int)
for f in sorted(os.listdir(OUT)):          # resume
    if f.startswith("img_") and f.endswith(".json"):
        d = json.load(open(os.path.join(OUT, f)))
        saved.append(d["feat"])
        grid += cells_of(np.array(d["corners"]), *d["size"], d["feat"]["scale"])

msg, color, last_save, last_dbg = "Brett ins Bild halten", "#eee", 0, 0
while True:
    try:
        jpg = fetch()
    except OSError as e:
        print("fetch:", e, flush=True); time.sleep(1); continue
    img = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_GRAYSCALE)
    h, w = img.shape
    ok, c = cv2.findChessboardCornersSB(img, PAT, flags=cv2.CALIB_CB_NORMALIZE_IMAGE)
    if not ok:
        prev = None
        msg, color = "Brett nicht erkannt – ganz ins Bild, nicht zu schräg", "#f86"
    else:
        moved = np.abs(c - prev).max() if prev is not None else 99
        prev = c
        f = features(c, w, h)
        poly = c.reshape(-1, 2)
        white = float(np.percentile(img[int(poly[:, 1].min()):int(poly[:, 1].max()),
                                        int(poly[:, 0].min()):int(poly[:, 0].max())], 95))
        if white > 245:
            msg, color = "Zu hell – Tablet dunkler stellen", "#f86"
        elif moved > STILL_PX:
            msg, color = "Erkannt – stillhalten …", "#fd5"
        elif saved and min(distance(f, s) for s in saved) < 0.4:
            msg, color = "Schon ähnlich – neue Stelle oder anders kippen", "#fd5"
        elif time.time() - last_save > 0.8:
            n = len(saved) + 1
            cells = cells_of(poly, w, h, f["scale"])
            with open(os.path.join(OUT, f"img_{n:03d}.jpg"), "wb") as fh:
                fh.write(jpg)
            json.dump({"feat": f, "cells": cells.tolist(), "corners": c.reshape(-1, 2).tolist(),
                       "size": [w, h], "white": white}, open(os.path.join(OUT, f"img_{n:03d}.json"), "w"))
            saved.append(f); grid += cells; last_save = time.time()
            msg, color = f"✓ Bild {n} gespeichert", "#2f6"
            print(f"saved {n}: {json.dumps({k: round(v, 3) for k, v in f.items()})} white={white:.0f}", flush=True)
    tilted = sum(1 for s in saved if max(abs(s["tx"]), abs(s["ty"])) > 0.03)
    need = grid.copy()                           # want 3 per border zone and 3 close views
    if need.min() < 3:
        gy, gx = np.unravel_index(need.argmin(), need.shape)
        hint = (" | etwas NÄHER (aber noch scharf, ~70 cm)" if (gy, gx) == (1, 1)
                else f" | fehlt: {ZONES[gy][gx]} – Brett GANZ an den Rand")
    elif len(saved) < TARGET:
        hint = " | weiter: Rand/Ecken, nah, gekippt"
    else:
        hint = " | FERTIG – genug Bilder"
    post(n=len(saved), msg=msg + hint, color=color, grid=grid.tolist(), tilted=tilted)
    if time.time() - last_dbg > 2:     # debug: what the script currently sees
        last_dbg = time.time()
        with open(os.path.join(OUT, "..", "capture_last.jpg"), "wb") as fh:
            fh.write(jpg)
        print(time.strftime("%H:%M:%S"), msg, flush=True)
