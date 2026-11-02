# OV9281 test results, 2026-10-29 (Pi 3B, 192.168.1.94)

Setup: Pi 3 Model B Rev 1.2, Debian 13, kernel 6.18.50, libcamera v0.7.2, rpicam-apps 1.14.0, unicam (no ISP in raw tests). Scripts and data in `~/t` on the Pi.

## 1. Mode sweep (rpicam-vid, 3 s)
| Mode | Req fps | Interval | fps | Drops |
|---|---|---|---|---|
| R8 | 30 | 34.727 ms | 28.80 | 0 |
| R8 | 240 | 4.342 ms | 230.30 | 0 |
| R10 | 30 | 33.334 ms | 30.00 | 0 |
| R10 | 240 | 4.168 ms | 239.91 | 26 |

Hypothesis confirmed: R8 runs ~4.2% slow at any fps, R10 is exact.

## 2. Controls during streaming
| Mode | fps | vblank | pixel_rate | exposure (lines) |
|---|---|---|---|---|
| R8 | 30 | 3957 | 200 MHz | 130 |
| R8 | 240 | 144 | 200 MHz | 130 |
| R10 | 30 | 3085 | 160 MHz | 104 |
| R10 | 240 | 35 | 160 MHz | 104 |

Fit of frame period = L·(400 + vblank + c):
- R10: L = 9.5625 µs (exactly as the driver claims), c ≈ 1 line.
- R8: L = **7.967 µs** (driver claims 7.65 µs), so the real pixel rate is **192 MHz**, not 200. c ≈ 1 line.
- Frame period = (401 + vblank) · line_time.
- Consequence: in R8, libcamera's exposure is also 4% longer than requested (130 lines = 1036 µs, not 1000).

## 3. Throttling
After 10 s at R8/300 fps: `throttled=0x0`, 47 °C, ARM at 1.2 GHz. rpicam ~35% CPU.
Drops at 288 fps via rpicam: 439 in 10 s, rising from ~20/s to a steady ~57/s (≈20% of frames). Not caused by throttling.

## 4. Raw V4L2 (no ISP), R8 640x400 GREY, 3 mmap buffers, v4l2-ctl
| vblank | fps | seq gaps | jitter (sd) |
|---|---|---|---|
| 300 | 179.04 | 0 / 1000 | 0.9 µs |
| 144 | 230.30 | 0 / 1000 | 0.5 µs |
| 100 | 250.53 | 0 / 1000 | 0.9 µs |
| 60 | 272.27 | 3 / 1000 | 0.7 µs |
| 40 | 284.62 | 4 / 10000 | 5.0 µs |
| 34 | 288.55 | 4 / 10000 | 1.1 µs |
| 31-33 | ~290 | 0-2 / 500 | ~1 µs |
| ≤ 30 | **stream hangs after frame 0** (any exposure) | | |

- The ISP was the drop source. Raw capture loses only a few frames per 10k, in bursts of 2-5 frames. These look like userspace hiccups (v4l2-ctl over SSH, no RT priority), not hardware.
- `seq` advances across dropped frames, so it is usable as the frame ID.
- Timestamps are CLOCK_MONOTONIC. The flag says `ts-src-eof`, but they behave like frame start: dequeue comes at ts + rows · line + 0.26 ms (see crop-evaluation.md).
- The driver's minimum vblank (22) is not usable on Pi 3 unicam: the stream stalls at vblank ≤ 30. **Use vblank ≥ 34 → max ~288 fps.**

## 5. vblank change while streaming (direct ioctl, R8, vblank 144)
- A `VIDIOC_S_CTRL` on the subdev takes **~600 µs** (I2C). Spawning `v4l2-ctl` takes ~8.8 ms.
- The step is exact (+10 lines → +10 × 7.967 µs), with no drops and no corrupted frames.
- The sensor **latches vblank at end of frame**. A write that completes before EOF(n+1) lengthens only the interval EOF(n+1)→EOF(n+2).
- Single-frame pulse rule (verified at all phases 0.1-0.85 of the frame):
  1. After dequeuing frame n, write nominal ± k.
  2. ~1 frame later (before EOF n+2), restore.
  3. Exactly one interval changes, and frame n+2 shows the shift.
- Avoid writes ending right at EOF: one write that straddled EOF split the +5 lines into +2 then +4. The driver probably doesn't use group hold.

## 6. Exposure / gain
- The exposure unit is **lines** (7.967 µs in R8). Peak brightness scales ~linearly: max pixel 14/21/34/57/117/211 at 13/25/50/100/200/400 lines, gain 16.
- Black level ≈ 4 (8-bit).
- The test scene was a dark room at night. At 100-200 µs a usable image needs strong illumination (or high gain: gain 255 at 104 µs gives max 134).
- No corruption at short exposure.

## 7. Crop / ROI
- Mbus codes: Y10, Y8. Frame sizes: only the fixed 1280x800, 1280x720, 640x400.
- `S_SELECTION` returns ENOTTY. Asking for 640x200 snaps back to 640x400.
- **A custom window needs a driver patch.** 640x400 is binned from the full 1280x800 crop.

## Extra: 1280x800 fps (raw V4L2)
- At 1280x800 the driver changes its limits: **vblank min 110** (lower values are clamped), **hblank min 250** (default 250), exposure max 885 lines.
- hblank stays at whatever was set before. After the 640 mode it is still 890, which caps the rate at 97 fps (R8) / 81 fps (R10).
- Line = (1280 + hblank) / pixel clock, with the real R8 clock at 192 MHz. Frame = (~800.4 + vblank) lines.

| Format | hblank | vblank | fps | Drops |
|---|---|---|---|---|
| R8 | 890 | 110 | 97.19 | 0 / 500 |
| R8 | 500 | 110 | 118.45 | 0 / 500 |
| R8 | 350 | 110 | 129.33 | 0 / 500 |
| R8 | **250** | **110** | **137.76** | 1 / 5000 (jitter 1.0 µs) |
| R10 | 890 | 110 | 80.99 | 0 / 500 |
| R10 | 250 | 110 | **114.80** | 0 / 500 |

- R8 max is again 4% below libcamera's 143.7. R10 matches libcamera's 114.9.
- No throttling (43.5 °C, 0x0).
- Image is valid at full resolution. It is unbinned, so it gets ~4x less signal per pixel than 640x400; at 3.2 ms / gain 16 it is nearly black indoors at night.

## Not done
- **8 (Zero W):** needs the Zero W's IP and key access.
- **9-10 (PWM and phase lock):** no PWM chip yet (needs `dtoverlay=pwm,pin=18,func=2` + reboot) and a jumper GPIO18 (pin 12) → GPIO17 (pin 11) to timestamp edges. libgpiod v2.2.1 and python gpiod 2.2.0 are installed.
- **11:** galvo and DAC hardware not purchased yet.

## Answers to open questions
- The original measurements match this Pi 3B to the µs (R8 240 → 4.342 ms here; the 250 fps → 4.167 ms in the handoff is the same 4.2% error), so they were very likely taken on the 3B.
- vblank change: it takes effect at the next frame boundary after the write, without a glitch, as long as the write doesn't end right at EOF.
