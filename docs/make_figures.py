# Renders the figures in docs/images/ that the README shows.
# Reads data that stays out of git (recordings/, tools/sync/results/) plus calib/.
# usage: python3 docs/make_figures.py   (from the repo root; needs numpy, matplotlib, pillow)
import csv, json, os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from PIL import Image, ImageDraw

OUT = "docs/images"
SURF, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3de"
BLUE, ORANGE, AQUA, YELLOW, MAGENTA = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"
LINE_US = 1530 / 192.0  # one sensor line in 8-bit mode, µs

plt.rcParams.update({
    "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "text.color": INK, "font.size": 10, "axes.titlesize": 11, "axes.titleweight": "bold",
    "axes.titlelocation": "left", "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True,
    "legend.frameon": False,
})


def save(fig, name):
    fig.savefig(f"{OUT}/{name}", dpi=160, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)
    print(name)


# 1. Throw test, 250 fps: every 3rd raw frame (12 ms apart) overlaid on the empty scene, plus the
#    centroid the current track.c finds in every frame. replay.csv comes from `track -p <rec_dir>`.
d = "recordings/rec_20261102_221531"
fr = np.fromfile(f"{d}/frames.raw", np.uint8).reshape(-1, 400, 640).astype(np.int16)
rp = list(csv.DictReader(open(f"{d}/replay.csv")))
tx = np.array([float(r["cx"]) for r in rp])
ty = np.array([float(r["cy"]) for r in rp])
seen = np.where(~np.isnan(tx))[0]
bg = np.median(fr[200::4], axis=0)
comp = bg.copy()
for i in range(seen[0], seen[-1] + 1, 3):
    m = fr[i] < bg - 35
    comp[m] = np.minimum(comp[m], fr[i][m])
fig = plt.figure(figsize=(6.4, 4))
ax = fig.add_axes([0, 0, 1, 1])
ax.imshow(comp, cmap="gray", vmin=0, vmax=255)
ax.plot(tx[seen], ty[seen], "-", color=ORANGE, lw=1.2)
ax.plot(tx[seen], ty[seen], "o", color=ORANGE, ms=2.5)
ax.axis("off")
fig.savefig(f"{OUT}/throw-tracked.png", dpi=150)
plt.close(fig)
print("throw-tracked.png")

# Same throw as an animation, slowed down 10x, with the tracker's crosshair and trail.
gif = []
for i in range(max(seen[0] - 5, 0), min(seen[-1] + 6, len(fr))):
    im = Image.fromarray(fr[i].clip(0, 255).astype(np.uint8)).convert("RGB")
    dr = ImageDraw.Draw(im)
    trail = [(tx[j], ty[j]) for j in seen if j <= i]
    if len(trail) > 1:
        dr.line(trail, fill=ORANGE, width=2)
    if i in seen:
        x, y = tx[i], ty[i]
        dr.line((x - 14, y, x + 14, y), fill=ORANGE, width=2)
        dr.line((x, y - 14, x, y + 14), fill=ORANGE, width=2)
    dr.text((8, 6), f"frame {i - seen[0]:+d}   t = {(i - seen[0]) * 4:+d} ms   (250 fps, 10x slower)", fill="white")
    gif.append(im.resize((400, 250), Image.LANCZOS).quantize(24))
gif[0].save(f"{OUT}/throw-tracked.gif", save_all=True, append_images=gif[1:], duration=40, loop=0)
print("throw-tracked.gif")

# 2. Frame rate vs. rows read (sensor crop, vblank 56). Measured points, formula as a line.
meas = [(16, 1719.1), (64, 1037.9), (128, 678.7), (200, 488.5), (800, 146.4)]
rows = np.arange(16, 801)
fig, ax = plt.subplots(figsize=(6.4, 3.4))
ax.plot(rows, 1e6 / ((rows + 57) * LINE_US), color=BLUE, lw=2, label="frame = (rows + 57) lines")
ax.plot(*zip(*meas), "o", ms=8, color=BLUE, mec=SURF, mew=2, label="measured")
for r, f in meas:
    ax.annotate(f"{f:.0f} fps", (r, f), xytext=(8, 4), textcoords="offset points", color=INK, fontsize=9)
ax.set_xscale("log")
ax.set_xticks([16, 32, 64, 128, 200, 400, 800], ["16", "32", "64", "128", "200", "400", "800"])
ax.minorticks_off()
ax.set_xlabel("rows read from the sensor (window height)")
ax.set_ylabel("frames per second")
ax.set_title("OV9281 frame rate with the sensor window cropped over I2C")
ax.legend(loc="upper right")
save(fig, "fps-vs-rows.png")

# 3. Frame sync: phase error per frame (locked run) and camera B − A offset per flash (locked vs. free-run).
fig, (a1, a2) = plt.subplots(1, 2, figsize=(9.6, 3.4), gridspec_kw={"width_ratios": [2.2, 1]})
run = "tools/sync/results/flash_20261103_221007"
for host, name, col in [("pi3", "Pi 3B", BLUE), ("zero", "Pi Zero W", ORANGE)]:
    r = list(csv.DictReader(open(f"{run}/{host}/frames.csv")))
    t = (np.array([int(x["ts_ns"]) for x in r]) - int(r[0]["ts_ns"])) / 1e9
    e = np.array([float(x["e_us"]) for x in r])
    ok = np.array([x["locked"] == "1" for x in r])
    inside = 100 * np.mean(np.abs(e[ok]) <= LINE_US)
    a1.plot(t[ok], e[ok], ".", ms=2.5, color=col, alpha=0.7,
            label=f"{name}: sd {np.std(e[ok]):.1f} µs, {inside:.0f} % within one line")
a1.axhspan(-LINE_US, LINE_US, color=GRID, alpha=0.6, lw=0)
a1.set_ylim(-26, 26)
a1.set_xlabel("time (s)")
a1.set_ylabel("frame start − target (µs)")
a1.set_title("Phase error per frame, 100 fps (grey band: ± one sensor line, 8 µs)")
a1.legend(loc="lower right", markerscale=4, fontsize=8.5)

offs = {}
for label, path in [("free-run", "tools/sync/results/flash_20261103_221115"), ("locked", run)]:
    vals = []
    for line in open(f"{path}/result.txt"):
        p = line.split()
        if p and p[0] in ("rise", "fall") and p[-1].endswith("us"):
            vals.append(float(p[-1][:-2]))
    offs[label] = np.array(vals)
rng = np.random.default_rng(0)
for i, (label, v) in enumerate(offs.items()):
    a2.plot(i + rng.uniform(-0.12, 0.12, len(v)), v, "o", ms=4, color=[INK2, BLUE][i], alpha=0.6, mew=0)
    a2.annotate(f"{np.mean(v):+.0f} µs", (i, np.mean(v)), xytext=(0, 14 if i else -18),
                textcoords="offset points", ha="center", color=INK, fontsize=9)
a2.set_xticks([0, 1], list(offs))
a2.set_xlim(-0.6, 1.6)
a2.set_ylim(-600, 100)
a2.grid(axis="x", visible=False)
a2.set_ylabel("camera B − camera A (µs)")
a2.set_title("Offset between the cameras")
fig.tight_layout(w_pad=3)
save(fig, "frame-sync.png")

# 4. Latency on the camera node: end of exposure to detection packet sent (128-row window, 678 fps).
steps = [("readout", 1.02, BLUE), ("dequeue", 0.26, ORANGE), ("copy window", 0.25, AQUA),
         ("threshold + centroid", 0.15, YELLOW), ("UART packet", 0.16, MAGENTA)]
fig, ax = plt.subplots(figsize=(9.6, 1.6))
x = 0
for i, (name, ms, col) in enumerate(steps):
    ax.barh(0, ms, left=x, height=0.5, color=col, edgecolor=SURF, linewidth=2)
    below = i % 2 == 1
    ax.annotate(f"{name}\n{ms:.2f} ms", (x + ms / 2, -0.25 if below else 0.25),
                xytext=(0, -6 if below else 6), textcoords="offset points",
                ha="center", va="top" if below else "bottom", fontsize=8.5, color=INK)
    x += ms
ax.set_xlim(0, 1.95)
ax.set_ylim(-1, 1)
ax.set_yticks([])
ax.grid(axis="y", visible=False)
ax.spines["left"].set_visible(False)
ax.set_xlabel("ms after end of exposure")
ax.set_title(f"Camera node latency: {x:.2f} ms from exposure to detection on the wire")
save(fig, "latency-chain.png")

# 5. Calibration: 12 of the 60 views with the detected checkerboard corners.
cdir = "calib/zero-2026-11-02"
tw, th, gap = 320, 200, 6
sheet = Image.new("RGB", (4 * tw + 3 * gap, 3 * th + 2 * gap), SURF)
for k, n in enumerate([15, 21, 26, 29, 30, 31, 34, 37, 40, 45, 47, 57]):
    im = Image.open(f"{cdir}/img_{n:03d}.jpg").convert("RGB").resize((tw, th))
    dr = ImageDraw.Draw(im)
    for u, v in json.load(open(f"{cdir}/img_{n:03d}.json"))["corners"]:
        u, v = u * tw / 1280, v * th / 800
        dr.ellipse((u - 1.6, v - 1.6, u + 1.6, v + 1.6), fill=ORANGE)
    sheet.paste(im, ((k % 4) * (tw + gap), (k // 4) * (th + gap)))
sheet.save(f"{OUT}/calibration-views.jpg", quality=88)
print("calibration-views.jpg")

# 6. Lens distortion of the Zero camera: how far each pixel sits from its undistorted position.
c = json.load(open(f"{cdir}/calibration.json"))
K, (k1, k2, p1, p2, k3) = np.array(c["K"]), c["dist"]
fx, fy, cx, cy = K[0, 0], K[1, 1], K[0, 2], K[1, 2]
u, v = np.meshgrid(np.arange(1280) + 0.5, np.arange(800) + 0.5)
xd, yd = (u - cx) / fx, (v - cy) / fy
x, y = xd.copy(), yd.copy()
for _ in range(20):  # invert the distortion model by fixed-point iteration
    r2 = x * x + y * y
    rad = 1 + k1 * r2 + k2 * r2 ** 2 + k3 * r2 ** 3
    x = (xd - (2 * p1 * x * y + p2 * (r2 + 2 * x * x))) / rad
    y = (yd - (p1 * (r2 + 2 * y * y) + 2 * p2 * x * y)) / rad
shift = np.hypot((x - xd) * fx, (y - yd) * fy)
cmap = LinearSegmentedColormap.from_list("blues", ["#f1f6fd", "#9cc2ef", BLUE, "#123f7a"])
fig, ax = plt.subplots(figsize=(6.4, 4.3))
im = ax.imshow(shift, cmap=cmap, extent=(0, 1280, 800, 0))
cs = ax.contour(u, v, shift, levels=[1, 5, 10, 15], colors=INK, linewidths=0.7)
ax.clabel(cs, fmt="%d px", fontsize=8)
ax.grid(False)
ax.set_xlabel("x (px)")
ax.set_ylabel("y (px)")
ax.set_title(f"Lens distortion, Pi Zero camera: mean {shift.mean():.1f} px, up to {shift.max():.0f} px")
fig.colorbar(im, ax=ax, shrink=0.8, label="shift to undistorted position (px)")
save(fig, "distortion-map.png")
