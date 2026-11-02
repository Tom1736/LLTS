"""Intrinsic calibration from the views saved by calib_capture.py.

Usage: python calib_solve.py <dir> [nominal_fx]
Rejects views whose RMS error is > 2.5x the median, recalibrates, prints
K, distortion, uncertainties and the field of view including distortion.
"""
import glob, json, math, os, sys
import cv2
import numpy as np

D = sys.argv[1]
FX_NOM = float(sys.argv[2]) if len(sys.argv) > 2 else 950.0
PAT = (9, 6)
obj = np.zeros((PAT[0] * PAT[1], 3), np.float32)
obj[:, :2] = np.mgrid[0:PAT[0], 0:PAT[1]].T.reshape(-1, 2)   # unit squares

views = []
for f in sorted(glob.glob(os.path.join(D, "img_*.json"))):
    d = json.load(open(f))
    img = cv2.imread(f[:-5] + ".jpg", cv2.IMREAD_GRAYSCALE)
    c = np.array(d["corners"], np.float32).reshape(-1, 1, 2)
    c = cv2.cornerSubPix(img, c, (5, 5), (-1, -1),
                         (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 50, 0.01))
    views.append((os.path.basename(f)[:-5], c, d["feat"]))
w, h = json.load(open(glob.glob(os.path.join(D, "img_*.json"))[0]))["size"]


def calib(vs):
    rms, K, dist, rv, tv, sdi, sde, per = cv2.calibrateCameraExtended(
        [obj] * len(vs), [v[1] for v in vs], (w, h), None, None)
    return rms, K, dist, rv, tv, sdi.ravel(), per.ravel()


rms, K, dist, rv, tv, sd, per = calib(views)
print(f"Alle {len(views)} Bilder: RMS {rms:.3f} px")
keep = [v for v, e in zip(views, per) if e <= 2.5 * np.median(per)]
drop = [v[0] for v, e in zip(views, per) if e > 2.5 * np.median(per)]
if drop:
    print("Verworfen:", ", ".join(f"{n} ({e:.2f} px)" for n, e in zip(drop, per[[v[0] in drop for v in views]])))
    rms, K, dist, rv, tv, sd, per = calib(keep)
views = keep
fx, fy, cx, cy = K[0, 0], K[1, 1], K[0, 2], K[1, 2]
k1, k2, p1, p2, k3 = dist.ravel()[:5]
print(f"\nVerwendet: {len(views)} Bilder, RMS-Reprojektionsfehler {rms:.3f} px "
      f"(pro Bild {per.min():.3f}–{per.max():.3f}, Median {np.median(per):.3f})")
print(f"fx = {fx:.3f} ± {sd[0]:.3f} px")
print(f"fy = {fy:.3f} ± {sd[1]:.3f} px   (fx/fy = {fx / fy:.5f})")
print(f"cx = {cx:.3f} ± {sd[2]:.3f} px   (Bildmitte {w / 2 - 0.5:.1f}, Abweichung {cx - (w / 2 - 0.5):+.1f})")
print(f"cy = {cy:.3f} ± {sd[3]:.3f} px   (Bildmitte {h / 2 - 0.5:.1f}, Abweichung {cy - (h / 2 - 0.5):+.1f})")
print(f"k1 = {k1:+.5f} ± {sd[4]:.5f}, k2 = {k2:+.5f} ± {sd[5]:.5f}, k3 = {k3:+.5f} ± {sd[8]:.5f}")
print(f"p1 = {p1:+.6f} ± {sd[6]:.6f}, p2 = {p2:+.6f} ± {sd[7]:.6f}")
print(f"Brennweite physikalisch (3 µm Pixel): {fx * 0.003:.3f} mm  (Nennwert 2.850 mm, fx_nom {FX_NOM:.0f})")

# pose spread: tilt of the board plane relative to the image plane
tilts = [math.degrees(math.acos(abs(cv2.Rodrigues(r)[0][2, 2]))) for r in rv]
dists = [float(np.linalg.norm(t)) for t in tv]
print(f"Neigung des Bretts: {min(tilts):.1f}°–{max(tilts):.1f}° (Median {np.median(tilts):.1f}°); "
      f"Abstand {min(dists):.1f}–{max(dists):.1f} Feldbreiten")


def angle(px, py):
    u = cv2.undistortPoints(np.array([[[px, py]]], np.float64), K, dist).ravel()
    return u


def fov(a, b):
    ua, ub = angle(*a), angle(*b)
    va, vb = np.append(ua, 1), np.append(ub, 1)
    return math.degrees(math.acos(va @ vb / np.linalg.norm(va) / np.linalg.norm(vb)))


L, R, T, B = -0.5, w - 0.5, -0.5, h - 0.5
print(f"\nBildwinkel mit Verzeichnung:")
print(f"  horizontal {fov((L, cy), (R, cy)):.3f}°")
print(f"  vertikal   {fov((cx, T), (cx, B)):.3f}°")
print(f"  diagonal   {fov((L, T), (R, B)):.3f}°")
print(f"Ohne Verzeichnung (nur fx): horizontal {2 * math.degrees(math.atan(w / 2 / fx)):.3f}°, "
      f"diagonal {2 * math.degrees(math.atan(math.hypot(w / 2 / fx, h / 2 / fy))):.3f}°")

# displacement caused by distortion
uu, vv = np.meshgrid(np.arange(0, w, 4) + 0.0, np.arange(0, h, 4) + 0.0)
pts = np.stack([uu.ravel(), vv.ravel()], 1).reshape(-1, 1, 2)
und = cv2.undistortPoints(pts, K, dist, P=K).reshape(-1, 2)
disp = np.linalg.norm(und - pts.reshape(-1, 2), axis=1)
print(f"Verschiebung durch Verzeichnung: Ecke {disp.max():.3f} px, Mittel {disp.mean():.3f} px, "
      f">1 px bei {100 * np.mean(disp > 1):.1f} % der Pixel")

json.dump({"image_size": [w, h], "K": K.tolist(), "dist": dist.ravel().tolist(), "rms": rms,
           "views": [v[0] for v in views], "std": sd.tolist()[:9],
           "note": "sensor orientation (image appears upside down on this mount)"},
          open(os.path.join(D, "calibration.json"), "w"), indent=1)
print(f"\nGespeichert: {os.path.join(D, 'calibration.json')}")
