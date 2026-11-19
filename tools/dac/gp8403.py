"""DFRobot Gravity 2-channel I2C DAC (GP8403) with a hard output cap, plus a GPIO scope marker.

Two output ranges, chosen per GP8403 instance (range_volts):
  5  (default)  0-5 V. All galvo scripts use this; nothing changes for them.
  10            0-10 V, since the hardware upgrade of 2026-11-18. Only scripts that ask
                for it explicitly (dac_sine.py --range 10) get it.
Every output in this repo goes through this module, and these things keep it at or
below the cap of the range in use (MAX_VOLTS = 5 V, MAX_VOLTS_10V = 10 V):
  1. The range register is set to the instance's range before the first data write,
     then re-asserted every RANGE_REFRESH_S. Data is never written if the range wasn't
     confirmed (ACKed) within RANGE_MAX_AGE_S, which covers a DAC that reset itself and
     a DAC that another script left in the other range.
  2. Every voltage goes through volts_to_code(). It clamps to [0, cap], converts with the
     *measured* full-scale voltage of that range, and caps the code. Then it asserts.
  3. The caps are constants here, not command-line options.
  4. Scripts set the outputs back to 0 V on exit.
This is a software cap; the chip's real full scale has a tolerance. Measure the output at
code 4095 once per range and enter it as FULL_SCALE_VOLTS / FULL_SCALE_VOLTS_10V: if it
reads e.g. 5.06 V, the 5 V cap drops to code 4046.

Wiring (Gravity -> Pi 3B header): + pin 1 (3.3 V), - pin 6 (GND), C pin 5 (SCL), D pin 3 (SDA).
I2C bus 1 runs at 400 kHz on the 3B (dtparam=i2c_arm_baudrate=400000). Address 0x5F.
No Python packages needed: talks to /dev/i2c-1 and /dev/gpiomem directly.
"""
import fcntl
import os
import time

I2C_BUS = "/dev/i2c-1"
I2C_SLAVE = 0x0703          # ioctl: set target address
DEFAULT_ADDR = 0x5F         # as found on the Pi 3B; the module's range is 0x58-0x5F

REG_RANGE = 0x01            # output range register
RANGE_5V = 0x00             # register value for 0-5 V
RANGE_10V = 0x11            # register value for 0-10 V (only for range_volts=10)
REG_CH = {0: 0x02, 1: 0x04} # output data registers: channel 0 (X), channel 1 (Y)

MAX_VOLTS = 5.0             # cap in the 5 V range (galvo scripts). Do not raise.
FULL_SCALE_VOLTS = 5.0      # measured output at code 4095 in the 0-5 V range (nominal 5.0)
MAX_VOLTS_10V = 10.0        # cap in the 10 V range (hardware limit since 2026-11-18)
FULL_SCALE_VOLTS_10V = 10.0 # measured output at code 4095 in the 0-10 V range (nominal 10.0)
MAX_CODE = 4095             # 12-bit

RANGE_REFRESH_S = 0.1       # re-assert the range this often (call refresh_range() between edges)
RANGE_MAX_AGE_S = 0.25      # never write data if the range wasn't confirmed this recently


def _cap_code(max_volts, full_scale):
    return min(MAX_CODE, int(max_volts / full_scale * MAX_CODE))   # floor


# range_volts -> (register value, cap in V, measured full scale in V, highest allowed code)
RANGES = {
    5: (RANGE_5V, MAX_VOLTS, FULL_SCALE_VOLTS, _cap_code(MAX_VOLTS, FULL_SCALE_VOLTS)),
    10: (RANGE_10V, MAX_VOLTS_10V, FULL_SCALE_VOLTS_10V,
         _cap_code(MAX_VOLTS_10V, FULL_SCALE_VOLTS_10V)),
}
MAX_CODE_ALLOWED = RANGES[5][3]                 # 5 V range, used by the galvo scripts

assert MAX_VOLTS <= 5.0 and MAX_VOLTS_10V <= 10.0
for _reg, _cap, _fs, _code in RANGES.values():
    assert 0 < _cap and _fs > 0 and _code / MAX_CODE * _fs <= _cap + 1e-9


def volts_to_code(volts, range_volts=5):
    """Clamp to [0, cap of the range] and convert to a 12-bit code, capped for that range."""
    _, cap, fs, max_code = RANGES[range_volts]
    v = float(volts)
    if v != v:                                  # NaN never reaches the DAC
        v = 0.0
    v = min(max(v, 0.0), cap)
    code = int(round(v / fs * MAX_CODE))
    code = min(max(code, 0), max_code)
    assert 0 <= code <= max_code
    assert code / MAX_CODE * fs <= cap + 1e-9
    return code


def code_to_volts(code, range_volts=5):
    return code / MAX_CODE * RANGES[range_volts][2]


class GP8403:
    ATTEMPTS = 3                                # per register write; a lone NACK is retried

    def __init__(self, addr=DEFAULT_ADDR, range_volts=5):
        if range_volts not in RANGES:
            raise ValueError(f"range_volts must be one of {sorted(RANGES)}")
        self.range_volts = range_volts
        self.range_reg = RANGES[range_volts][0]
        self.fd = os.open(I2C_BUS, os.O_RDWR)
        fcntl.ioctl(self.fd, I2C_SLAVE, addr)
        self.retries = 0
        self.range_at = float("-inf")           # never confirmed yet: first write sets it

    def _write(self, payload):
        for attempt in range(self.ATTEMPTS):
            try:
                os.write(self.fd, payload)
                return
            except OSError:                     # Errno 121: no ACK (bus glitch)
                if attempt == self.ATTEMPTS - 1:
                    raise
                self.retries += 1

    def set_range(self):
        self._write(bytes([REG_RANGE, self.range_reg]))
        self.range_at = time.monotonic()

    set_range_5v = set_range                    # old name (all old scripts use range 5)

    def refresh_range(self):
        """Re-assert the range if the last time is RANGE_REFRESH_S ago. Cheap to call often."""
        if time.monotonic() - self.range_at >= RANGE_REFRESH_S:
            self.set_range()

    def _ensure_range(self):
        if time.monotonic() - self.range_at >= RANGE_MAX_AGE_S:
            self.set_range()                    # if this fails for good, no data is written

    @staticmethod
    def _data(code):
        return _code_bytes(code)

    def set_volts(self, volts, channels, combined=True):
        """Same voltage on the given channels. combined: both in one message (0x02, 4 bytes)."""
        code = volts_to_code(volts, self.range_volts)
        lo, hi = self._data(code)
        self._ensure_range()
        if combined and list(channels) == [0, 1]:
            self._write(bytes([REG_CH[0], lo, hi, lo, hi]))
        else:
            for ch in channels:
                self._write(bytes([REG_CH[ch], lo, hi]))
        return code

    def set_xy(self, vx, vy, combined=False):
        """Different voltages on channel 0 (X) and 1 (Y). Returns (code_x, code_y).

        combined=False writes two messages (one per channel), which works whether or not
        the chip auto-increments from 0x02 to 0x04. combined=True writes one message.
        """
        cx, cy = volts_to_code(vx, self.range_volts), volts_to_code(vy, self.range_volts)
        xl, xh = self._data(cx)
        yl, yh = self._data(cy)
        self._ensure_range()
        if combined:
            self._write(bytes([REG_CH[0], xl, xh, yl, yh]))
        else:
            self._write(bytes([REG_CH[0], xl, xh]))
            self._write(bytes([REG_CH[1], yl, yh]))
        return cx, cy

    def write_encoded(self, group):
        """Fast path: send messages made by encode_xy()/encode_ch(). Checked again here
        against this instance's range, so even a hand-made payload can't select a range
        or exceed the cap."""
        self._ensure_range()
        for msg in group:
            check_payload(msg, self.range_volts)
            try:
                os.write(self.fd, msg)          # common case: no retry bookkeeping
            except OSError:
                self._write(msg)

    def close(self):
        os.close(self.fd)


_DATA_REGS = (REG_CH[0], REG_CH[1])


def _code_bytes(code):
    data = code << 4                            # 12-bit value is left-aligned in 16 bits
    return data & 0xFF, (data >> 8) & 0xFF


def encode_xy(vx, vy, combined=False, range_volts=5):
    """Pre-encode one X/Y point into I2C messages for write_encoded().

    Values go through volts_to_code(), so the cap applies here. combined=True gives one
    6-byte message (relies on the chip auto-incrementing 0x02 -> 0x04), otherwise two.
    """
    cx, cy = volts_to_code(vx, range_volts), volts_to_code(vy, range_volts)
    xl, xh = _code_bytes(cx)
    yl, yh = _code_bytes(cy)
    if combined:
        return (bytes([REG_CH[0], xl, xh, yl, yh]),)
    return (bytes([REG_CH[0], xl, xh]), bytes([REG_CH[1], yl, yh]))


def encode_ch(volts, channel, range_volts=5):
    """Pre-encode one value for a single channel (0 or 1): one 3-byte message."""
    lo, hi = _code_bytes(volts_to_code(volts, range_volts))
    return (bytes([REG_CH[channel], lo, hi]),)


def check_payload(msg, range_volts=5):
    """Raise unless msg is a data write (0x02/0x04) whose codes are within the range's cap."""
    max_code = RANGES[range_volts][3]
    if msg[0] not in _DATA_REGS or len(msg) not in (3, 5):
        raise ValueError(f"refusing I2C message {msg.hex()}: not a channel data write")
    for k in range(1, len(msg), 2):
        if ((msg[k + 1] << 8 | msg[k]) >> 4) > max_code:
            raise ValueError(f"refusing I2C message {msg.hex()}: above the "
                             f"{RANGES[range_volts][1]:g} V cap")


def decode_payload(group):
    """Codes in a message group, for checks: [(register, code), ...]."""
    out = []
    for msg in group:
        reg = msg[0]
        for k in range(1, len(msg), 2):
            out.append((reg + (k - 1), (msg[k + 1] << 8 | msg[k]) >> 4))
    return out


class Marker:
    """Scope trigger on a GPIO, via direct register writes on /dev/gpiomem (BCM2837).

    A register write takes well under 1 us, so the edge marks the moment the script starts
    a DAC write with practically no delay of its own. Default GPIO 27 = header pin 13,
    GND next to it on pin 14.
    """
    GPFSEL0, GPSET0, GPCLR0 = 0x00, 0x1C, 0x28

    def __init__(self, pin=27):
        import mmap
        if not 4 <= pin <= 27:
            raise ValueError("marker pin must be a header GPIO 4..27 (2/3 are the I2C bus)")
        fd = os.open("/dev/gpiomem", os.O_RDWR | os.O_SYNC)
        self.mem = mmap.mmap(fd, 4096, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE)
        os.close(fd)
        self.regs = memoryview(self.mem).cast("I")
        self.mask = 1 << pin
        self.fsel = self.GPFSEL0 // 4 + pin // 10
        self.shift = (pin % 10) * 3
        self.old_mode = (self.regs[self.fsel] >> self.shift) & 7
        self.low()                              # set the level before enabling the output
        self._set_mode(1)                       # 001 = output

    def _set_mode(self, mode):
        self.regs[self.fsel] = (self.regs[self.fsel] & ~(7 << self.shift)) | (mode << self.shift)

    def high(self):
        self.regs[self.GPSET0 // 4] = self.mask

    def low(self):
        self.regs[self.GPCLR0 // 4] = self.mask

    def set(self, level):
        self.high() if level else self.low()

    def close(self):
        self.low()
        self._set_mode(self.old_mode)           # back to what it was (input)
        self.regs.release()
        self.mem.close()


class NoMarker:
    def high(self): pass
    def low(self): pass
    def set(self, level): pass
    def close(self): pass


def make_marker(pin):
    return NoMarker() if pin < 0 else Marker(pin)
