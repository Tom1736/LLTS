# Frame sync between the two cameras, 2026-11-03

Pi 3B (192.168.1.94, camera node A) and Pi Zero W (192.168.1.48, camera node B), both OV9281 at 640x400 R8, 100 fps.
Tools are in `tools/sync/` (how-to in German: [tools/sync/README.md](../../tools/sync/README.md)). On the Pis they live in `~/sync`.

## Summary
- **Both sensors are phase-locked to a 10 Hz hardware PWM pulse from the Pi 3.** One wire carries it to GPIO17 on both Pis. Each Pi timestamps the edges in its own clock and steers its own sensor's vblank, one line at a time.
  - No network, NTP or crystal enters the lock, and the two sensors never talk to each other.
- **Lock quality, measured from the edges:** Pi 3 sd 1.9-2.4 µs, max 8.6 µs; Pi Zero sd 2.5-2.6 µs, max 7.8 µs. 0 dropped frames, ~4 vblank writes per second on each Pi.
  - One sensor line is 8 µs, the smallest step vblank can make, so this is as tight as this method gets.
- **Camera to camera during the flash test:** −0.8 ± 3.3 µs from the edges. The optical check (screen flashes) agrees to within ~±40 µs; its resolution is limited by the laptop LCD, not the cameras.
- **Same first frame on both cameras for 60 of 61 flash edges.** The one miss crossed 50 % brightness 0.4 % of a frame from a frame boundary.
- **Pitfall found: on the Pi Zero, a frame must not start on the edge.** Its single core then serves the GPIO and camera interrupts one after the other, which made every 10th timestamp ~23 µs late. Frames now start 0.35 frame after each edge (default on both Pis).

## 1. Approach
- **Why not free-running cameras:** two free-running sensors drift against each other. In the free-run test they sat 0.49 ms apart, and that was luck: any offset up to half a frame (5 ms at 100 fps) is possible. At 5 m/s, 1 ms is 5 mm between the two views (see `system-architecture.md`).
- **Why not FSIN:** the sensor's frame-sync input needs a wire soldered to each camera module and support in the `ov9282` driver. The vblank phase lock needs neither: the driver's `vertical_blanking` control is enough.
- **Why both Pis lock, not just the Zero:** each camera runs from its own oscillator on the module, not from its Pi's clock. The Pi 3's camera drifts against the Pi 3 just as the Zero's drifts against the Zero (both measured ~35 ppm slow).
- **Why a shared edge instead of sending times:** both Pis timestamp the same physical edge. The clock offset between the Pis never has to be known, and NTP or network latency doesn't matter.
- **Why hardware PWM:** the pulse comes from the Pi 3's crystal through the PWM peripheral, with no software in the timing path. The edges measured 100.000 ms apart with only µs-level jitter on both Pis.

## 2. Hardware
| From | To | Purpose |
|---|---|---|
| Pi 3 pin 12 (GPIO18, PWM out) | Pi 3 pin 11 (GPIO17) | The Pi 3 timestamps its own pulse (jumper between adjacent pins) |
| Pi 3 pin 12 (GPIO18) | Pi Zero pin 11 (GPIO17) | Reference to the Zero (a 1 kΩ series resistor is optional protection) |
| Pi 3 pin 14 (GND) | Pi Zero pin 14 (GND) | Common ground |

- **GPIO18** is PWM0 on alt function 5. test-results-2026-10-29 (tests 9-10) had already planned it, with the same jumper to GPIO17.
- **The Pi 3 needs the jumper** because a pin in PWM mode can't also deliver edge events to the GPIO driver.
- **GPIO17** is a plain GPIO input on both Pis. Pinout sites list it as SPI1 CE1, but that alt function only applies if SPI1 is enabled (it isn't on either Pi).
  - The pins kept free for later: UART GPIO14/15 (Zero → Pi 3 link) and SPI0 GPIO7-11 (DAC).
  - If SPI1 is ever needed on the Zero, move the input with `camsync -l <line>`.
- **Both inputs are pulled down** by camsync, so an unconnected wire reads as "no pulse" instead of noise. Both boards use 3.3 V logic, so no level shifting.
- **The pulse** comes from `pulse.sh`: 10 Hz, 1 ms high, rising edge used. It loads the `pwm` overlay at runtime (`dtoverlay pwm pin=18 func=2`), so it's gone after a reboot. For a permanent setup, add `dtoverlay=pwm,pin=18,func=2` to `/boot/firmware/config.txt` on the Pi 3.

## 3. The lock: `camsync.c`
The same program runs on both Pis: `sudo ./camsync [-f fps] [-p pulse_hz] [-o offset_us] [-t seconds] [-u] [-s]`.

### 3.1 Capture
- 640x400 Y8 over raw V4L2 (no ISP), HBLANK 890, so a line is 1530 px / 192 MHz = 7.96875 µs (real R8 pixel clock, see test-results-2026-10-29).
- Frame period = (VTS + 0.95) lines with VTS = 400 + vblank. At 100 fps the nominal vblank is 854.
- Exposure defaults to VTS − 30 − 20 = 1204 lines (9.59 ms, 96 % of the frame). The 20 lines of slack are how far the loop may shorten a frame; it may lengthen without limit.
- V4L2 timestamps are CLOCK_MONOTONIC at frame start.

### 3.2 Edge timestamps
- **Source:** the GPIO character device (v2 uAPI, no libgpiod needed). The kernel takes the rising-edge timestamp in the interrupt handler, in CLOCK_MONOTONIC: the same clock as the frame timestamps.
- **Smoothing:** the edges are filtered into a grid.
  1. Predict the next edge from the last one plus the estimated period.
  2. Take the residual between the measured edge and the prediction.
  3. Correct the phase by 0.3 × residual and the period by 0.05 × residual.
- **Missing edges** are counted by rounding the gap to whole periods.
- **Outliers:** an edge more than 300 µs off the grid is ignored. After 3 in a row, the grid restarts.
- **Measured edge residuals:** Pi 3 sd 0.95 µs (max 4.3), Pi Zero sd 1.39 µs (max 6.0).

### 3.3 Phase error
With the edge period Tp and N = fps / pulse rate (10), every frame start S should sit on the grid E + off + m · T with T = Tp / N:
```
d = S − E − off
m = round(d / T)          frame number since edge E
e = d − m · T             phase error, in [−T/2, T/2)
g = k · N + m             global frame number (k = edge number)
```
T comes from the measured edge period, so the frame rate locks to the Pi 3's crystal and not to either Pi's own clock.

### 3.4 Steering vblank
- **When a write takes effect:** a vblank written after dequeuing frame n sets the interval from frame n+1 to n+2 (test-results-2026-10-29, test 5). The interval n → n+1 is already fixed.
- **Each frame:**
  ```
  e1 = e + (v_now + 400.95) · L − T          predicted error of frame n+1 (wrapped to ±T/2)
  v  = round((T − G · e1) / L − 400.95)      vblank for n+1 → n+2, G = 0.5
  ```
  `v` is clamped to [vblank_min, 2 × nominal]. It is written with the `V4L2_CID_VBLANK` control (0.15-0.33 ms at 400 kHz I2C), only when it changes.
- **Line time L is learnt** from undisturbed frame intervals (moving average, gain 0.02; intervals more than 300 ppm off are ignored). This absorbs the sensor crystal's error: both sensors run ~35 ppm slow. In practice vblank sits at 854 and steps to 853 about 4 times a second.
- **Acquisition:** from any start phase the camera is locked within 1 s.
- **Quantisation:** vblank is an integer number of lines, so the phase dithers within about one line (8 µs). A finer step would need HTS trimming or FSIN.

### 3.5 Offset: the edge must not hit a frame start on the Zero
- **First wired run, frames starting on the edge** (offset 0):
  - Pi 3: sd 2.2 µs.
  - Zero: sd 8 µs, max 26-29 µs, and 7× as many vblank writes.
- **Cause:** on the Zero, every 10th frame-start timestamp came ~23 µs late and the next one correspondingly early. Those are the frames that start on an edge.
  - The Zero has one core, so the camera's frame-start interrupt and the GPIO interrupt are served one after the other, and one timestamp waits for the other.
  - Edge residuals were also 8.8 µs sd instead of 1.4.
  - The loop then "corrected" timing noise that wasn't in the sensor at all.
- **Fix:** frames start 0.35 frame after each edge (default `-o`; 3.5 ms at 100 fps), so the edge lands at 65 % of a frame. That is away from the frame-start interrupt and from the frame-end interrupt at ~3.2 ms.
  - Both Pis use the same offset, so the cameras stay aligned.
  - With it, the Zero's frame-interval noise dropped from 8.9 to 2.0 µs sd and its lock from sd 8 µs to 2.5 µs.
- **Real-time priority:** without sudo (no SCHED_FIFO), one Zero vblank write took 9 ms (preempted) and caused a single 42 µs excursion. Always run camsync with sudo.

### 3.6 Output (`<dir>/` on the Pi)
| File | Content |
|---|---|
| `frames.csv` | seq, timestamp, edge number k, frame-in-period m, phase error e, vblank, locked flag |
| `edges.csv` | edge timestamp (monotonic and wall clock), k, filtered grid time, residual |
| `cells.u16` | per frame a 32x20 grid of 20x20 px sums (every 2nd row), ~1.3 kB/frame |
| `snap.pgm` | one full frame after 1 s, to check aim and exposure |
| `meta.txt` | fps, N, final period and line time, exposure, gain, offset, drops, writes |

Options for testing: `-u` measures the phase but never steers (free-run baseline), `-s` uses a synthetic reference in the Pi's own clock (loop test without wires).

## 4. The optical check: screen flash test
Both cameras film the laptop screen, where `flash.html` flashes a full-width band at random times (on 150-400 ms, off 300-700 ms), so the flashes have no relation to the frame grid. `run_flash_test.sh` records on both Pis at once, fetches the data and runs `flash_analyze.py`.

1. **Pair frames across the Pis.** Both logged the same edges. Matching edges by wall-clock time (NTP only has to be right to ±50 ms at 10 Hz) gives the edge number shift, and with it the same global frame number g on both cameras.
   - Measured: the wall clocks differed by 0.9 ms.
2. **Band signal.** The cells that change most between off and on (≥ 50 % of the maximum contrast) are summed per frame. Constant bright spots, like a lamp reflection on the screen, drop out.
3. **Timing inside the frame.** The exposure covers 96 % of the frame, so a light step turns into a brightness ramp across one frame.
   1. For each flash edge, normalise the signal to the levels before and after (0 → 1).
   2. Interpolate the 50 % crossing between frames. That gives the flash time in fractional frames, c.
   3. Optical offset B − A = (c_A − c_B) · T, i.e. how much later camera B exposes than camera A.
   - This uses only frame numbers, not timestamps, so it checks the edge timestamps independently.
4. **Cross-check** with the edge-measured offset e_B − e_A of the frames around each flash.

Validated on simulated recordings first:
- 0 µs offset → 0.0 ± 0.7 µs.
- 37 µs offset → mean 38.9 µs (±18 µs per flash edge).
- Edge cross-check 37.0 µs.

**Brightness matters.** At full white the band clipped at 255 on both cameras (72 % of the band pixels on the Pi 3). Clipping flattens the ramp, so `flash.html` has a brightness control (↑/↓) and the analysis warns about saturated cells. The tests ran at 60 %.

## 5. Results
### Lock over the wire (15 s each, both Pis at once)
| | Pi 3 | Pi Zero |
|---|---|---|
| Edge on frame start (offset 0) | sd 2.2 µs, max 10.4 µs, 51 writes | sd 8 µs, max 28.9 µs, 365 writes |
| **Edge at 65 % of frame (default)** | **sd 1.9-2.4 µs, max 8.6 µs**, 56 writes | **sd 2.5-2.6 µs, max 7.8 µs**, 57 writes |
| Dropped frames | 0 / 1498 | 0 / 1499 |

### Screen flash test (30 s each, 100 fps)
| | Same first frame | Optical B−A, rise | Optical B−A, fall | Edge-measured B−A |
|---|---|---|---|---|
| Locked | **60/61** | −160 ± 61 µs | −67 ± 32 µs | **−0.8 ± 3.3 µs** |
| Free-run (`-u`) | 62/67 | −635 ± 212 µs | −538 ± 229 µs | −485 ± 4.8 µs |
| Optical − edge, locked | | −160 µs | −67 µs | |
| Optical − edge, free-run | | −150 µs | −53 µs | |

- **The optical reading has a screen bias** of about −150 µs (flash on) and −55 µs (flash off).
  - It is the same with and without the lock, so it doesn't come from the cameras.
  - It differs between rise and fall, which a real camera offset never would.
  - Most likely cause: the cameras view the LCD from different angles, and an LCD's transition curve depends on the viewing angle.
- **With the bias removed,** the locked cameras are −11 µs (rise) and −14 µs (fall) apart, about ±40 µs. That is consistent with the edge-measured −0.8 µs.
- **The optical reading follows the free-run offset** (−485 µs) with the same bias. So the optical test does detect real offsets, and the edge measurement doesn't hide a large error.
- **"Same first frame" alone only proves < 1 frame.** The free-run cameras happened to sit only 5 % of a frame apart and still matched 62 of 67 times.
- **Per-flash scatter** is 30-60 µs when locked and ~220 µs when free-running. The interpolation error only cancels when both cameras sample at the same moments, as in the simulation.

## 6. Limits and open points
- **Only tested at 640x400, 100 fps.** Not yet tested with the sensor crop at 678+ fps (crop-evaluation.md):
  - fps must be an integer multiple of the pulse rate (678.7 fps doesn't fit 10 Hz; pick e.g. 680 fps and a matching VTS).
  - In 1280x800 the driver clamps the vblank control at ≥ 110, so the crop mode must write VTS directly over I2C, as crop-evaluation.md already notes.
  - Re-check the interrupt offset there: with short frames, frame start and frame end are close together.
- **Frame start is locked, not exposure.** The exposure windows match if both cameras use the same exposure setting. Not tested: different ROI start rows on the two cameras.
- **Interrupt latency differences** between the Pi 3 and the Zero go straight into the camera-to-camera offset. The optical test bounds that to ~±40 µs. A sharper check would use an LED switched by a GPIO (µs edges, no LCD) instead of the screen.
- **For PAIR in the architecture:** every frame now carries the global frame number g = k · N + m. Detections from both cameras can be paired by g directly; the edge number shift between the Pis is fixed once at startup by wall-clock matching.
- **The pulse isn't persistent:** run `pulse.sh` after each reboot of the Pi 3, or add the overlay to `config.txt`.

## Reproduce
```
ssh pi3 'sudo ~/sync/pulse.sh'                     # start the 10 Hz pulse
ssh pi3 'cd ~/sync && sudo ./camsync -t 15'         # lock check, prints LOCKED and the phase error each second
ssh pizero 'cd ~/sync && sudo ./camsync -t 15'
tools/sync/run_flash_test.sh 30                     # flash.html open and flashing, both cameras on the band
tools/sync/run_flash_test.sh 30 -u                  # free-run baseline
ssh pi3 'sudo ~/sync/pulse.sh stop'
```
