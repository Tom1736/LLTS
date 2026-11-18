// LLTS head mount: 2x OV9281 camera (SEN0634), XY galvo (ZJ15K type), laser tube.
// Parametric OpenSCAD model, no screws: everything press-fits, snaps or is held by friction.
// Open in OpenSCAD and use Window > Customizer to change values. Units: mm, angles: degrees.
//
// Head frame (everything is built in it; the feet then tilt it up by `pitch`):
//   X = right, seen from behind the head looking where the beam leaves the galvo
//   Y = forward = direction of the beam leaving the galvo
//   Z = up, Z = 0 is the print bed / underside of the head
//   X = Y = 0 sits under the centre of the lower (X) galvo mirror, which is
//   also where the beam leaves the upper mirror, i.e. the middle of the system.
//
// Parts to print (export each with `part`):
//   head        frame with camera pockets, galvo seat and the two laser sockets
//   slider      laser clip on a blade that slides in a sprung socket, print 2
//   foot_left, foot_right   wedges that tilt the head up by `pitch`, pegged in
//   test_*      small pieces to check fits before printing the head

/* [Render] */
// What to show or export
part = "assembly"; // [assembly, head, slider, foot_left, foot_right, test_camera, test_galvo, test_socket]
// Show the camera fields of view and the galvo scan cone in the assembly
show_fov = true;
// Show dummy cameras, galvo and laser in the assembly
show_hardware = true;

/* [Layout] */
// Lens centre to lens centre
cam_spacing = 165; // [150:1:180]
// Each camera turned inward
toe_in = 3.3; // [0:0.1:10]
// Upward tilt of the whole head, set by the feet
pitch = 15; // [0:1:30]
// Y of the camera front face (lens plane)
cam_front_y = 30;
// Height of the lens centre above the head's underside
cam_lens_z = 32;

/* [Camera module SEN0634 / OV9281-79] */
pcb_w = 25;
pcb_h = 24;
pcb_t = 1.0;
// Lens centre from the PCB edge opposite the connector (the connector points up)
lens_from_edge = 8.35;
// Mounting hole spacing across the board (the holes are only used as standoff spots)
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
cam_wall = 2.0;
cam_floor_t = 1.6;
// Total clearance across the PCB width
pcb_clear = 0.4;
// Crush rib interference per side; raise if the cameras sit too loose
pcb_rib_interf = 0.15;
// Crush rib heights relative to the lens centre
cam_rib_z = [-3, 9];
// Extra size of the lens window
lens_clear = 0.8;
// Depth of the camera side walls at their foot (bracing)
cam_shelf = 12;

/* [Galvo (seen from behind: X motor sticks out backward, Y motor to the right)] */
// Bracket footprint, left-right
galvo_w = 33;
// Bracket footprint, back-front
galvo_d = 33;
// Lower mirror centre from the bracket's left face (only sets the laser's distance, not its aim)
mirror_x = 11.5;
// Thickness of the bracket part the X motor is clamped in, back face to shaft exit (estimated)
galvo_col_t = 11;
// Lower mirror centre from the face where the X motor shaft comes out (measured)
mirror_from_col = 15;
// Lower mirror centre above the bracket's bottom
mirror_h = 17.5;
// Upper mirror height above the bracket's bottom (preview and clearance only)
upper_mirror_h = 28;
// Height of the galvo's underside above the head's underside
galvo_floor = 14;
galvo_clear = 0.5;
galvo_wall = 2.0;
// Locating lip above the galvo's underside
lip_h = 4;
// Width of the ledge the galvo rests on
ledge_w = 3;
galvo_rib_interf = 0.15;
// Crush rib positions along each wall, from the bracket's left-back corner
rib_left = [5];
rib_right = [8, 24];
rib_back = [5, 28];
rib_front = [27];

/* [Laser and sliders] */
laser_d = 16.5;
laser_len = 107;
// Beam hole centre from the tube's outer surface
laser_hole_from_edge = 4;
// Where the beam hole points, seen from the laser front: 90 = up, 270 = down, 0 = forward
laser_hole_angle = 90; // [0:15:345]
// Gap between galvo seat and laser front
laser_gap = 5;
// Clip positions, measured from the laser front (clear bands: 0-13, 20-40, 88-107)
clip_pos = [30, 97];
// Clip grips the tube this much under its diameter
clip_interf = 0.2;
clip_wall = 2.2;
// Half-angle of the clip opening at the top; smaller holds tighter but snaps harder
clip_open = 64; // [45:1:70]
// Blade thickness = clip width (along the laser)
blade_t = 4;
blade_w = 14;
// Adjustment travel of each slider, up/down and forward/back
adjust = 3;
// Sprung socket: leaf thickness, gap to the blade, preload
leaf_t = 1.2;
leaf_gap = 0.5;
preload = 0.3;
sock_wall_t = 3;
pad_t = 2;

/* [Frame] */
front_rail_h = 10;
rail_w = 10;
rail_h = 8;
// X positions of the two spines that carry the feet
spine_x = [-82.5, 10];

/* [Feet] */
foot_t = 8;
// Height of the head's lowest back corner above the table
foot_min_h = 4;
peg_d = 5;
peg_h = 5;
peg_clear = 0.3;
peg_rib_interf = 0.12;
// Peg positions (head frame Y) on the left and right spine
peg_y_left = [-16, 24];
peg_y_right = [-22, 24];

/* [Hidden] */
$fn = 64;
eps = 0.01;

// ---------- derived values ----------
c_g = galvo_clear / 2;
mirror_y = galvo_col_t + mirror_from_col;   // lower mirror centre from the bracket's back face
gx0 = -mirror_x;               // bracket left face
gy0 = -mirror_y;               // bracket back face
ix0 = gx0 - c_g; iy0 = gy0 - c_g;
ix1 = gx0 + galvo_w + c_g; iy1 = gy0 + galvo_d + c_g;
beam_z = galvo_floor + mirror_h;
up_z = galvo_floor + upper_mirror_h;
hole_off = laser_d / 2 - laser_hole_from_edge;
axis_y = -hole_off * cos(laser_hole_angle);
axis_z = beam_z - hole_off * sin(laser_hole_angle);
laser_front_x = ix0 - galvo_wall - laser_gap;
clip_x = [for (d = clip_pos) laser_front_x - d];

R_ci = (laser_d - clip_interf) / 2;
R_co = R_ci + clip_wall;
clip_bot = axis_z - R_co;               // nominal underside of the clip ring
sock_top = clip_bot - adjust - 1;       // sockets stay clear of the clip at the lowest setting
blade_bot = pad_t + adjust;             // nominal blade bottom, can drop by `adjust` onto the pad
blade_len = clip_bot + 1 - blade_bot;
wall_hw = blade_w / 2 + adjust + 1;     // half-width of the socket's rigid wall
bump_z = sock_top - 1.2;

pw = pcb_w + pcb_clear;
pcb_front_y = -(cam_front_wall + comp_gap);
pcb_back_y = pcb_front_y - pcb_t;
pocket_back_y = pcb_back_y - 1.5;
cam_top_z = pcb_h - lens_from_edge;
cam_floor_z = -(lens_from_edge + pcb_clear / 2);
cam_half = pw / 2 + cam_wall;

fr_x = cam_spacing / 2 + cam_half * cos(toe_in) + cam_shelf * sin(toe_in) + 1;
fr_y0 = cam_front_y - cam_shelf - 1;
fr_y1 = cam_front_y + 1;
br_y = axis_y - wall_hw - rail_w / 2;   // back rail centre line
br_x0 = min(clip_x) - blade_t / 2 - 0.1 - sock_wall_t;
seat_y0 = iy0 - galvo_wall;
spine_y0 = [br_y - rail_w / 2, seat_y0];

head_min_y = min(br_y - rail_w / 2, seat_y0);
lift = foot_min_h - head_min_y * sin(pitch);

// ---------- checks ----------
assert(sock_top - pad_t >= 8, "sockets too short for a working leaf spring: raise galvo_floor");
assert(cam_lens_z + cam_floor_z - cam_floor_t > front_rail_h + 3, "cam_lens_z too low for the camera pocket");
assert(clip_pos[0] - blade_t / 2 >= 20 && clip_pos[0] + blade_t / 2 <= 40, "front clip outside the clear band 20-40");
assert(clip_pos[1] - blade_t / 2 >= 88 && clip_pos[1] + blade_t / 2 <= 107, "back clip outside the clear band 88-107");
assert(bump_z > blade_bot + adjust + 1 && bump_z < clip_bot + 1 - adjust - 1, "leaf bump not covered by the blade over the full travel");

cam_back_y = cam_front_y - cam_shelf * cos(toe_in) - cam_half * sin(toe_in);
echo(str("head X ", br_x0, " .. ", fr_x, " (", fr_x - br_x0, " mm), Y ", head_min_y, " .. ", fr_y1, " (", fr_y1 - head_min_y, " mm)"));
echo(str("beam height ", beam_z, ", laser axis Y ", axis_y, " Z ", axis_z, ", clips at X ", clip_x));
echo(str("gap laser tube surface -> left camera ", cam_back_y - (axis_y + laser_d / 2), " mm, tube underside ", axis_z - laser_d / 2));
echo(str("socket top ", sock_top, ", leaf free length ", sock_top - pad_t, ", blade length ", blade_len));

// ---------- helpers ----------
module head_to_world() {
    translate([0, 0, lift]) rotate([pitch, 0, 0]) children();
}

// box from corner a to corner b
module box(a, b) {
    translate(a) cube([b[0] - a[0], b[1] - a[1], b[2] - a[2]]);
}

// polygon in the (Y, Z) plane, extruded along X from x0 by t
module yz_extrude(x0, t, pts) {
    translate([x0, 0, 0]) rotate([90, 0, 90]) linear_extrude(t) polygon(pts);
}

// ---------- camera holder ----------
// Local frame: origin = lens centre on the front face, +y = optical axis, +z = up.
// Open at the back and top. The PCB is pushed in from behind against four standoffs at
// its mounting holes; crush ribs on the side walls hold it. The connector points up.
module camera_holder(leg = cam_lens_z - front_rail_h + 0.5) {
    zb = -leg;
    lw = lens_box + lens_clear;
    so = 3.2;
    difference() {
        translate([-cam_half, -cam_front_wall, zb]) cube([2 * cam_half, cam_front_wall, cam_top_z - zb]);
        translate([-lw / 2, -cam_front_wall - 1, -lw / 2]) cube([lw, cam_front_wall + 2, lw]);
        hull() {
            translate([-lw / 2 - 1.2, -eps, -lw / 2 - 1.2]) cube([lw + 2.4, 1, lw + 2.4]);
            translate([-lw / 2, -1.2, -lw / 2]) cube([lw, eps, lw]);
        }
    }
    // side walls, deeper at the foot for bracing
    for (s = [-1, 1])
        yz_extrude(s > 0 ? pw / 2 : -cam_half, cam_wall,
            [[0, zb], [-cam_shelf, zb], [pocket_back_y, cam_floor_z - 4], [pocket_back_y, cam_top_z], [0, cam_top_z]]);
    // pocket floor with a 45 degree underside, so it prints without bridging
    fd = -cam_front_wall - pocket_back_y;
    yz_extrude(-pw / 2 - eps, pw + 2 * eps,
        [[-cam_front_wall + eps, cam_floor_z], [pocket_back_y, cam_floor_z], [pocket_back_y, cam_floor_z - cam_floor_t],
         [-cam_front_wall + eps, cam_floor_z - cam_floor_t - fd]]);
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
// Hollow box. The galvo rests on a narrow ledge along the walls and is located by a
// low lip with crush ribs. No floor: the bracket only needs support at its edges.
module galvo_seat(floor_z = galvo_floor) {
    top = floor_z + lip_h;
    difference() {
        box([ix0 - galvo_wall, iy0 - galvo_wall, 0], [ix1 + galvo_wall, iy1 + galvo_wall, top]);
        box([ix0, iy0, -1], [ix1, iy1, top + 1]);
    }
    // ledge with a 45 degree underside
    difference() {
        box([ix0 - eps, iy0 - eps, floor_z - ledge_w], [ix1 + eps, iy1 + eps, floor_z]);
        hull() {
            box([ix0, iy0, floor_z - ledge_w - eps], [ix1, iy1, floor_z - ledge_w]);
            box([ix0 + ledge_w, iy0 + ledge_w, floor_z], [ix1 - ledge_w, iy1 - ledge_w, floor_z + eps]);
        }
    }
    p = c_g + galvo_rib_interf;
    rr = 0.8;
    module rib(x, y) translate([x, y, floor_z - eps]) cylinder(r = rr, h = lip_h, $fn = 16);
    for (v = rib_left) rib(ix0 - rr + p, gy0 + v);
    for (v = rib_right) rib(ix1 + rr - p, gy0 + v);
    for (u = rib_back) rib(gx0 + u, iy0 - rr + p);
    for (u = rib_front) rib(gx0 + u, iy1 + rr - p);
}

// ---------- laser socket and slider ----------
// Local frame of a socket: origin on the bed under the slider's mid-plane, +x along the laser.
// The blade is pressed against the rigid wall (-x) by a leaf spring (+x). Friction holds it
// anywhere within +-adjust up/down and forward/back. Slide by hand, then leave it.
module socket() {
    xw = -blade_t / 2 - 0.1;                    // rigid wall face
    xl = blade_t / 2 + leaf_gap;                // leaf inner face
    box([xw - sock_wall_t, -wall_hw, 0], [xw, wall_hw, sock_top]);
    box([xw - sock_wall_t, -wall_hw, 0], [xl + leaf_t, wall_hw, pad_t]);
    box([xl, -blade_w / 2, pad_t - eps], [xl + leaf_t, blade_w / 2, sock_top]);
    // contact bump on the leaf
    rb = 1;
    tip = xw + blade_t - preload;
    // its underside runs steeply down into the leaf, so it prints without support
    hull() {
        intersection() {
            translate([tip + rb, 0, bump_z]) rotate([90, 0, 0]) cylinder(r = rb, h = blade_w, center = true, $fn = 24);
            box([tip - 1, -blade_w / 2, bump_z - rb], [xl + eps, blade_w / 2, bump_z + rb]);
        }
        box([xl - eps, -blade_w / 2, bump_z - 2 * rb], [xl + eps, blade_w / 2, bump_z]);
    }
}

// Slider in its use position: origin = tube axis, +x along the laser.
// Print it flat on its -x face (part "slider" does that).
module slider() {
    module ring2d() difference() {
        circle(r = R_co);
        circle(r = R_ci);
        polygon([[0, 0], [2 * R_co * sin(clip_open), 2 * R_co * cos(clip_open)], [0, 2 * R_co],
                 [-2 * R_co * sin(clip_open), 2 * R_co * cos(clip_open)]]);
    }
    // round the clip tips so the tube snaps in easily
    module clip2d() {
        ring2d();
        for (s = [-1, 1]) translate([s * (R_ci + clip_wall / 2) * sin(clip_open), (R_ci + clip_wall / 2) * cos(clip_open)])
            circle(d = clip_wall);
    }
    rotate([90, 0, 90]) translate([0, 0, -blade_t / 2]) linear_extrude(blade_t) {
        clip2d();
        // blade with a chamfered lower end as lead-in past the leaf bump
        bz0 = blade_bot - axis_z;
        polygon([[-blade_w / 2, bz0 + 1], [-blade_w / 2 + 1, bz0], [blade_w / 2 - 1, bz0], [blade_w / 2, bz0 + 1],
                 [blade_w / 2, -R_co + 1], [-blade_w / 2, -R_co + 1]]);
    }
}

module at_clip(i) translate([clip_x[i], axis_y, 0]) children();

// ---------- frame ----------
module frame() {
    // front rail: carries both cameras, the stereo baseline
    box([-fr_x, fr_y0, 0], [fr_x, fr_y1, front_rail_h]);
    // back rail: laser sockets to galvo seat
    box([br_x0, br_y - rail_w / 2, 0], [ix0 - galvo_wall + 0.5, br_y + rail_w / 2 + 0.5, rail_h]);
    // spines from back to front, these carry the feet
    for (i = [0, 1]) box([spine_x[i] - rail_w / 2, spine_y0[i], 0], [spine_x[i] + rail_w / 2, fr_y0 + 0.5, rail_h]);
}

module peg_holes() {
    for (i = [0, 1], py = (i == 0 ? peg_y_left : peg_y_right))
        translate([spine_x[i], py, -1]) cylinder(d = peg_d + peg_clear, h = peg_h + 1.5, $fn = 32);
}

module peg_ribs() {
    rr = 0.5;
    off = (peg_d + peg_clear) / 2 + rr - (peg_clear / 2 + peg_rib_interf);
    for (i = [0, 1], py = (i == 0 ? peg_y_left : peg_y_right), a = [90, 210, 330])
        translate([spine_x[i] + off * cos(a), py + off * sin(a), 0]) cylinder(r = rr, h = peg_h + 0.5, $fn = 12);
}

module head() {
    difference() {
        union() {
            frame();
            for (s = [-1, 1]) at_cam(s) camera_holder();
            galvo_seat();
            for (i = [0, 1]) at_clip(i) socket();
        }
        peg_holes();
    }
    peg_ribs();
}

// ---------- feet ----------
function hw(y) = [y * cos(pitch), y * sin(pitch) + lift];   // head underside point -> world (Y, Z)

module foot(i) {
    pys = i == 0 ? peg_y_left : peg_y_right;
    y0 = spine_y0[i] + 0.5;
    y1 = fr_y1 - 1;
    b = hw(y0); f = hw(y1);
    outline = [[b[0], 0], [f[0], 0], f, b];
    t0 = spine_x[i] - foot_t / 2;
    // Solid wedge, no lightening window: at 8 mm thickness the slicer's sparse infill
    // already makes it light, and a window would need bridging under its sloped top.
    yz_extrude(t0, foot_t, outline);
    head_to_world() for (py = pys) translate([spine_x[i], py, -1]) {
        cylinder(d = peg_d, h = peg_h - 0.6 + 1, $fn = 32);
        translate([0, 0, peg_h - 0.6 + 1 - eps]) cylinder(d1 = peg_d, d2 = peg_d - 1.2, h = 0.6, $fn = 32);
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
    color([0.15, 0.15, 0.15]) translate([gx0, gy0, galvo_floor]) {
        cube([galvo_w, galvo_col_t, 40]);
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

module sliders_in_place() {
    for (i = [0, 1]) at_clip(i) translate([0, 0, axis_z]) slider();
}

module assembly() {
    color("gainsboro") for (i = [0, 1]) foot(i);
    head_to_world() {
        color("orange") head();
        color("gold") sliders_in_place();
        if (show_hardware) {
            for (s = [-1, 1]) at_cam(s) dummy_camera();
            dummy_galvo();
            dummy_laser();
        }
        if (show_fov) fovs();
    }
}

// ---------- print orientations and test pieces ----------
module slider_print() {
    translate([0, 0, blade_t / 2]) rotate([0, -90, 0]) slider();
}

module foot_print(i) {
    translate([-spine_x[i], 0, 0]) foot(i);
}

module test_camera() {
    camera_holder(leg = lens_from_edge + cam_floor_t + 7);
}

module test_galvo() {
    translate([-ix0 + galvo_wall, -iy0 + galvo_wall, 0]) galvo_seat(floor_z = ledge_w + 1);
}

module test_socket() {
    socket();
    translate([0, 30, 0]) slider_print();
}

// ---------- output ----------
if (part == "assembly") assembly();
else if (part == "head") head();
else if (part == "slider") slider_print();
else if (part == "foot_left") foot_print(0);
else if (part == "foot_right") foot_print(1);
else if (part == "test_camera") test_camera();
else if (part == "test_galvo") test_galvo();
else if (part == "test_socket") test_socket();
