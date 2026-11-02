# Turn a track.c recording into an mp4 with the centroid marked (red cross), plus a summary.
# usage: view.py rec_dir [playback_fps]   (default 25 = 10x slow motion at 250 fps)
# needs numpy and ffmpeg
import csv, subprocess, sys
import numpy as np

d = sys.argv[1]
play = sys.argv[2] if len(sys.argv) > 2 else "25"
W, H = 640, 400
rows = list(csv.DictReader(open(f"{d}/track.csv")))
frames = np.fromfile(f"{d}/frames.raw", np.uint8).reshape(-1, H, W)

ts = np.array([int(r["ts_us"]) for r in rows])
seq = np.array([int(r["seq"]) for r in rows])
cx = np.array([float(r["cx"]) for r in rows])
cy = np.array([float(r["cy"]) for r in rows])
proc = np.array([int(r["proc_us"]) for r in rows])
found = ~np.isnan(cx)
print(f"{len(rows)} frames over {(ts[-1] - ts[0]) / 1e3:.1f} ms, {np.mean(np.diff(ts)):.1f} us/frame, "
      f"{int(np.sum(np.diff(seq) - 1))} dropped")
print(f"object found in {found.sum()} frames ({100 * found.mean():.1f}%), "
      f"x {np.nanmin(cx):.1f}-{np.nanmax(cx):.1f}, y {np.nanmin(cy):.1f}-{np.nanmax(cy):.1f}")
print(f"processing mean {proc.mean():.0f} us, max {proc.max()} us")

out = f"{d}/track.mp4"
ff = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                       "-s", f"{W}x{H}", "-r", play, "-i", "-", "-pix_fmt", "yuv420p", out],
                      stdin=subprocess.PIPE)
for f, x, y in zip(frames, cx, cy):
    rgb = np.repeat(f[:, :, None], 3, axis=2)
    if not np.isnan(x):
        xi, yi = int(round(x)), int(round(y))
        rgb[yi, max(xi - 10, 0):xi + 11] = (255, 0, 0)
        rgb[max(yi - 10, 0):yi + 11, xi] = (255, 0, 0)
    ff.stdin.write(rgb.tobytes())
ff.stdin.close()
ff.wait()
print("wrote", out)
