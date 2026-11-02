# Sensor crop (ROI) for higher fps: evaluation, 2026-11-02

Tested on the Pi 3B (192.168.1.94) with the OV9281 in 1280x800 R8, HTS 1530 px (line = 7.967 µs).
Tools are in `tools/crop/`. On the Pi they live in `~/t`; build `roi_test` there with `gcc -O2 -o roi_test roi_test.c -lm`.

## Summary
- **Cropping works today without a new driver.** Stream the stock 1280x800 mode, then overwrite the sensor's window registers over I2C from userspace (`/dev/i2c-10`, addr 0x60, `I2C_SLAVE_FORCE`).
  - The sensor switches within one frame. Unicam accepts the shorter frames without errors.
  - Each cropped line lands at the start of its 1280-byte stride in the buffer.
- **Only the number of rows sets the frame rate**: frame = (H + vblank + 1) · 7.967 µs.
  - A horizontal crop gives no speed-up: HTS below 765 (1530 px) hangs the stream or slows it down. It only cuts the data the CPU has to copy.
- **Hard floor on the Pi 3: vblank ≥ ~32 lines (≈ 255 µs).** Below that, unicam misses every other frame (or hangs, as seen in the 640 mode). This limits the receiver, not the sensor.
- **A moving ROI works.** Write Y_START/Y_END after dequeuing frame k; the new window appears at **frame k+2**, deterministically (94/94 at 313 fps).
  - At > 1 kHz the 100 kHz I2C write (0.85-1.0 ms) is longer than a frame, so it becomes k+2 or k+3 (≈ 50/50).
- **Recommendation:** use the userspace I2C approach now (smallest solution). Consider a driver patch only if the hack causes trouble. Raise the camera I2C bus to 400 kHz next.

## Measured frame rates (raw V4L2, 1280 wide, 0-3 seq gaps per 1500-4000 frames)
| Rows H | VTS | Frame | fps |
|---|---|---|---|
| 800 (stock, hblank 250) | 910 | 7.259 ms | 137.8 |
| 200 | 330 | 2.637 ms | 379 |
| 200 | 232 | 1.856 ms | 539 |
| 100 | 134 | 1.075 ms | 930 |
| 64 | 98 | 0.788 ms | 1269 |
| 32 | 66 | 0.533 ms | 1876 |
| 16 | 50 | 0.406 ms | 2465 |

Below VTS = H + 32 the rate halves (unicam drops alternate frames). Max exposure = VTS − 25 lines, e.g. 0.58 ms at 1269 fps.

## Sizing the ROI
- Full resolution at 1 m: 3 µm pixel / 2.85 mm focal length → **1.05 mm per pixel**. A ping pong ball (40 mm) is ~38 px across, a fly ~5 px.
- The ROI must hold the target plus its motion over the ROI update latency (2-3 frames) plus the prediction error.
  - Example: a ball at 5 m/s moves ~5 px/ms.
  - **H = 128 → 163 lines → 1.30 ms → ~770 fps** leaves ±45 px of margin.
  - H = 96 → ~960 fps.
- The width can be chosen freely (e.g. 320) to save CPU. It does not change the frame rate.
- **Untested option:** crop inside the 640x400 skipping mode (y_inc 2). Each output row covers 2 sensor rows, so you get twice the vertical field for the same frame time, at 2.1 mm/px.

## Latency chain (camera node, measured pieces)
| Step | 320x128 ROI @ ~770 fps | 640x400 @ 288 fps (today) |
|---|---|---|
| Readout of the window (H · 7.967 µs) | 1.02 ms | 3.19 ms |
| End of frame → userspace (DQBUF) | 0.26 ms | 0.26 ms |
| Copy ROI out of the DMA buffer (uncached, ~160 MB/s) | 0.25 ms | (ROI only) |
| Threshold + centroid on the copy (naive C, ~270 MB/s) | ~0.15 ms | ~0.15 ms |
| UART packet, 16 B @ 1 Mbaud | 0.16 ms | 0.16 ms |
| **End of exposure → packet sent** | **~1.85 ms** | **~3.8 ms** |

Notes:
- **V4L2 timestamps are taken at frame start, not frame end.** Dequeue comes at ts + H · line + 0.26 ms. This matters for the phase lock and for the predictor's time base.
- **The DMA buffers are uncached**, so never process pixels in place. Copy just the ROI rows first: 1280x64 in place took > 1 frame; a 320x64 copy takes 0.13 ms.
- With 4 buffers and a SCHED_FIFO loop, userspace keeps up at 1250-1870 fps. Gaps rose to ~3% while the 1 ms I2C write blocked the same thread.
  - Likely cause: I2C interrupt load delaying unicam's IRQ inside the 255 µs blanking.
  - Fix: faster I2C, the write in its own thread, IRQ affinity.

## Options to implement it
1. **Userspace I2C writes (tested, works). Recommended now.**
   - After STREAMON, write the X/Y window (0x3800-0x380B), VTS (0x380E) and optionally HTS. Per frame, write Y_START+X_END+Y_END in one 8-byte burst (0x3802..0x3807).
   - No kernel work. The ROI is fully dynamic.
   - Caveats:
     - It bypasses the driver. V4L2 still reports 1280x800, and `bytesused` is always the full buffer.
     - The driver clamps the `vertical_blanking` control at ≥ 110 and the exposure maximum at 885. The phase lock must therefore write VTS directly (same cost: one I2C write) and clamp exposure to VTS − 25 itself.
     - Every STREAMON rewrites the mode registers, so the window has to be re-applied after each start.
     - Not yet used: the sensor's group hold (0x3208) to make start/end updates atomic. No torn windows were seen with the single burst.
2. **Patched `ov9282` driver (out-of-tree module).** Kernel headers are installed, and the matching source is in `~/drv/ov9282.c` on the Pi.
   - Add `set_selection(CROP)` plus arbitrary output height with a correct `vblank_min`, and a private control for the Y offset that writes under group hold.
   - Gains: correct buffer size and format for libcamera/V4L2, proper locking, no `I2C_SLAVE_FORCE`.
   - Cost: about a day of work plus a rebuild for each kernel update.
   - Per-frame cost is the same: the control path measured 0.6 ms, also I2C-bound.
3. **FPGA (later).** Receive MIPI directly and compute the centroid line by line while the window streams in.
   - Removes the 255 µs vblank floor, the dequeue delay and the uncached copy. Latency ≈ readout + a few µs.
   - The FPGA can also drive the sensor's I2C for ROI moves.

## Next steps
1. Raise the camera I2C bus from 100 kHz to 400 kHz (boot config change + reboot, untested).
   - Expected: 8-byte write 0.85 ms → ~0.23 ms, so the ROI move becomes a deterministic k+2 at ~1 kHz, with fewer drops.
   - Check that the OV9281 is stable at that speed.
2. Fix the Pi's power supply: `get_throttled` reported 0x50000 (undervoltage and throttling have occurred since boot).
3. Fold the ROI writes and the copy+centroid into one camera-node loop (`roi_test.c` is the starting point) and re-run the vblank phase lock with direct VTS writes.
4. Optional: try the skipping-mode crop and group hold.
