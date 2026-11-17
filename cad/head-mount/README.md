# Head mount: cameras, galvo, laser (2026-11-16)
A 3D-printed mount that holds both OV9281 cameras, the XY galvo and the laser on one plate, plus a stand that tilts the whole head up. Everything is in one parametric OpenSCAD file, [llts_head.scad](llts_head.scad). Open it in OpenSCAD and change values under Window > Customizer.

| Preview | |
|---|---|
| ![front](preview_front.png) | ![back](preview_back.png) |

![top view with camera fields of view (blue) and galvo scan cone (red)](preview_top_fov.png)

## Geometry
| | Value | Parameter |
|---|---|---|
| Camera spacing (lens to lens) | 165 mm | `cam_spacing` |
| Toe-in per camera | 3.3° (designed for a 60° galvo) | `toe_in` |
| Upward pitch of the whole head | 15°, set by the stand | `pitch` |
| Galvo | centred between the cameras, beam leaves along the head's forward axis | |
| Laser | enters from the left, horizontally, at the lower mirror's height | |
| Beam height above the plate | 27.5 mm (galvo seat 10 mm + mirror 17.5 mm) | `galvo_raise`, `mirror_h` |
| Camera lens height above the plate | 30 mm | `cam_lens_z` |
| Plate | 224 × 63 mm | derived |

- **Cameras sit 30 mm in front of the galvo exit.** So they don't see the galvo or the laser, and the beam never reaches the camera holders.
- **The laser runs behind the left camera.** The checks render the head against the camera fields of view, the galvo scan cone (±30°) and the laser path; all three come out empty.
- **Galvo orientation**, seen from behind the head looking where the beam goes: the X motor (lower mirror) sticks out backward and the Y motor (upper mirror) to the right. The lower mirror scans horizontally.

## Parts
| STL | Count | Notes |
|---|---|---|
| `stl/head.stl` | 1 | plate, camera pockets, galvo seat, lower halves of the laser rings. Print flat as exported. |
| `stl/ring_cap.stl` | 2 | upper half of a laser ring. Print split face down (as exported). |
| `stl/stand.stl` | 1 | 15° wedge. Print as exported. |
| `stl/test_camera.stl`, `test_galvo.stl`, `test_ring.stl` | 1 each | small fit tests, see below |

- **Print settings:** PETG or PLA, 0.2 mm layers, 3-4 walls, 25-40 % infill. No supports needed.
- **Bed size:** the plate is 224 mm long. It fits a 256 mm bed (Bambu A1/P1/X1). On a 220 × 220 bed, turn it 45°.

## Hardware
| Part | Count | Use |
|---|---|---|
| M3 × 16 socket head or set screw | 6 | laser push screws, 3 per ring |
| M3 × 10 socket head | 4 | ring caps |
| M3 × 12 countersunk | 4 | head to stand |
| M3 hex nut | 14 | all captive, slid into slots |

## Before printing the head
1. **Measure the lower mirror position on the galvo.** The values come from the photos and are probably within ±2 mm. The laser rings can adjust ±3 mm, so a good measurement keeps the beam near the middle of that range.
   - `mirror_x`: bracket's left face to the lower mirror centre (default 11.5)
   - `mirror_y`: bracket's back face to the lower mirror centre (default 24.5)
   - `mirror_h`: bracket bottom to the lower mirror centre (17.5, from you)
2. **Check the galvo footprint.** The seat expects the L-shaped bracket to fill a 32 × 32 mm box (`galvo_w`, `galvo_d`). The X motor must sit at least 4 mm above the bracket bottom, otherwise lower `galvo_wall_h`.
3. **Rotate the laser so the beam hole points up.** The rings are placed for that. If it has to point elsewhere, set `laser_hole_angle` (90 = up, 270 = down).
4. **Print the test pieces (~30 min in total).**
   - `test_camera`: the PCB should press in by hand and stay put. Too tight: lower `pcb_rib_interf`. Too loose: raise it (steps of 0.05).
   - `test_galvo`: the galvo should press in with light force. Tune with `galvo_rib_interf` and `galvo_clear`.
   - `test_ring`: check that the nuts slide into their slots and the screws reach the tube.

## Assembly
1. **Nuts:** slide the M3 nuts into all slots: 4 per ring bottom (2 push screws, 2 cap screws), 1 per ring cap, and 1 per stand rib.
2. **Cameras:** push each camera in from behind, connector up, until the PCB sits on the four standoffs. The lens sits flush with the front face. The ribbon leaves upward and bends back over the laser.
   - **The image is upside down** compared with the connector-down orientation. The intrinsic calibration stays valid, because it belongs to the sensor. Do the stereo calibration after mounting.
3. **Galvo:** press it into its seat, X motor toward the back.
4. **Laser:** lay it into the two lower ring halves, front end toward the galvo, hole up. Put the caps on and screw them down with M3 × 10.
5. **Push screws:** turn in until they touch the tube: 1 from the top, 2 from below at 30° (front-down and back-down).
6. **Stand:** screw the head onto the stand with 4 × M3 × 12 countersunk screws.

## Aligning the laser
Use the lowest laser power and laser safety glasses. Centre the galvo (0 V on both axes) and put a scrap of paper on the lower mirror to see the spot.

| Move the beam | At a ring |
|---|---|
| up | top screw out, both lower screws in by the same amount |
| down | both lower screws out, top screw in |
| forward (toward the cameras) | front-down screw out, back-down screw in |
| backward | back-down screw out, front-down screw in |

- **Both rings the same way:** the beam shifts in parallel.
- **Only the back ring:** the beam tilts around the front ring. At the mirror, about 50 mm away, moving the back ring 1 mm shifts the spot about 0.7 mm the opposite way.
- **When the spot sits on the mirror centre:** snug all three screws on each ring so the tube can't rotate. Turning the tube moves the beam on a 4.25 mm circle around its axis.
- **Range:** ±3 mm at each ring, which gives roughly ±3 mm shift and ±5° tilt.

## Regenerating the STLs
```bash
cd cad/head-mount && for p in head stand ring_cap test_camera test_galvo test_ring; do openscad --backend=manifold -D "part=\"$p\"" -o stl/$p.stl llts_head.scad; done
```
OpenSCAD comes from `brew install --cask openscad@snapshot`; the stable cask is disabled in Homebrew. The console prints the plate size, beam height, ring positions and the gap between the laser and the left camera.

## Open points
- **Mirror position** (`mirror_x`, `mirror_y`): estimated from photos, should be measured.
- **Galvo hold-down:** crush ribs only for now. If the galvo bracket has threaded holes underneath, screw holes through the seat can be added.
- **Pi boards and cable strain relief:** not part of the mount yet.
