# Sensor crop (ROI) for higher fps: evaluation, 2026-11-02

Tested on the Pi 3B (192.168.1.94) with the OV9281 in 1280x800 R8, HTS 1530 px (line = 7.967 µs).
Tools are in `tools/crop/`. On the Pi they live in `~/t`; build `roi_test` there with `gcc -O2 -o roi_test roi_test.c -lm`.

## Summary
- **Cropping works today without a new driver.** Stream the stock 1280x800 mode, then overwrite the sensor's window registers over I2C from userspace (`/dev/i2c-10`, addr 0x60, `I2C_SLAVE_FORCE`).
  - `tools/crop/roi.py x0 x1 y0 y1` sets a window in output-pixel coordinates; ranges are half-open.
  - The sensor switches within one frame. Unicam accepts the shorter frames, and each cropped line lands at the start of its 1280-byte stride.
- **The driver's mode streams with mirror and flip on** (0x3821 bit 2, 0x3820 bit 2). The window registers are in sensor-array coordinates, so `roi.py` maps x → 1280 − x and y → 800 − y.
- **Placement is pixel-exact if three rules hold.** `roi.py` enforces them by widening the window, and returns the window it actually set:
  1. **x edges on multiples of 8.** The sensor aligns the X window to 8 px: with mirror on, the output's left edge follows X_END + 1 rounded down to 8. Otherwise the window shifts right by up to 7 px. Odd widths hang the stream.
  2. **y edges even.** An odd Y start in array coordinates shifts the output by 1 px in x. Y itself is exact at any row.
  3. **Width ≥ 120 px.** At 112 px and below the sensor returns a mostly flat grey frame (~166).
  - Verified with `verify_roi.py` against a static target: averaged full frames vs. cropped frames, ±10 px offset search. **7/7 windows matched at dx = 0, dy = 0**, among them x 200-400 / y 400-500, snapped odd requests (x 333-517 / y 301-413 → 328-520 / 300-414) and a narrow one widened to 120 px.
- **Frame time is exactly linear in rows**: frame = (VTS + 0.95) · 7.967 µs with VTS = rows + vblank. This was measured for 16…800 rows, to within 0.1 line.
  - fps = 1 / frame time, so fps itself is not linear in rows.
  - A horizontal crop gives no speed-up: HTS below 765 (1530 px) hangs the stream or slows it down. It only cuts the data the CPU has to copy.
- **The blanking floor is about 56 lines, not the driver's 110 and not 34.**
  - Below ~32 lines, unicam drops every other frame.
  - Between ~32 and ~52-56 lines, frames still arrive on time, but **the pixel values are wrong**: too dark, and they fall as exposure rises.
  - ≥ 52 was enough for 16 and 64 rows; 200 rows needed 56. Use **vblank ≥ 56** and **exposure ≤ VTS − 30**; exposure stays linear up to there.
  - ⚠ An earlier version of this doc listed fps at vblank 34 (e.g. 2465 fps at 16 rows). The timing was real, but those images were invalid.
- **A moving ROI works and, at 400 kHz I2C, is deterministic.** Write Y_START/Y_END after dequeuing frame k, and the new window shows at **frame k+2** at > 1 kHz (197/197 jumps, at 1269, 1876 and 2465 fps).
  - At 313 fps it already shows at k+1, because the write finishes before the next frame starts.
- **Recommendation:** use the userspace I2C approach now (smallest solution) with the camera I2C at 400 kHz. Consider a driver patch only if the hack causes trouble.

## Frame rates with valid images (vblank 56, frame = (rows + 57) · 7.967 µs)
| Rows | Frame | fps | How | Drops |
|---|---|---|---|---|
| 800 (stock driver, vblank 110) | 7.259 ms | 137.8 | measured | 0 |
| 800 (vblank 56) | 6.829 ms | 146.4 | measured timing; image not checked | 0 |
| 400 | 3.641 ms | 275 | formula | |
| 200 | 2.047 ms | 488.5 | measured, image checked | 0 / 4000 |
| 128 | 1.473 ms | 678.7 | measured, image checked | 0 / 4000 |
| 100 | 1.251 ms | 799 | formula | |
| 64 (vblank 52) | 0.932 ms | 1073.5 | measured, image checked | 0 / 4000 |
| 64 | 0.963 ms | 1037.9 | measured, image checked | 0 / 4000 |
| 32 | 0.709 ms | 1410 | formula | |
| 16 (vblank 52) | 0.556 ms | 1799.4 | measured, image checked | 147 / 4000 |
| 16 | 0.582 ms | 1719.1 | measured, image checked | 15 / 4000 |

"Image checked" means the crop's brightness matched the same window at VTS 600 (long frame) within ~1%. Formula rows use frame = (VTS + 0.95) · 7.967 µs, which matched every measurement from 16 to 800 rows within 0.1 line. The 16-row runs dropped some frames; 64 rows and up dropped none.

## I2C at 400 kHz (`dtparam=i2c_vc_baudrate=400000` in `/boot/firmware/config.txt`)
The backup of the old config is at `/boot/firmware/config.txt.bak-2026-11-02`.

| | 100 kHz (default) | 400 kHz |
|---|---|---|
| 8-byte window write (userspace) | 0.85-1.03 ms | 0.22-0.32 ms |
| `vertical_blanking` control ioctl | ~600 µs | 153 µs (max 196) |
| ROI move at 1269 fps | k+2 or k+3 (≈ 50/50) | k+2 (197/197) |
| Seq gaps while moving the ROI every 40 frames (8000 frames) | 235-297 | 0 |

The drops at 100 kHz were caused by the long I2C transfers. At 400 kHz they're gone.

## Sizing the ROI
- Full resolution at 1 m: 3 µm pixel / 2.85 mm focal length → **1.05 mm per pixel**. A ping pong ball (40 mm) is ~38 px across, a fly ~5 px.
- The ROI must hold the target plus its motion over 2 frames of ROI latency plus the prediction error.
  - Example: a ball at 5 m/s moves ~5 px/ms.
  - **128 rows → 678 fps** gives a 1.5 ms frame, so ~15 px of motion in 2 frames; that leaves ±30-40 px of margin around the ball.
- The width (≥ 120 px, multiple of 8) can be chosen to save CPU. It does not change the frame rate.
- To move the ROI per frame, keep the same rules: shift x in steps of 8 and y in steps of 2. Steps of 8 px are ~8 mm at 1 m, fine for keeping a ball inside the window.
- **Untested option:** crop inside the 640x400 skipping mode (y_inc 2). Each output row covers 2 sensor rows, so you get twice the vertical field for the same frame time, at 2.1 mm/px.

## Latency chain (camera node, measured pieces)
| Step | 320x128 ROI @ 678 fps | 640x400 @ 288 fps (today) |
|---|---|---|
| Readout of the window (rows · 7.967 µs) | 1.02 ms | 3.19 ms |
| End of frame → userspace (DQBUF) | 0.26 ms | 0.26 ms |
| Copy ROI out of the DMA buffer (uncached, ~160 MB/s) | 0.25 ms | (ROI only) |
| Threshold + centroid on the copy (naive C, ~270 MB/s) | ~0.15 ms | ~0.15 ms |
| UART packet, 16 B @ 1 Mbaud | 0.16 ms | 0.16 ms |
| **End of exposure → packet sent** | **~1.85 ms** | **~3.8 ms** |

Notes:
- **V4L2 timestamps are taken at frame start, not frame end.** Dequeue comes at ts + rows · line + 0.26 ms. This matters for the phase lock and for the predictor's time base.
- **The DMA buffers are uncached**, so never process pixels in place. Copy just the ROI rows first: 1280x64 in place took > 1 frame; a 320x64 copy takes 0.13 ms.
- With 4 buffers and a SCHED_FIFO loop, userspace keeps up at up to 2465 fps without drops at 400 kHz.
- **The driver powers the sensor off while it isn't streaming.** Register access only works after STREAMON (EIO/ENXIO otherwise), and every STREAMON rewrites the mode registers, so the window has to be re-applied after each start.

## Options to implement it
1. **Userspace I2C writes (tested, works). Recommended now.**
   - After STREAMON, write the X/Y window (0x3800-0x380B) and VTS (0x380E) with `roi.py`. Per frame, move the ROI with one 8-byte burst (0x3802..0x3807).
   - No kernel work. The ROI is fully dynamic.
   - Caveats:
     - It bypasses the driver. V4L2 still reports 1280x800, and `bytesused` is always the full buffer.
     - The driver clamps the `vertical_blanking` control at ≥ 110 and the exposure maximum at 885. The phase lock must therefore write VTS directly (same cost: one I2C write) and clamp exposure to VTS − 30 itself.
     - Not yet used: the sensor's group hold (0x3208) to make start/end updates atomic. No torn windows were seen with the single burst.
2. **Patched `ov9282` driver (out-of-tree module).** Kernel headers are installed, and the matching source is in `~/drv/ov9282.c` on the Pi.
   - Add `set_selection(CROP)` plus arbitrary output height with `vblank_min` = 56, and a private control for the Y offset that writes under group hold.
   - Gains: correct buffer size and format for libcamera/V4L2, proper locking, no `I2C_SLAVE_FORCE`.
   - Cost: about a day of work plus a rebuild for each kernel update.
   - Per-frame cost is the same, since I2C is the bottleneck either way.
3. **FPGA (later).** Receive MIPI directly and compute the centroid line by line while the window streams in.
   - Removes the receiver's 32-line floor (the sensor's ~56-line floor still applies), the dequeue delay and the uncached copy. Latency ≈ readout + a few µs.
   - The FPGA can also drive the sensor's I2C for ROI moves.

## Next steps
1. Fix the Pi's power supply: undervoltage events are still being logged.
2. Fold the ROI writes and the copy+centroid into one camera-node loop (`roi_test.c` is the starting point) and re-run the vblank phase lock with direct VTS writes.
3. Optional: try the skipping-mode crop and group hold.
