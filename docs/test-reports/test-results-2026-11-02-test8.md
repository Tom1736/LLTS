# Test 8: Pi Zero W as camera node B, 2026-11-02 (192.168.1.48)

Setup: Pi Zero W Rev 1.1 (ARMv6, 1 core at 1 GHz, no NEON), kernel 6.18.50+rpt-rpi-v6, OV9281 in R8. Same tools as on the Pi 3B, built on the Zero with gcc -O2 (`roi_test.c`) and -O3 (`track.c`).
Script: `tools/bench/test8.sh`. Raw output of parts B and C: `test8-zero-raw.log`. Part A comes from the first run, which hung in part B (see "Hang").

## Summary
- **Capture is as good as on the Pi 3B or better.** The frame rates match the 3B to 0.01 fps, with 0 seq gaps up to 288.55 fps (640x400) and 1721 fps (16-row crop).
- **The ROI moves at frame k+2, same as on the 3B** (122/122 jumps at 488-1721 fps). The 8-byte I2C write takes 0.29-0.32 ms (3B: 0.22-0.32 ms).
- **The CPU is the limit, and only per pixel.** The copy out of the uncached DMA buffer runs at ~180 MB/s, as on the 3B (~160 MB/s). Computing is ~2-5× slower than on the 3B.
- **A narrow ROI keeps up: 320 px wide at 128 rows (678.7 fps) and at 64 rows (1038 fps) ran with 0 drops.** At 640 px wide it is at the limit (3 gaps). At 1280 px wide it falls behind (66 % dropped).
- **Full frame 640x400 with detection only reaches ~150 fps** (5.7 ms per frame). That is fine as the search mode when the target is lost, not for tracking.
- **The Zero W works as camera node B if the ROI stays ≤ 320 px wide.** With the real detection instead of the test's sum pass, the estimated load is ~80 % of the frame at 678 fps (see "Budget"). It still has to be measured in the combined loop.

## A. Raw V4L2, 640x400 R8, 3 mmap buffers, 2000 frames, no RT
| vblank | fps | seq gaps | jitter (sd) | 3B (section 4, 2026-10-29) |
|---|---|---|---|---|
| 300 | 179.04 | 0 / 1989 | 4.0 µs | 179.04, 0 gaps |
| 144 | 230.30 | 0 / 1989 | 3.3 µs | 230.30, 0 gaps |
| 100 | 250.53 | 0 / 1989 | 3.5 µs | 250.53, 0 gaps |
| 60 | 272.27 | 0 / 1989 | 7.8 µs | 272.27, 3 / 1000 |
| 56 | 274.65 | 0 / 1989 | 7.5 µs | |
| 40 | 284.62 | 0 / 1989 | 6.2 µs | 284.62, 4 / 10000 |
| 34 | 288.55 | 0 / 1989 | 4.8 µs | 288.55, 4 / 10000 |

- The timestamp jitter is 4-8 µs instead of ~1 µs on the 3B. The frames still arrive on time; only the interrupt latency on the single core varies more.

## B. 640x400 full frame + copy + threshold map + centroid (`track.c`, SCHED_FIFO), 10 s each
| fps | Frame | Processed | Dropped | Copy | Detect | Total (max) |
|---|---|---|---|---|---|---|
| 150 | 6.67 ms | 1492 | 0 | 1.43 ms | 4.29 ms | 5.72 ms (6.02) |
| 200 | 5.00 ms | 1685 | 299 (15 %) | 1.47 ms | 4.37 ms | 5.84 ms (11.9) |
| 250 | 4.00 ms | 1713 | 770 (31 %) | 1.40 ms | 4.34 ms | 5.75 ms (14.0) |

- Copy: 256 KB in 1.4 ms = **~180 MB/s**.
- Detect: 4.3 ms for 256 000 px = **~17 ns/px (~59 MB/s)**. `detect()` compares each pixel against its own threshold and sums x. It is written for NEON vectorisation, which ARMv6 lacks.
- The loop processes ~170 frames/s no matter how fast the camera runs; the rest is dropped.

## C. Sensor crop over I2C (`roi_test.c`, SCHED_FIFO), 1280x800 mode, vblank 56, 5000 frames
The ROI jumps between y 200 and y 500 (array coordinates) every 40 frames. "Process" is one pass summing all pixels of the copy, not the real detection.

| Rows × width | fps | Seq gaps | Copy | Process | ts → userspace (mean / max) | ROI jump visible at |
|---|---|---|---|---|---|---|
| 200 × 320 | 488.5 | 0 | 0.362 ms | 0.556 ms | 1.887 / 1.977 ms | k+2: 122/122 |
| **128 × 320** | **678.7** | **0** | **0.222 ms** | **0.335 ms** | **1.306 / 1.404 ms** | **k+2: 122/122** |
| 128 × 640 | 678.5 | 3 | 0.459 ms | 0.750 ms | 1.325 / 5.749 ms | k+2: 122/122 |
| 128 × 1280 | 678.4 | 3213 | 0.940 ms | 1.438 ms | 5.079 / 14.371 ms | k+3: 38, k+4: 84 |
| 64 × 320 | 1037.9 | 0 | 0.107 ms | 0.159 ms | 0.792 / 0.918 ms | k+2: 122/122 |
| 16 × 320 | 1721.3 | 0 | 0.025 ms | 0.042 ms | 0.398 / 0.502 ms | k+2: 122/122 |

- The frame rates match the formula frame = (rows + 57) · 7.967 µs, as on the 3B.
- **End of frame → userspace is ~0.28 ms** (ts → userspace minus rows · 7.967 µs: 0.29 / 0.29 / 0.28 / 0.27 ms for 200 / 128 / 64 / 16 rows). On the 3B it is 0.26 ms.
- The sum pass costs ~8 ns/px, half of `detect()` in part B.
- At 1280 px wide the loop needs ~2.4 ms per 1.47 ms frame, so it falls behind. The ROI jump then shows up at k+3/k+4, because the loop is processing old frames.
- 16 rows ran with 0 drops in 5000 frames. The 3B dropped 15 / 4000 in the same setting (crop-evaluation.md).
- Temperature stayed at 35-40 °C, `throttled=0x0` before and after. Only "Fixed dependency cycle" messages at boot in dmesg, no unicam errors.

## Budget at 320 × 128, 678.7 fps (1.47 ms per frame)
| Step | Measured / estimated |
|---|---|
| Copy ROI out of the DMA buffer | 0.22 ms (measured) |
| Threshold map + centroid | ~0.69 ms (estimated: 40 960 px × 17 ns from part B) |
| ROI write over I2C, if moved every frame | 0.29 ms (measured; the test moved it only every 40th frame) |
| **Total** | **~1.2 ms = ~80 % of the frame** |

- It fits, but with little headroom for interrupts and the UART send.
- **Latency of node B:** end of exposure → packet ≈ 1.02 ms readout + 0.28 ms dequeue + 0.22 ms copy + ~0.69 ms detect + 0.16 ms UART ≈ **2.4 ms**. Node A on the 3B: ~1.85 ms. `PAIR` waits for the slower node, so the predictor's lead grows by ~0.5 ms. The I2C write comes after the packet and is not on this path.
- Ways to gain headroom (not tested):
  - A global threshold instead of the per-pixel map, or a threshold map only in the ROI.
  - Detect on every 2nd row and column. A 40 mm ball is ~38 px wide, so the centroid stays sub-pixel at ¼ of the work.
  - Write the ROI only when the target gets near the window's edge, not every frame.
  - Fuse copy and detect into one pass over the uncached buffer.

## Hang in the first run
- In the first run, `track.c` at 200 fps needed 5.8 ms per 5 ms frame. Under SCHED_FIFO, the loop then never sleeps.
- The plain `timeout` that should stop it after 10 s did not get the CPU. SSH stopped responding, and the Zero was restarted (uptime 18 min afterwards). The log on the SD card lost the last seconds before the restart.
- `sched_rt_runtime_us` is 950000, so RT throttling is enabled. It still did not keep the system usable.
- `test8.sh` now runs the timeouts at a higher FIFO priority (90) than the loops (50 / 80). The second run went through without problems.
- **Consequence for the camera node:** the loop must never fall behind for long. It needs a watchdog with higher priority, or it must drop old frames and always process only the newest one.

## Not done
- Real detection (threshold + centroid) inside the ROI loop with a per-frame ROI write and UART send: the combined camera-node loop from crop-evaluation.md, next step 2.
- 640x400 skipping-mode crop on the Zero.
