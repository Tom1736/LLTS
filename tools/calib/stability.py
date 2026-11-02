"""Bootstrap stability and point coverage for a calibration directory.

Usage: python stability.py <dir> [resamples]
Resamples the views with replacement, recalibrates each time and prints the
spread of fx, cx, cy and of the distortion shift at the image corners/edges.
Run calib_solve.py first so the coverage uses the calibrated principal point.
"""
import glob, json, os, sys
import cv2
import numpy as np

D = sys.argv[1]
N_BOOT = int(sys.argv[2]) if len(sys.argv) > 2 else 40
PAT = (9, 6)
obj = np.zeros((PAT[0] * PAT[1], 3), np.float32)
obj[:, :2] = np.mgrid[0:PAT[0], 0:PAT[1]].T.reshape(-1, 2)

fs = sorted(glob.glob(os.path.join(D, "img_*.json")))
C = []
for f in fs:
    d = json.load(open(f))
    img = cv2.imread(f[:-5] + ".jpg", cv2.IMREAD_GRAYSCALE)
    c = np.array(d["corners"], np.float32).reshape(-1, 1, 2)
    C.append(cv2.cornerSubPix(img, c, (5, 5), (-1, -1),
                              (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 50, 0.01)))
w, h = json.load(open(fs[0]))["size"]
cal_file = os.path.join(D, "calibration.json")
if os.path.exists(cal_file):
    K0 = json.load(open(cal_file))["K"]
    cx, cy = K0[0][2], K0[1][2]
else:
    cx, cy = w / 2 - 0.5, h / 2 - 0.5

# coverage: how far out do the measured points reach?
p = np.concatenate(C).reshape(-1, 2)
r = np.hypot(p[:, 0] - cx, p[:, 1] - cy)
rc = max(np.hypot(x - cx, y - cy) for x in (0, w) for y in (0, h))
print(f"{len(C)} Bilder, Messpunkte bis {r.max():.0f} von {rc:.0f} px Eckradius ({100 * r.max() / rc:.0f} %)")
print(f"Punkte nahe am Rand (< 60 px): links {np.sum(p[:, 0] < 60)}, rechts {np.sum(p[:, 0] > w - 60)}, "
      f"oben {np.sum(p[:, 1] < 60)}, unten {np.sum(p[:, 1] > h - 60)}")

P = np.array([[0, 0], [w - 1, 0], [0, h - 1], [w - 1, h - 1],
              [0, cy], [w - 1, cy], [cx, 0], [cx, h - 1]], np.float64).reshape(-1, 1, 2)


def run(idx):
    _, K, d, _, _ = cv2.calibrateCamera([obj] * len(idx), [C[i] for i in idx], (w, h), None, None)
    u = cv2.undistortPoints(P, K, d, P=K).reshape(-1, 2)
    return K[0, 0], K[0, 2], K[1, 2], np.linalg.norm(u - P.reshape(-1, 2), axis=1)


rng = np.random.default_rng(1)
out = [run(rng.choice(len(C), len(C), replace=True)) for _ in range(N_BOOT)]
fx, ccx, ccy = (np.array([o[i] for o in out]) for i in range(3))
V = np.array([o[3] for o in out])
print(f"Bootstrap {N_BOOT}x: fx ±{fx.std():.2f} px, cx ±{ccx.std():.2f}, cy ±{ccy.std():.2f}")
print(f"  Verzeichnung Ecken (ol, or, ul, ur): {V[:, :4].mean(0).round(1)} ± {V[:, :4].std(0).round(2)} px")
print(f"  Verzeichnung Ränder (l, r, o, u):    {V[:, 4:].mean(0).round(1)} ± {V[:, 4:].std(0).round(2)} px")
