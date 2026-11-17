// LLTS head mount: 2x OV9281 camera (SEN0634), XY galvo (ZJ15K type), laser tube.
// Parametric OpenSCAD model. Open in OpenSCAD and use Window > Customizer to change values.
// Units: mm, angles: degrees.
//
// Head frame (everything is built in it; the stand then tilts it up by `pitch`):
//   X = right, seen from behind the head looking where the beam leaves the galvo
//   Y = forward = direction of the beam leaving the galvo
//   Z = up, Z = 0 is the top surface of the base plate
//   X = Y = 0 sits under the centre of the lower (X) galvo mirror, which is
//   also where the beam leaves the upper mirror, i.e. the middle of the system.
//
// Parts to print (export each with `part`):
//   head      base plate with camera pockets, galvo seat and the lower halves of the laser rings
//   stand     wedge that tilts the head up by `pitch`
//   ring_cap  upper half of a laser ring, print 2
//   test_*    small pieces to check fits before printing the head

/* [Render] */
// What to show or export
part = "assembly"; // [assembly, head, stand, ring_cap, test_camera, test_galvo, test_ring]
// Show the camera fields of view and the galvo scan cone in the assembly
show_fov = true;
// Show dummy cameras, galvo and laser in the assembly
show_hardware = true;

/* [Layout] */
// Lens centre to lens centre
cam_spacing = 165; // [150:1:180]
// Each camera turned inward
toe_in = 3.3; // [0:0.1:10]
// Upward tilt of the whole head, set by the stand
pitch = 15; // [0:1:30]
// Y of the camera front face (lens plane), head frame
cam_front_y = 30;
// Height of the lens centre above the plate top
cam_lens_z = 30;

/* [Camera module SEN0634 / OV9281-79] */
pcb_w = 25;
pcb_h = 24;
pcb_t = 1.0;
// Lens centre from the PCB edge opposite the connector (the connector points up)
lens_from_edge = 8.35;
// Mounting hole spacing across the board (holes are only used as standoff spots)
hole_dx = 21;
// Mounting holes measured from the edge opposite the connector
hole_z = [2.0, 15.5];
// Square lens holder
lens_box = 6.5;
// Lens tip above the PCB front surface
lens_len = 5.18;
// Gap between PCB front and front wall (the connector is 2.5 high)
comp_gap = 3.0;
cam_front_wall = 2.0;
cam_wall = 2.5;
// Total clearance across the PCB width/height
pcb_clear = 0.4;
// Crush rib interference per side; raise if the cameras sit too loose
pcb_rib_interf = 0.15;
// Crush rib heights relative to the lens centre
cam_rib_z = [-3, 9];
// Extra size of the lens window
lens_clear = 0.8;
// Depth of the camera base behind the front face
cam_shelf = 12;

/* [Galvo (seen from behind: X motor sticks out backward, Y motor to the right)] */
// Bracket footprint, left-right
galvo_w = 32;
// Bracket footprint, back-front
galvo_d = 32;
// Lower mirror centre, measured from the bracket's left face
mirror_x = 11.5;
// Lower mirror centre, measured from the bracket's back face
mirror_y = 24.5;
// Lower mirror centre above the bracket's bottom
mirror_h = 17.5;
// Upper mirror height (preview and clearance only)
upper_mirror_h = 28;
// Galvo seat height above the plate
galvo_raise = 10;
galvo_clear = 0.5;
galvo_wall = 3;
galvo_wall_h = 4;
galvo_rib_interf = 0.15;
// Gap in the back wall for the X motor
motor_cut = 28;
// Crush rib positions along each wall, from the bracket's left-back corner
rib_left = [5];
rib_right = [8, 24];
rib_back = [29];
rib_front = [27];

/* [Laser] */
laser_d = 16.5;
laser_len = 107;
// Beam hole centre from the tube's outer surface
laser_hole_from_edge = 4;
// Where the beam hole points, seen from the laser front: 90 = up, 270 = down, 0 = forward
laser_hole_angle = 90; // [0:15:345]
// Gap between galvo seat wall and laser front
laser_gap = 5;
// Ring positions, measured from the laser front (clear bands: 0-13, 20-40, 88-107)
ring_pos = [30, 97];
ring_t = 10;
// Radial adjustment range per ring
adjust = 3;
// Push screw directions in the ring plane: 90 = up, 210 = back-down, 330 = front-down
screw_angles = [90, 210, 330];
ear_w = 8;
ear_lo = 5;
ear_hi = 4;
sup_t = 1.5;
ped_w = 16;

/* [Hardware] */
m3_d = 3.3;
nut_af = 5.5;
nut_t = 2.4;
nut_clear = 0.3;

/* [Base plate and stand] */
plate_t = 5;
plate_r = 4;
rim_h = 8;
rim_t = 3;
// Stand screw positions (X, Y) in the head frame, countersunk M3 from the top
stand_screws = [[-105, -18], [85, -18], [-35, 18], [35, 18]];
// Height of the plate's back edge above the table
stand_min_h = 10;
stand_rib_t = 10;
stand_bar_w = 10;
stand_bar_h = 3;

/* [Hidden] */
$fn = 64;
eps = 0.01;

// ---------- derived values ----------
c_g = galvo_clear / 2;
gx0 = -mirror_x;               // bracket left face
gy0 = -mirror_y;               // bracket back face
beam_z = galvo_raise + mirror_h;
up_z = galvo_raise + upper_mirror_h;
hole_off = laser_d / 2 - laser_hole_from_edge;
axis_y = -hole_off * cos(laser_hole_angle);
axis_z = beam_z - hole_off * sin(laser_hole_angle);
laser_front_x = gx0 - c_g - galvo_wall - laser_gap;
nut_tc = nut_t + nut_clear;
nut_afc = nut_af + nut_clear;
R_b = laser_d / 2 + adjust;
R_n = R_b + 2 + nut_tc / 2;
R_o = R_n + nut_tc / 2 + 2;
ear_y = R_o + ear_w / 2;

pw = pcb_w + pcb_clear;
pcb_front_y = -(cam_front_wall + comp_gap);
pcb_back_y = pcb_front_y - pcb_t;
pocket_back_y = pcb_back_y - 1.5;
cam_top_z = pcb_h - lens_from_edge;
cam_floor_z = -(lens_from_edge + pcb_clear / 2);
cam_half = pw / 2 + cam_wall;

plate_x0 = laser_front_x - max(ring_pos) - ring_t / 2 - 2;
plate_x1 = cam_spacing / 2 + cam_half * cos(toe_in) + cam_shelf * sin(toe_in) + 2;
plate_y0 = min(gy0 - c_g - galvo_wall, axis_y - R_o - ear_w) - rim_t - 1;
plate_y1 = cam_front_y + 1;

lift = stand_min_h - (plate_y0 * sin(pitch) - plate_t * cos(pitch));

// ---------- checks ----------
assert(axis_z - R_o > 0, "laser ring would cut into the plate: raise galvo_raise");
assert(cam_lens_z > lens_from_edge + 3, "cam_lens_z too low for the camera pocket floor");
assert(ring_pos[0] - ring_t / 2 >= 20 && ring_pos[0] + ring_t / 2 <= 40, "front ring outside the clear band 20-40");
assert(ring_pos[1] - ring_t / 2 >= 88 && ring_pos[1] + ring_t / 2 <= 107, "back ring outside the clear band 88-107");
assert(lens_len >= cam_front_wall + comp_gap - 0.3, "lens tip sits deep inside the front wall: check comp_gap");

cam_back_y = cam_front_y - cam_shelf * cos(toe_in) - cam_half * sin(toe_in);
echo(str("plate ", plate_x1 - plate_x0, " x ", plate_y1 - plate_y0, " mm"));
echo(str("beam height above plate ", beam_z, ", laser axis Y ", axis_y, " Z ", axis_z));
echo(str("laser front X ", laser_front_x, ", rings at X ", [for (d = ring_pos) laser_front_x - d]));
echo(str("gap laser tube surface -> left camera base ", cam_back_y - (axis_y + laser_d / 2), " mm"));
echo(str("ring bore ", 2 * R_b, ", ring OD ", 2 * R_o));

// ---------- helpers ----------
module rrect(x0, y0, x1, y1, h, r) {
    hull() for (x = [x0 + r, x1 - r], y = [y0 + r, y1 - r]) translate([x, y, 0]) cylinder(r = r, h = h);
}

module head_to_world() {
    translate([0, 0, lift]) rotate([pitch, 0, 0]) children();
}

// ---------- camera holder ----------
// Local frame: origin = lens centre on the front face, +y = optical axis, +z = up.
// The PCB is pushed in from behind against four standoffs at the mounting holes;
// crush ribs on the side walls hold it. The connector points up, the ribbon leaves upward.
module camera_holder(base_h = cam_lens_z) {
    so = 3.2;
    // base below the pocket floor, with a shelf to the back
    translate([-cam_half, -cam_shelf, -base_h]) cube([2 * cam_half, cam_shelf, base_h + cam_floor_z]);
    difference() {
        union() {
            // front wall
            translate([-cam_half, -cam_front_wall, cam_floor_z - eps]) cube([2 * cam_half, cam_front_wall, cam_top_z - cam_floor_z]);
            // side walls
            for (s = [-1, 1]) translate([s > 0 ? pw / 2 : -cam_half, pocket_back_y, cam_floor_z - eps])
                cube([cam_wall, -pocket_back_y, cam_top_z - cam_floor_z]);
        }
        // lens window with a 45 degree chamfer at the front
        lw = lens_box + lens_clear;
        translate([-lw / 2, -cam_front_wall - 1, -lw / 2]) cube([lw, cam_front_wall + 2, lw]);
        hull() {
            translate([-lw / 2 - 1.2, -eps, -lw / 2 - 1.2]) cube([lw + 2.4, 1, lw + 2.4]);
            translate([-lw / 2, -1.2, -lw / 2]) cube([lw, eps, lw]);
        }
    }
    // standoffs at the four mounting holes (pads only, no components there)
    for (x = [-hole_dx / 2, hole_dx / 2], hz = hole_z)
        translate([x - so / 2, pcb_front_y - eps, hz - lens_from_edge - so / 2]) cube([so, comp_gap + 2 * eps, so]);
    // crush ribs along the push-in direction, with a lead-in
    p = pcb_clear / 2 + pcb_rib_interf;
    for (s = [-1, 1], z = cam_rib_z) {
        ax = s * (pw / 2 + 0.6 - p);
        hull() {
            translate([ax, pcb_front_y, z]) rotate([90, 0, 0]) cylinder(r = 0.6, h = pcb_t + 0.6, $fn = 16);
            translate([ax + s * 0.45, pocket_back_y + 0.01, z]) rotate([90, 0, 0]) cylinder(r = 0.15, h = 0.01, $fn = 8);
        }
    }
}

module at_cam(s) {
    translate([s * cam_spacing / 2, cam_front_y, cam_lens_z]) rotate([0, 0, s * toe_in]) children();
}

// ---------- galvo seat ----------
module galvo_seat(raise = galvo_raise) {
    ix0 = gx0 - c_g; iy0 = gy0 - c_g;
    ix1 = gx0 + galvo_w + c_g; iy1 = gy0 + galvo_d + c_g;
    translate([ix0 - galvo_wall, iy0 - galvo_wall, 0]) cube([ix1 - ix0 + 2 * galvo_wall, iy1 - iy0 + 2 * galvo_wall, raise]);
    difference() {
        translate([ix0 - galvo_wall, iy0 - galvo_wall, raise - eps]) cube([ix1 - ix0 + 2 * galvo_wall, iy1 - iy0 + 2 * galvo_wall, galvo_wall_h]);
        translate([ix0, iy0, raise - 1]) cube([ix1 - ix0, iy1 - iy0, galvo_wall_h + 2]);
        // gap for the X motor that sticks out backward
        translate([-motor_cut / 2, iy0 - galvo_wall - 1, raise - 1]) cube([motor_cut, galvo_wall + 2, galvo_wall_h + 2]);
    }
    // crush ribs
    p = c_g + galvo_rib_interf;
    rr = 0.8;
    module rib(x, y) translate([x, y, raise - eps]) cylinder(r = rr, h = galvo_wall_h, $fn = 16);
    for (v = rib_left) rib(ix0 - rr + p, gy0 + v);
    for (v = rib_right) rib(ix1 + rr - p, gy0 + v);
    for (u = rib_back) if (abs(gx0 + u) > motor_cut / 2 + rr) rib(gx0 + u, iy0 - rr + p);
    for (u = rib_front) rib(gx0 + u, iy1 + rr - p);
}

// ---------- laser ring ----------
// Local frame: origin = ring centre (laser axis when centred), +x = laser axis.
// Three push screws (M3) with captive nuts steer the tube. Two rings = height, side and angle.
module hex_trap_radial(slot_dir) {
    translate([0, R_n, 0]) rotate([-90, 0, 0]) translate([0, 0, -nut_tc / 2]) cylinder(d = nut_afc / cos(30), h = nut_tc, $fn = 6);
    translate([slot_dir > 0 ? 0 : -(ring_t / 2 + 1), R_n - nut_tc / 2, -nut_afc / 2]) cube([ring_t / 2 + 1, nut_tc, nut_afc]);
}

module push_screw(a, slot_dir) {
    rotate([a, 0, 0]) {
        translate([0, R_b - 1, 0]) rotate([-90, 0, 0]) cylinder(d = m3_d, h = R_o - R_b + 3, $fn = 24);
        hex_trap_radial(slot_dir);
    }
}

module ear_holes() {
    for (s = [-1, 1]) translate([0, s * ear_y, -ear_lo - 1]) cylinder(d = m3_d, h = ear_lo + ear_hi + 2, $fn = 24);
}

module ring_bottom(slot_dir = 1, zc = axis_z) {
    difference() {
        union() {
            intersection() {
                rotate([0, 90, 0]) cylinder(r = R_o, h = ring_t, center = true);
                translate([-ring_t, -R_o - 1, -R_o - 1]) cube([2 * ring_t, 2 * R_o + 2, R_o + 1]);
            }
            translate([-ring_t / 2, -ped_w / 2, -zc]) cube([ring_t, ped_w, zc]);
            for (s = [-1, 1]) {
                translate([-ring_t / 2, s > 0 ? R_o - 4 : -(R_o + ear_w), -ear_lo]) cube([ring_t, ear_w + 4, ear_lo]);
                // two thin walls under each ear keep the middle free for the push screw and the hex key
                for (xs = [-1, 1]) translate([xs > 0 ? ring_t / 2 - sup_t : -ring_t / 2, s > 0 ? R_o - 1 : -(R_o + ear_w), -zc])
                    cube([sup_t, ear_w + 1, zc - ear_lo + eps]);
            }
        }
        rotate([0, 90, 0]) cylinder(r = R_b, h = ring_t + 2, center = true);
        translate([-ring_t, -R_o - ear_w - 1, 0]) cube([2 * ring_t, 2 * (R_o + ear_w + 1), R_o + 1]);
        for (a = screw_angles) if (sin(a) < 0) push_screw(a, slot_dir);
        ear_holes();
        // captive nuts for the cap screws, slid in from the outside
        for (s = [-1, 1]) {
            translate([0, s * ear_y, -ear_lo / 2 - nut_tc / 2]) rotate([0, 0, 30]) cylinder(d = nut_afc / cos(30), h = nut_tc, $fn = 6);
            translate([-nut_afc / 2, s > 0 ? ear_y : -(R_o + ear_w + 1), -ear_lo / 2 - nut_tc / 2]) cube([nut_afc, R_o + ear_w + 1 - ear_y, nut_tc]);
        }
    }
}

module ring_cap(slot_dir = 1) {
    difference() {
        union() {
            intersection() {
                rotate([0, 90, 0]) cylinder(r = R_o, h = ring_t, center = true);
                translate([-ring_t, -R_o - 1, 0]) cube([2 * ring_t, 2 * R_o + 2, R_o + 1]);
            }
            for (s = [-1, 1]) translate([-ring_t / 2, s > 0 ? R_o - 4 : -(R_o + ear_w), 0]) cube([ring_t, ear_w + 4, ear_hi]);
        }
        // bore as a clipped teardrop so the cap prints split face down without supports
        rotate([90, 0, 90]) translate([0, 0, -ring_t / 2 - 1]) linear_extrude(ring_t + 2) intersection() {
            hull() { circle(r = R_b); translate([0, R_b * sqrt(2)]) square(0.01, center = true); }
            translate([-R_o, -R_o]) square([2 * R_o, R_o + R_b + 0.75]);
        }
        for (a = screw_angles) if (sin(a) > 0) push_screw(a, slot_dir);
        ear_holes();
    }
}

module at_ring(i) {
    translate([laser_front_x - ring_pos[i], axis_y, axis_z]) children();
}

// ---------- head ----------
module plate() {
    difference() {
        union() {
            translate([0, 0, -plate_t]) rrect(plate_x0, plate_y0, plate_x1, plate_y1, plate_t, plate_r);
            // stiffening rim along the back edge, left out at the rings so the
            // back-down push screws and the ear nut slots stay reachable
            difference() {
                translate([plate_x0 + plate_r, plate_y0, -eps]) cube([plate_x1 - plate_x0 - 2 * plate_r, rim_t, rim_h]);
                for (d = ring_pos) translate([laser_front_x - d - 14, plate_y0 - 1, -1]) cube([28, rim_t + 2, rim_h + 2]);
            }
        }
        for (p = stand_screws) translate([p[0], p[1], 0]) {
            translate([0, 0, -plate_t - 1]) cylinder(d = m3_d, h = plate_t + 2, $fn = 24);
            translate([0, 0, -1.7]) cylinder(d1 = 3.4, d2 = 6.4, h = 1.7 + eps, $fn = 32);
            translate([0, 0, -eps]) cylinder(d = 6.4, h = rim_h + 1, $fn = 32);
        }
    }
}

module head() {
    plate();
    for (s = [-1, 1]) at_cam(s) camera_holder();
    galvo_seat();
    at_ring(0) ring_bottom(slot_dir = 1);
    at_ring(1) ring_bottom(slot_dir = -1);
}

// ---------- stand ----------
module stand() {
    function hw(p) = [p[0] * cos(pitch) - p[1] * sin(pitch), p[0] * sin(pitch) + p[1] * cos(pitch) + lift];
    b = hw([plate_y0, -plate_t]);
    f = hw([plate_y1, -plate_t]);
    xs = [for (p = stand_screws) p[0]];
    difference() {
        union() {
            for (x = xs) translate([x - stand_rib_t / 2, 0, 0]) rotate([90, 0, 90])
                linear_extrude(stand_rib_t) polygon([[b[0], 0], [f[0], 0], [f[0], f[1]], [b[0], b[1]]]);
            for (y = [b[0], f[0] - stand_bar_w])
                translate([min(xs) - stand_rib_t / 2, y, 0]) cube([max(xs) - min(xs) + stand_rib_t, stand_bar_w, stand_bar_h]);
        }
        head_to_world() for (p = stand_screws) translate([p[0], p[1], -plate_t]) {
            translate([0, 0, -30]) cylinder(d = m3_d, h = 31, $fn = 24);
            translate([0, 0, -4 - nut_tc]) {
                cylinder(d = nut_afc / cos(30), h = nut_tc, $fn = 6);
                translate([0, -nut_afc / 2, 0]) cube([stand_rib_t, nut_afc, nut_tc]);
            }
        }
    }
}

// ---------- dummies for the assembly view ----------
module dummy_camera() {
    color("darkgreen") translate([-pcb_w / 2, pcb_back_y, -lens_from_edge]) cube([pcb_w, pcb_t, pcb_h]);
    color("black") {
        translate([-lens_box / 2, pcb_front_y, -lens_box / 2]) cube([lens_box, lens_len - 1, lens_box]);
        translate([0, pcb_front_y, 0]) rotate([-90, 0, 0]) cylinder(d = 5, h = lens_len);
        translate([-11, pcb_front_y, cam_top_z - 5.5]) cube([22, 2.5, 6]);
    }
    color("silver") translate([-8, pcb_front_y + 1, cam_top_z]) cube([16, 0.3, 12]);
}

module dummy_galvo() {
    color([0.15, 0.15, 0.15]) translate([gx0, gy0, galvo_raise]) {
        cube([galvo_w, 11, 40]);
        translate([galvo_w - 10, 0, 0]) cube([10, galvo_d, 40]);
    }
    color([0.1, 0.1, 0.1]) {
        translate([0, gy0, beam_z]) rotate([90, 0, 0]) cylinder(d = 25, h = 17);
        translate([gx0 + galvo_w, -1, up_z]) rotate([0, 90, 0]) cylinder(d = 25, h = 22);
    }
    color("lightblue") {
        translate([0, 0, beam_z]) rotate([0, -45, 0]) cube([5, 9, 0.6], center = true);
        translate([0, 0, up_z]) rotate([45, 0, 0]) cube([14, 6, 0.6], center = true);
    }
}

module dummy_laser() {
    color("silver") translate([laser_front_x - laser_len, axis_y, axis_z]) rotate([0, 90, 0]) cylinder(d = laser_d, h = laser_len);
    color("red") {
        translate([laser_front_x, 0, beam_z]) rotate([0, 90, 0]) cylinder(d = 1, h = -laser_front_x);
        translate([0, 0, beam_z]) cylinder(d = 1, h = up_z - beam_z);
        translate([0, 0, up_z]) rotate([-90, 0, 0]) cylinder(d = 1, h = 200);
    }
}

module frustum(hh, vh, L) {
    hull() {
        cube(0.01, center = true);
        translate([0, L, 0]) cube([2 * L * tan(hh), 0.01, 2 * L * tan(vh)], center = true);
    }
}

module fovs() {
    for (s = [-1, 1]) at_cam(s) translate([0, -1, 0]) color([0.2, 0.4, 1, 0.15]) frustum(66.65 / 2, 44.83 / 2, 250);
    translate([0, 0, up_z]) color([1, 0, 0, 0.12]) frustum(30, 30, 250);
}

module assembly() {
    color("gainsboro") stand();
    head_to_world() {
        color("orange") head();
        color("gold") { at_ring(0) ring_cap(1); at_ring(1) ring_cap(-1); }
        if (show_hardware) {
            for (s = [-1, 1]) at_cam(s) dummy_camera();
            dummy_galvo();
            dummy_laser();
        }
        if (show_fov) fovs();
    }
}

// ---------- test pieces ----------
module test_camera() {
    camera_holder(base_h = lens_from_edge + 3);
}

module test_galvo() {
    translate([-gx0, -gy0, 0]) galvo_seat(raise = 2);
}

module test_ring() {
    translate([0, 0, axis_z]) ring_bottom(1);
    translate([-ring_t / 2 - 2, -R_o - ear_w - 2, 0]) cube([ring_t + 4, 2 * (R_o + ear_w + 2), 2]);
    translate([0, 2 * (R_o + ear_w) + 8, 0]) ring_cap(1);
}

// ---------- output ----------
if (part == "assembly") assembly();
else if (part == "head") head();
else if (part == "stand") stand();
else if (part == "ring_cap") ring_cap(1);
else if (part == "test_camera") test_camera();
else if (part == "test_galvo") test_galvo();
else if (part == "test_ring") test_ring();
