# Check that roi.set_window() returns exactly the requested pixels:
# stream full frames, switch to the window mid-stream, then search the last full frame
# for the offset that best matches the first cropped frames.
# usage: verify_roi.py x0 x1 y0 y1
import subprocess, time, re, sys
import roi

x0, x1, y0, y1 = map(int, sys.argv[1:5])
S, W, F = "/dev/v4l-subdev0", 1280, 1280 * 800


def sh(*a):
    subprocess.run(a, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


sh("v4l2-ctl", "-d", S, "--set-subdev-fmt", "pad=0,width=1280,height=800,code=0x2001")
sh("v4l2-ctl", "-d", "/dev/video0", "--set-fmt-video=width=1280,height=800,pixelformat=GREY")
sh("v4l2-ctl", "-d", S, "-c", "horizontal_blanking=250,vertical_blanking=110,exposure=800,analogue_gain=255")
cap = subprocess.Popen(["v4l2-ctl", "-d", "/dev/video0", "--stream-mmap=4", "--stream-count=60",
                        "--stream-to=v.raw", "--verbose"], stdout=open("v.txt", "w"), stderr=subprocess.STDOUT)
while open("v.txt").read().count("seq:") < 8:  # sensor is powered only while streaming
    time.sleep(0.05)
t_set = time.monotonic() * 1e3
req = (x0, x1)
x0, x1, y0, y1 = roi.set_window(x0, x1, y0, y1, vts=910)  # keep frame length so exposure stays identical
w, h = x1 - x0, y1 - y0
try:
    cap.wait(timeout=10)
except subprocess.TimeoutExpired:
    cap.kill()
    print(f"x {x0}-{x1} y {y0}-{y1} ({w}x{h}): STREAM HUNG after applying the window")
    sys.exit(1)

ts = [float(m.group(1)) * 1e3 for l in open("v.txt") for m in [re.search(r"ts: ([\d.]+)", l)] if m]
raw = open("v.raw", "rb").read()
frames = [raw[i * F:(i + 1) * F] for i in range(len(raw) // F)]
# average up to 5 frames on each side of the switch to beat sensor noise
# (frame-start timestamps, so stay a frame clear of the switch on both sides)
fulls = [frames[i] for i, t in enumerate(ts) if t < t_set - 10][-5:]
crops = [frames[i] for i, t in enumerate(ts) if t > t_set + 30][:5]
R = 10  # search radius in pixels


def avg(fs, x, y, ww, hh):
    return [[sum(f[(y + r) * W + x + c] for f in fs) / len(fs) for c in range(ww)] for r in range(hh)]


crop = avg(crops, 0, 0, w, h)
fx0, fy0 = max(x0 - R, 0), max(y0 - R, 0)
fx1, fy1 = min(x1 + R, 1280), min(y1 + R, 800)
full = avg(fulls, fx0, fy0, fx1 - fx0, fy1 - fy0)


def mad(dx, dy):
    if not (fx0 <= x0 + dx and x1 + dx <= fx1 and fy0 <= y0 + dy and y1 + dy <= fy1):
        return None
    s = n = 0
    for r in range(h):
        fr = full[y0 + dy - fy0 + r]
        ox = x0 + dx - fx0
        for c in range(0, w, 2):
            s += abs(crop[r][c] - fr[ox + c]); n += 1
    return s / n


scores = sorted((m, dx, dy) for dx in range(-R, R + 1) for dy in range(-R, R + 1)
                for m in [mad(dx, dy)] if m is not None)
best = scores[0]
mean_crop = sum(map(sum, crop)) / (w * h)
mean_ref = sum(sum(full[y0 - fy0 + r][x0 - fx0:x0 - fx0 + w]) for r in range(h)) / (w * h)
print(f"req x {req[0]}-{req[1]} -> x {x0}-{x1} y {y0}-{y1} ({w}x{h}, {len(fulls)}+{len(crops)} frames): best dx={best[1]} dy={best[2]} "
      f"mad={best[0]:.2f} (at 0,0: {mad(0, 0):.2f}, 2nd best {scores[1][0]:.2f} at {scores[1][1]},{scores[1][2]}); "
      f"mean crop {mean_crop:.1f} ref {mean_ref:.1f}")
