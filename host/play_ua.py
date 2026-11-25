# SPDX-License-Identifier: Apache-2.0
"""play_ua.py - stream a uADPCM file (tools/uadpcm.py encode) into
tt_um_pettit_micro3 from the demo board's RP2 in MicroPython: a PIO state
machine puts one 4-bit code on ui[3:0] and pulses the strobe ui[4] per
sample, and two DMA channels that chain to each other feed it from two RAM
buffers, so the stream has no gap while the next block is read from flash.

Run on the Tiny Tapeout FPGA breakout (TTDBv3, RP2350B): ui_in[0..3] are
GPIO 17..20 and ui_in[4] is GPIO 21 there, the defaults below.  The RP2040
demo boards have ui_in[0..3] on GPIO 9..12 and ui_in[4] on GPIO 17.

    from ttboard.boot.demoboard_detect import DemoboardDetect
    from ttboard.demoboard import DemoBoard
    DemoboardDetect.probe(); tt = DemoBoard()
    tt.shuttle.tt_um_pettit_micro3.enable()
    tt.clock_project_PWM(32_000_000)      # the PWM is clock / 32: 1 MHz
    tt.reset_project(True); tt.reset_project(False)
    import play_ua
    play_ua.play("/clip.ua")
"""
import rp2
import struct
import time
from machine import Pin, mem32

CODE_PIN = 17         # ui_in[0]; ui_in[1..3] are the next three GPIOs
STROBE_PIN = 21       # ui_in[4]
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
    dma = [rp2.DMA(), rp2.DMA()]

    def ctrl(i, chain):
        # a channel that chains to itself does not chain
        return dma[i].pack_ctrl(size=0, inc_read=True, inc_write=False, treq_sel=DREQ_PIO0_TX0,
                                chain_to=dma[i ^ 1 if chain else i].channel)

    def load(i):
        """Read the next block into buffer i and arm its channel; False at the end of the file."""
        n = f.readinto(bufs[i])
        if n:
            dma[i].config(read=bufs[i], write=PIO0_TXF0, count=n, ctrl=ctrl(i, True), trigger=False)
        return n

    try:
        if load(0):
            more = load(1)
            if not more:
                dma[0].ctrl = ctrl(0, False)
            sm.active(1)
            dma[0].active(1)
            cur = 0
            while True:
                while dma[cur].active():        # the other channel starts by itself when this one ends
                    time.sleep_ms(1)
                if not more:
                    break
                more = load(cur)                # refill the one that just finished, behind the one playing
                if not more:
                    dma[cur ^ 1].ctrl = ctrl(cur ^ 1, False)
                cur ^= 1
            time.sleep_ms(2)                    # the FIFO's last 16 samples
    finally:
        sm.active(0)
        dma[0].close()
        dma[1].close()
        f.close()
    print("%s: %d samples at %d Hz" % (path, samples, rate))
