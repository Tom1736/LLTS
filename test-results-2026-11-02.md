# OV9281 setup and calibration, 2026-11-02 (Pi Zero W, 192.168.1.48)

Setup: Pi Zero W Rev 1.1 (ARMv6, 1 core, 426 MB RAM), Raspbian 13, kernel 6.18.50+rpt-rpi-v6, libcamera v0.7.2, rpicam-apps 1.13.0. Hostname `pizero`, user `tom`. Scripts in `~/t` on the Pi.
Calibration computed on the PC with OpenCV 5.0.0.

## 1. Camera bring-up on the Zero
- Not detected at first ("No cameras available"): `camera_auto_detect=1` only covers official camera modules.
- `/boot/firmware/config.txt` now matches the Pi 3B: `camera_auto_detect=0`, `dtparam=i2c_vc_baudrate=400000`, `dtoverlay=ov9281`. Backup: `config.txt.bak-2026-11-02`.
- After a reboot: `ov9281 [1280x800 10-bit MONO] (/base/soc/i2c0mux/i2c@1/ov9281@60)`, same modes as on the 3B.
- **Unplugging the CSI cable while powered kills the stream.** unicam logs `stream on failed in subdev`, rpicam logs `Device timeout`. Restarting rpicam doesn't help; only a reboot does. Never plug or unplug the cable while powered.
- The camera is mounted upside down (image rotated 180°). **All values below are in sensor orientation.**

## 2. Image quality (tablet checkerboard, 1280x800, MJPEG, auto exposure)
| Lighting | Clipped on board | Black / white | Edge width 10-90 % (h / v) | Temporal noise |
|---|---|---|---|---|
| Lamp on, reflection on tablet | 2.7 % | 14 / 209 | 2.75 / 2.29 px | 1.25 DN |
| Lamp off (tablet only light) | 61.9 % | 56 / 254 | 4.41 / 2.98 px | 3.86 DN |
| **Lamp on, no reflection (final)** | **0.0 %** | **12 / 176** | **2.33 / 2.31 px** | **0.94 DN** |

- Edges are equally sharp in both directions, so the lens is not tilted and focus is fine at the working distance.
- With the lamp off, auto exposure is set by the dark room: the tablet clips and bleeds into the black squares (black rises to 56). This is not a focus problem.
- The sharpness score on the live page (mean squared Laplacian) scales with contrast². It is only comparable while scene and lighting stay the same.
- Fixed focus. Hyperfocal distance for f = 2.85 mm, f/2 and a 3 µm blur circle is ≈ 1.36 m, so everything from ≈ 0.7 m to ∞ is sharp to about 1 px. Boards held close enough to fill about half the image were too blurred to detect.

## 3. Intrinsic calibration
Method: a 10x7-square board (9x6 inner corners) on the tablet (`/board` page). Views were captured automatically: a frame is kept only if the board is still (< 1 px corner motion between frames) and the pose is new. Then `findChessboardCornersSB` + `cornerSubPix`, and `calibrateCameraExtended` with 5 parameters (k1 k2 p1 p2 k3). 60 views; none rejected (outlier rule: per-view error > 2.5 × median). Board tilt 3-56° (median 18°).

| | Value | ± (model std) | ± (bootstrap, 40×) | Datasheet |
|---|---|---|---|---|
| RMS reprojection error | **0.148 px** (per view 0.086-0.306) | | | |
| fx | **951.831 px** | 1.404 | 3.12 | 950 |
| fy | **951.130 px** | 1.417 | | 950 |
| fx / fy | **1.00074** → square pixels | | | 1 |
| f (3 µm pixels) | **2.855 mm** | | | 2.85 mm |
| cx | **626.891 px** (−12.6 from centre) | 0.773 | 1.50 | |
| cy | **428.263 px** (+28.8 from centre) | 0.723 | 1.47 | |

The model std from OpenCV is about half the bootstrap spread. Use the bootstrap values as the real uncertainty. The bootstrap estimate itself varies by about 20 % between runs: a rerun with `tools/stability.py` gave fx ±3.80, cx ±1.98, cy ±1.84, corners ±1.4-1.6 px. So read it as fx ≈ ±3-4 px and corners ≈ ±1.5 px.

```
K = [[951.831,   0.000, 626.891],
     [  0.000, 951.130, 428.263],
     [  0.000,   0.000,   1.000]]
dist (k1, k2, p1, p2, k3) = [0.176675, -0.434961, 0.002631, -0.000089, 0.339641]
image size 1280x800, sensor orientation
```

### Field of view (including distortion)
| | Measured | Pinhole with fx only |
|---|---|---|
| Horizontal | **66.650°** | 67.833° |
| Vertical | **44.834°** | |
| Diagonal | **75.555°** | 76.834° |

- **The datasheet's 79.3° is not confirmed.** The diagonal FOV is 75.6°. Near the edge, distortion makes the FOV slightly smaller than the pinhole model, not larger. So the earlier guess (barrel distortion explains 79°) was wrong.
- Footprint of one pixel on a plane perpendicular to the axis (after undistortion): Z / 951.5, for example 1.051 mm at 1 m.

### Distortion
- Shift between distorted and undistorted position: **18.4 px** in the corners, **7.6 px** on average. More than 1 px on 90.1 % of the pixels.
- Undistortion is required for any measurement outside the image centre.

### Stability
Bootstrap (40 resamples of the views, recalibrated each time), 5-parameter model:

| Views | fx | cx / cy | Corner shift (4 corners) | Edge shift (l, r, t, b) |
|---|---|---|---|---|
| 50 | ±3.70 px | ±1.72 / ±1.55 px | ±1.61 / 1.79 / 1.57 / 1.60 px | ±0.87 / 0.82 / 0.27 / 0.30 px |
| **60 (final)** | **±3.12 px** | **±1.50 / ±1.47 px** | **±1.23 / 1.15 / 1.41 / 1.32 px** | **±0.82 / 0.69 / 0.23 / 0.24 px** |

- The 5-parameter model fits better than k1, k2 only: RMS 0.148 vs 0.172. The k1, k2 model also varies more between subsets, so the 5-parameter model is used.
- With the first 28 views the corners were extrapolated: points reached only 81 % of the corner radius, and corner shift varied by 3-24 px between subsets. With 50+ views the points reach 91 % of the corner radius.
- Views 51-60 were taken from further away (board scale 0.09-0.13 vs median 0.15), so they improved the result only a little.
- **Weakest region: the bottom corners.** Only 1 point lies within 60 px of the bottom edge. Views with the board touching the bottom-left and bottom-right edge would still help most.
- 1 px ≈ 0.06°, so the remaining corner uncertainty is < 0.1°.
- **The calibration is only valid while the lens is not turned.** It also applies to the 1280x800 mode only; 640x400 is binned and needs K scaled by 0.5.

## 4. Data and tools
- `calib/zero-2026-11-02/`: the 60 calibration views. Each view has an `img_NNN.jpg` (1280x800, sensor orientation) and an `img_NNN.json` with corners, pose features and white level. The result is in `calibration.json` (K, dist, RMS, std).
- `tools/live.py` (runs on the Pi, also at `~/t/live.py` on the Zero): live view on port 8000.
  - `/` shows the image with crosshair, sharpness, brightness and clipping.
  - `/board` shows the calibration pattern for the tablet.
  - `/status` is the capture feedback.
  - Start with `python3 live.py 1280 800 10`. Uses ~100 % CPU on the Zero at 1280x800, so it is only for setup.
- `tools/calib_capture.py <pi-ip> <outdir> [target]`: auto capture from the live view. It posts its status to the page and resumes if `outdir` already has views.
- `tools/calib_solve.py <dir>`: calibration with outlier rejection, FOV and distortion. Writes `calibration.json`.
- `tools/stability.py <dir> [resamples]`: bootstrap stability and point coverage.
- `tools/calibrate_pi.sh <pi-ip> <name>`: whole procedure in one command. Step-by-step guide in [tools/README.md](tools/README.md).
- `tools/quality.py <jpgs…>`: edge width, contrast, noise, clipping. The board ROI is set by the env variable `ROI=y0,y1,x0,x1`.
- PC requirements: Python with `opencv-python`, `numpy` and `pillow`.

## Not done
- **8 (Zero W) performance**: fps/drop sweep like on the Pi 3B. Not yet run.
- Intrinsic calibration of the Pi 3B camera.
- Stereo calibration: needs both cameras rigidly mounted and the board's square size measured (intrinsics don't need it).
- Exposure for tracking: indoor light needs ~10 ms or more. Moving objects need ≤ 1 ms, which means roughly 10× more light.
