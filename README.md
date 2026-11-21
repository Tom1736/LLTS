# LLTS

Low-latency laser tracking of a ping pong ball. Two global-shutter cameras watch the ball, two Raspberry Pis find it in their images, and an XY galvo steers a laser to where the ball will be by the time the mirrors get there.

> **Work in progress, actively developed.** The camera side (sensor cropping, frame sync, calibration, a first tracker) and the beam side (DAC, analog stage, galvo control, mount) each work on their own. They are not joined into one closed loop yet. Everything below reflects the state of late November 2026.

<p align="center">
  <img src="docs/images/head-mount-assembled.jpg" alt="Printed head mount with two cameras, galvo and laser" width="360">
  &nbsp;
  <img src="docs/images/analog-stage-breadboard.jpg" alt="Breadboard with the LM324 analog stage and the DAC" width="360">
</p>

*Left:* the printed head: OV9281 cameras in the two end blocks, the XY galvo in the middle, the laser tube in its two sliding clips. Pi 3B bottom left, Pi Zero W on the left. *Right:* the analog stage between DAC and galvo drivers, on a breadboard for now: an LM324 shifts the DAC's 0–10 V to ±5 V. The Gravity DAC is bottom right, the ±12 V supply in the back.

## The problem

A ping pong ball easily does 5 m/s. That is 5 mm per millisecond, so every millisecond between exposure and the mirrors moving leaves the dot 5 mm behind the ball. At 1 m from the cameras one pixel is about 1 mm, and the ball is about 38 px across.

The stock camera stack doesn't get close. Through libcamera and the ISP, the Pi 3B dropped about 20 % of frames at 288 fps, and indoor auto exposure sits at 10 ms or more. So most of the work so far went into taking the camera path apart and measuring every step of it.

## How it's meant to work

```
cam B (OV9281) ─ Pi Zero W: detect ─── UART ───┐
                                               ▼
cam A (OV9281) ─ Pi 3B:     detect ───► pair by frame no. ─► triangulate ─► track + predict
     ▲                                                                            │
     └──────────── move both crop windows ◄───────────────────────────────────────┤
                                                                                  ▼
                                      galvo mirrors ◄─ ±5 V stage ◄─ DAC ◄─ aim point
```

- **Small window, high frame rate.** The sensor reads its full 1280×800 at about 138 fps. Reading only a 128-row window around the ball gives 679 fps. The window follows the prediction from frame to frame.
- **One timebase for both cameras.** Both sensors are locked to the same 10 Hz pulse, so frame *n* on one camera and frame *n* on the other were exposed at the same moment. Two views taken 1 ms apart would put the triangulated ball 5 mm off.
- **Detection next to the sensor.** Each Pi finds the ball in its own image. Only a 16-byte packet goes from the Zero to the 3B.
- **Aim ahead.** The predictor leads by the whole chain: exposure, readout, detection, DAC, op-amp and mirror settling.

The full design, with the reasoning for each block, is in [docs/system-architecture.md](docs/system-architecture.md). It started as [a hand sketch](docs/block_diagram.jpg).

## Where it stands

### Camera timing (Pi 3B, 29 Oct)
We skipped libcamera and captured raw frames over V4L2. The driver's pixel clock turned out to be wrong: it is 192 MHz, not the 200 MHz the driver reports, which is why libcamera's 8-bit frame rates are 4 % too high. At 640×400 the raw path runs at up to about 288 fps. [Report](docs/test-reports/test-results-2026-10-29.md)

### Sensor crop above 1000 fps (Pi 3B, 2 Nov)
The driver only offers three fixed modes. We stream the 1280×800 mode and overwrite the sensor's window registers over I2C from userspace, with no kernel patch. The window is pixel-exact as long as x edges sit on multiples of 8, y edges are even and the width is at least 120 px; [`roi.py`](tools/crop/roi.py) enforces that.

| Rows read | fps | Dropped frames |
|---|---|---|
| 800 (stock) | 138 | 0 |
| 200 | 488 | 0 / 4000 |
| 128 | 679 | 0 / 4000 |
| 64 | 1038 | 0 / 4000 |
| 16 | 1719 | 15 / 4000 |

Above 1000 fps, with the camera I2C at 400 kHz, a moved window shows up exactly two frames later (197 of 197 jumps). On the camera node, end of exposure to "detection packet sent" adds up to about 1.85 ms at 128 rows. [Report](docs/test-reports/crop-evaluation.md)

### Frame sync between the two Pis (3 Nov)
There is no frame-sync wire to the sensors. Instead, the Pi 3B puts out a 10 Hz hardware PWM pulse, both Pis timestamp its edges, and each one nudges its own sensor's vertical blanking one line at a time until frames start on the grid. Result: about 2–2.6 µs standard deviation, under 9 µs worst case, no dropped frames. One sensor line is 8 µs, so that is as tight as this method gets.

To check it optically, both cameras filmed a laptop screen flashing at random times: 60 of 61 flashes landed in the same frame on both. Along the way we found that on the single-core Zero, a frame starting right on the pulse edge delays one interrupt behind the other by ~23 µs, so frames now start 0.35 frame after each edge. Only tested at 640×400, 100 fps so far. [Report](docs/test-reports/frame-sync-2026-11-03.md)

### Calibration (Pi Zero camera, 2 Nov)
A tablet shows a checkerboard, and a script on the PC keeps a frame only when the board is still and in a new pose. 60 views, reprojection error 0.148 px. The measured field of view is 66.7° × 44.8° (75.6° diagonal), not the 79.3° the shop lists. Distortion moves the corners by 18 px, so every point gets undistorted before it's used. [Report](docs/test-reports/test-results-2026-11-02.md), [how-to](tools/calib/README.md)

### First tracker (Pi 3B, 2 Nov, updated 16 Nov)
[`track.c`](tools/track/track.c) finds a dark test object in raw 640×400 frames at 250 fps and records frames plus centroids. In the first throw tests it dropped no frames, and the full-frame search took about 2 ms per frame. It has since gained a search window around the last position plus velocity. One camera only, no crop yet.

### DAC and galvo (16–19 Nov)
A DFRobot Gravity GP8403 (2-channel I2C DAC) on the Pi 3B drives the galvo. The scripts in [`tools/dac/`](tools/dac/) talk to `/dev/i2c-1` directly and protect the galvos: a hard voltage cap, a slew limit, soft start and stop. They draw sines, circles, squares and text. One of the two vector fonts writes a whole word as a single connected line, so the beam never has to jump. One channel updates about 6000 times a second, and a GPIO marker lets us measure latency on the scope.

### Analog stage (18 Nov)
An LM324 difference amplifier maps the DAC's 0–10 V to the galvo's ±5 V. The 5 V reference comes from its own regulator, because the Pi's 5 V rail logs undervoltage and a divider off the 12 V supply sags whenever the mirrors move. A pull-down to −12 V keeps the LM324's crossover glitch away from the galvo's centre position. Built on the breadboard in the photo above. [Build notes and schematic](docs/galvo-analog-stage.md)

### Head mount (17–18 Nov)
One parametric OpenSCAD file, no screws. The cameras and galvo press in, and the laser sits in two sliding clips that are also how it gets aligned onto the mirror. Cameras 165 mm apart, toed in 3.3°, whole head tilted up 15°. The model checks that the camera views, the ±30° scan cone and the laser path stay clear of the frame. Printed and assembled. [CAD, print and alignment notes](cad/head-mount/README.md)

## Next up

- Calibrate the Pi 3B camera, then the stereo pair. The board's square size still needs measuring for that.
- Benchmark the Pi Zero: can one core capture, copy the window and find the centroid at 600+ fps? If not, the split between the two Pis changes.
- Run frame sync together with the sensor crop. The frame rate has to be a multiple of the 10 Hz pulse (680 instead of 678.7 fps), and in the crop mode the frame length has to be written straight to the sensor.
- Write the parts that are designed but not built: triangulation, track filter, predictor, crop-window planner, UART link.
- Calibrate the galvo: mirror geometry and pose relative to the cameras.
- Confirm the galvo drivers' input range, and measure whether X and Y change at the same moment. Over I2C the DAC writes one channel after the other; the architecture assumed both outputs latch together.
- Light: tracking needs 1 ms exposure or less, which means roughly 10× more light on the ball than indoor lighting gives.
- Laser watchdog: switch the laser off when a camera stream stalls or the track is lost.
- Fix the Pi 3B's power supply (undervoltage).

## Hardware

| | |
|---|---|
| Cameras | 2 × OV9281, 1 MP mono global shutter, 2.85 mm f/2 fixed focus (DFRobot SEN0634) |
| Compute | Raspberry Pi 3B (camera A and the main loop), Raspberry Pi Zero W (camera B) |
| Beam | XY galvo with drivers, laser module in a 16.5 mm tube |
| Galvo drive | DFRobot Gravity GP8403 I2C DAC, LM324 stage on ±12 V, separate 5 V reference (MB102 fed by a USB-C PD trigger at 9 V) |
| Mount | 3D-printed, press-fit, no screws |

## Repo layout

```
docs/
  system-architecture.md    block diagram and the reasoning behind it
  galvo-analog-stage.md     op-amp stage: schematic, wiring, bring-up, troubleshooting
  hardware-setup.md         Pis, network, camera config, pitfalls (German)
  kamera-grundlagen.md      OV9281 basics: focal length, FOV, distortion, focus (German)
  test-reports/             dated measurement reports, where all the numbers come from
  images/
tools/
  crop/      sensor window over I2C and its verification
  sync/      camsync.c (frame sync), screen flash test (how-to in German)
  calib/     live view, focus, intrinsic calibration (how-to in German)
  track/     track.c single-camera tracker, view.py turns recordings into video
  dac/       GP8403 driver with output cap, galvo test patterns, vector fonts
cad/
  head-mount/   OpenSCAD source, STLs, 3MF print plates
  reference/    measurements and photos of camera, galvo and laser used for the CAD
calib/          calibration images and results per camera
```

Most of the code runs on the Pis over SSH; usage is in each file's header comment or the folder's README. There is no single build step yet, since the pieces are still separate experiments. Raw recordings (~370 MB) and sync test results stay out of git.

If you only read one report, read [crop-evaluation.md](docs/test-reports/crop-evaluation.md). It explains most of the design choices.

## Team

First-semester students at ETH Zurich:

- Tom Schmidt-Ott (Electrical Engineering and Information Technology)
- Tim Sindelar (Computer Science)
- Hannes Sobottka (Physics)

## License

[MIT](LICENSE), for code, CAD files and docs.
