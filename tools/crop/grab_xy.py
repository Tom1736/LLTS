# Grab one full 1280x800 frame, then one cropped frame (x0,y0,Wd,H), and save both as PGM.
# usage: grab_xy.py x0 y0 Wd H
import subprocess, time, sys, ovreg
x0, y0, Wd, H = map(int, sys.argv[1:5])
S = "/dev/v4l-subdev0"


def sh(*a):
    subprocess.run(a, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


sh("v4l2-ctl", "-d", S, "--set-subdev-fmt", "pad=0,width=1280,height=800,code=0x2001")
sh("v4l2-ctl", "-d", "/dev/video0", "--set-fmt-video=width=1280,height=800,pixelformat=GREY")
sh("v4l2-ctl", "-d", S, "-c", "horizontal_blanking=250,vertical_blanking=110,exposure=800,analogue_gain=255")
sh("v4l2-ctl", "-d", "/dev/video0", "--stream-mmap=3", "--stream-count=5", "--stream-to=full_ref.raw")
cap = subprocess.Popen(["v4l2-ctl", "-d", "/dev/video0", "--stream-mmap=3", "--stream-count=200", "--stream-to=xy.raw"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(0.6)
ovreg.wr(0x3800, x0, 2); ovreg.wr(0x3804, x0 + Wd + 15, 2); ovreg.wr(0x3808, Wd, 2)
ovreg.wr(0x3802, y0, 2); ovreg.wr(0x3806, y0 + H + 15, 2); ovreg.wr(0x380a, H, 2)
cap.wait()
F = 1280 * 800
full = open("full_ref.raw", "rb").read()[-F:]
crop = open("xy.raw", "rb").read()[-F:]
open("full_ref.pgm", "wb").write(b"P5 1280 800 255\n" + full)
# show the first H rows of the cropped buffer at the driver stride (1280)
open("xy_stride.pgm", "wb").write(b"P5 1280 %d 255\n" % H + crop[:1280 * H])
# and the same bytes reinterpreted as packed Wd-wide lines
open("xy_packed.pgm", "wb").write(b"P5 %d %d 255\n" % (Wd, H) + crop[:Wd * H])
ref = bytes(b for r in range(y0, y0 + H) for b in full[r * 1280 + x0:r * 1280 + x0 + Wd])
open("xy_ref.pgm", "wb").write(b"P5 %d %d 255\n" % (Wd, H) + ref)
