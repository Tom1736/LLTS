# Direct OV9281 register access over /dev/i2c-10 while the kernel driver owns the device.
from smbus2 import SMBus, i2c_msg
BUS, ADDR = 10, 0x60
_bus = SMBus(BUS, force=True)
def rd(reg, n=1):
    w = i2c_msg.write(ADDR, [reg >> 8, reg & 0xff]); r = i2c_msg.read(ADDR, n)
    _bus.i2c_rdwr(w, r); v = 0
    for b in list(r): v = (v << 8) | b
    return v
def wr(reg, val, n=1):
    data = [(val >> (8 * (n - 1 - i))) & 0xff for i in range(n)]
    _bus.i2c_rdwr(i2c_msg.write(ADDR, [reg >> 8, reg & 0xff] + data))
