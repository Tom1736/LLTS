# Stream 1280x800, then shrink the sensor's vertical window on the fly via I2C.
# usage: crop.py H y0 vts [frames] [hold]
import subprocess, time, re, sys, ovreg
H, y0, vts = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
N = int(sys.argv[4]) if len(sys.argv) > 4 else 1500
S = "/dev/v4l-subdev0"
LINE = 0.0079675  # ms, R8 with HTS 1530


def sh(*a):
    subprocess.run(a, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


sh("v4l2-ctl", "-d", S, "--set-subdev-fmt", "pad=0,width=1280,height=800,code=0x2001")
sh("v4l2-ctl", "-d", "/dev/video0", "--set-fmt-video=width=1280,height=800,pixelformat=GREY")
sh("v4l2-ctl", "-d", S, "-c", "horizontal_blanking=250,vertical_blanking=110,exposure=20")
cap = subprocess.Popen(["v4l2-ctl", "-d", "/dev/video0", "--stream-mmap=4", f"--stream-count={N}", "--verbose"],
                       stdout=open("crop.txt", "w"), stderr=subprocess.STDOUT)
time.sleep(0.6)
t0 = time.monotonic() * 1e3
ovreg.wr(0x3802, y0, 2)
ovreg.wr(0x3806, y0 + H + 15, 2)
ovreg.wr(0x380a, H, 2)
ovreg.wr(0x380e, vts, 2)
t1 = time.monotonic() * 1e3
try:
    cap.wait(timeout=15)
except subprocess.TimeoutExpired:
    cap.kill()
    print("CAPTURE HUNG")

s, t, by = [], [], set()
for l in open("crop.txt"):
    m = re.search(r"seq:\s+(\d+) bytesused: (\d+) ts: ([\d.]+)", l)
    if m:
        s.append(int(m.group(1))); by.add(int(m.group(2))); t.append(float(m.group(3)) * 1e3)
i = next((j for j in range(len(t)) if t[j] > t1), len(t))


def iv(a, b):
    return (t[b] - t[a]) / (s[b] - s[a]) if b - a > 2 else float("nan")


gaps = sum(b - a - 1 for a, b in zip(s[i + 3:], s[i + 4:]))
pre, post = iv(0, i - 1), iv(i + 3, len(t) - 1)
print(f"H={H} y0={y0} vts={vts}: writes {t1 - t0:.2f}ms frames={len(s)} bytesused={sorted(by)}")
print(f"  before {pre:.4f}ms ({1000 / pre:.1f}fps)  after {post:.4f}ms ({1000 / post:.1f}fps)  "
      f"lines={post / LINE:.1f} gaps_after={gaps}")
print("  transition:", " ".join(f"{t[j + 1] - t[j]:.3f}" for j in range(max(i - 2, 0), min(i + 4, len(t) - 1))))
