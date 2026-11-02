# Set the OV9281 output window in output-pixel coordinates of the 1280x800 mode.
# The sensor must already be streaming the 1280x800 mode (STREAMON resets these registers).
# Half-open ranges: x0 <= x < x1, y0 <= y < y1.
# usage: roi.py x0 x1 y0 y1 [vts]   (default vts = rows + 56)
# Keep exposure <= vts - 30 lines.
import sys
import ovreg

# Lines. Unicam on the Pi 3 drops frames below ~32, but the sensor already delivers
# wrong pixel values below ~52-56 (frames still arrive on time), so 56 is the real floor.
VBLANK_MIN = 56


def set_window(x0, x1, y0, y1, vts=None):
    """Returns the window actually set as (x0, x1, y0, y1), widened so x edges are multiples
    of 8 and y edges are even."""
    assert 0 <= x0 < x1 <= 1280 and 0 <= y0 < y1 <= 800
    # Measured on the Pi 3 with the stock 1280x800 mode:
    # - the sensor aligns the X window to 8 px (with mirror on, the output's left edge follows
    #   X_END + 1 rounded down to 8), and odd widths hang the stream;
    # - an odd Y start in array coordinates shifts the output 1 px in x;
    # - widths below 120 return a flat grey frame.
    x0, x1 = x0 & ~7, (x1 + 7) & ~7
    y0, y1 = y0 & ~1, (y1 + 1) & ~1
    if x1 - x0 < 120:
        x0 = max(min(x0, 1280 - 120), 0); x1 = x0 + 120
    w, h = x1 - x0, y1 - y0
    # Window registers are in sensor-array coordinates; the driver's mode streams with
    # mirror (0x3821 bit 2) and flip (0x3820 bit 2) set, which reverses the output.
    ax = 1280 - x1 if ovreg.rd(0x3821) & 0x04 else x0
    ay = 800 - y1 if ovreg.rd(0x3820) & 0x04 else y0
    # The array window is 16 px larger than the output; the output starts 8 px in
    # (X_OFF/Y_OFF = 8), so window start == output start in these coordinates.
    ovreg.wr(0x3800, ax, 2); ovreg.wr(0x3804, ax + w + 15, 2); ovreg.wr(0x3808, w, 2)
    ovreg.wr(0x3802, ay, 2); ovreg.wr(0x3806, ay + h + 15, 2); ovreg.wr(0x380a, h, 2)
    ovreg.wr(0x380e, vts or h + VBLANK_MIN, 2)
    return x0, x1, y0, y1


if __name__ == "__main__":
    a = list(map(int, sys.argv[1:]))
    print("window x %d-%d y %d-%d" % set_window(*a))
