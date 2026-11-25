# SPDX-License-Identifier: Apache-2.0
"""play_ua.py - stream a uADPCM file (tools/uadpcm.py encode) into
tt_um_pettit_micro3 from the demo board's RP2 in MicroPython: a PIO state
machine puts one 4-bit code on ui[3:0] and pulses the strobe ui[4] per
sample, and DMA feeds it from RAM, a block at a time.

NOT YET RUN ON HARDWARE.  Check the pin numbers for your board: the defaults
are the RP2040 demo board's (ui_in[0..3] = GP9..GP12, ui_in[4] = GP17).

    import play_ua
    play_ua.play("spacelove.ua")

Before calling it: select the project, reset it (rst_n low for 16 clocks or
more) and set its clock to 32 MHz (the PWM is clock / 32, so 32 MHz is the
1 MHz the audio Pmod's filter wants; the sample rate comes from this script).
"""
import rp2
import struct
import time
from machine import Pin, mem32

CODE_PIN = 9          # ui_in[0]; ui_in[1..3] are the next three GPIOs
STROBE_PIN = 17       # ui_in[4]
BLOCK = 16384         # bytes per DMA transfer: 32768 samples, about a second

PIO0_BASE = 0x50200000
PIO0_TXF0 = PIO0_BASE + 0x010
PIO0_FDEBUG = PIO0_BASE + 0x008
DREQ_PIO0_TX0 = 0


# 16 PIO clocks per sample: the code changes while the strobe is low, the
# strobe rises half a sample later and the code stays until the next one
# (the chip reads it for 3 microseconds after the strobe).  One byte of the
# file is two codes, low nibble first.
@rp2.asm_pio(out_init=(rp2.PIO.OUT_LOW,) * 4, sideset_init=rp2.PIO.OUT_LOW,
             out_shiftdir=rp2.PIO.SHIFT_RIGHT, autopull=True, pull_thresh=8,
             fifo_join=rp2.PIO.JOIN_TX)
def _stream():
    out(pins, 4).side(0)[7]
    nop().side(1)[7]


def play(path, code_pin=CODE_PIN, strobe_pin=STROBE_PIN):
    f = open(path, "rb")
    magic, samples, rate = struct.unpack("<4sII", f.read(12))
    assert magic == b"uADP", "not a uADPCM file"
    sm = rp2.StateMachine(0, _stream, freq=16 * rate, out_base=Pin(code_pin), sideset_base=Pin(strobe_pin))
    bufs = [bytearray(BLOCK), bytearray(BLOCK)]
    dma = rp2.DMA()
    ctrl = dma.pack_ctrl(size=0, inc_read=True, inc_write=False, treq_sel=DREQ_PIO0_TX0)
    n = f.readinto(bufs[0])
    sm.active(1)
    which = 0
    try:
        while n:
            dma.config(read=bufs[which], write=PIO0_TXF0, count=n, ctrl=ctrl, trigger=True)
            which ^= 1
            n = f.readinto(bufs[which])     # read the next block while this one plays
            while dma.active():
                time.sleep_ms(1)
        time.sleep_ms(2)                    # the FIFO's last 16 samples
    finally:
        sm.active(0)
        dma.close()
        f.close()
    print("%s: %d samples at %d Hz" % (path, samples, rate))
