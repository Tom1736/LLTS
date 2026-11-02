# Stream 1280x800, then set an X/Y window and HTS/VTS on the fly via I2C.
# usage: crop_xy.py Wd H hts_reg vts [frames]   (hts_reg in sensor units of 2 pixels)
import subprocess, time, re, sys, ovreg
Wd, H, hts, vts = map(int, sys.argv[1:5])
N = int(sys.argv[5]) if len(sys.argv) > 5 else 3000
S = "/dev/v4l-subdev0"
x0, y0 = 640 - Wd // 2, 400 - H // 2


def sh(*a):
    subprocess.run(a, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


sh("v4l2-ctl", "-d", S, "--set-subdev-fmt", "pad=0,width=1280,height=800,code=0x2001")
sh("v4l2-ctl", "-d", "/dev/video0", "--set-fmt-video=width=1280,height=800,pixelformat=GREY")
sh("v4l2-ctl", "-d", S, "-c", "horizontal_blanking=250,vertical_blanking=110,exposure=20")
cap = subprocess.Popen(["v4l2-ctl", "-d", "/dev/video0", "--stream-mmap=4", f"--stream-count={N}", "--verbose"],
                       stdout=open("cropxy.txt", "w"), stderr=subprocess.STDOUT)
time.sleep(0.6)
t1 = time.monotonic() * 1e3
ovreg.wr(0x3800, x0, 2); ovreg.wr(0x3804, x0 + Wd + 15, 2); ovreg.wr(0x3808, Wd, 2)
ovreg.wr(0x3802, y0, 2); ovreg.wr(0x3806, y0 + H + 15, 2); ovreg.wr(0x380a, H, 2)
ovreg.wr(0x380c, hts, 2); ovreg.wr(0x380e, vts, 2)
try:
    cap.wait(timeout=15)
except subprocess.TimeoutExpired:
    cap.kill()
    print(f"W={Wd} H={H} hts={hts} vts={vts}: CAPTURE HUNG")
    sys.exit()
s, t = [], []
for l in open("cropxy.txt"):
    m = re.search(r"seq:\s+(\d+) bytesused: (\d+) ts: ([\d.]+)", l)
    if m:
        s.append(int(m.group(1))); t.append(float(m.group(3)) * 1e3)
i = next((j for j in range(len(t)) if t[j] > t1), len(t)) + 3
iv = (t[-1] - t[i]) / (s[-1] - s[i])
gaps = sum(b - a - 1 for a, b in zip(s[i:], s[i + 1:]))
print(f"W={Wd} H={H} hts={hts} ({2 * hts}px) vts={vts}: {iv:.4f}ms {1000 / iv:.1f}fps "
      f"line={iv / vts * 1000:.3f}us gaps={gaps}/{len(s) - i}")
