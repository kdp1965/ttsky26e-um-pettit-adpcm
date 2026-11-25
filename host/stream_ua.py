#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""stream_ua.py FILE.ua [PORT] - play a uADPCM file of any length on the Tiny
Tapeout FPGA breakout by streaming it from this computer over the board's USB
serial port: the board asks for a 16 KiB block ("R"), this script sends it,
and the two chained DMA channels of host/play_ua.py play the blocks without
a gap.  For files that do not fit the board's flash (a 3.6 minute song at
31250 Hz is 3.4 MB).

Needs mpremote (pip install mpremote).  The board must hold the bitstream
(/bitstreams/tt_um_pettit_micro3.bin, fpga/ `make upload`).
"""
import struct
import sys
import time

from mpremote.transport_serial import SerialTransport

BOARD = r'''
import sys, time, micropython, rp2, struct
from machine import Pin
from ttboard.boot.demoboard_detect import DemoboardDetect
from ttboard.demoboard import DemoBoard
DemoboardDetect.probe()
tt = DemoBoard()
tt.shuttle.tt_um_pettit_micro3.enable()
tt.ui_in.value = 0
tt.clock_project_PWM(32000000)
tt.reset_project(True); time.sleep_ms(5); tt.reset_project(False)

BLOCK = 16384
TXF0 = 0x50200010

@rp2.asm_pio(out_init=(rp2.PIO.OUT_LOW,) * 4, sideset_init=rp2.PIO.OUT_LOW,
             out_shiftdir=rp2.PIO.SHIFT_RIGHT, autopull=True, pull_thresh=8, fifo_join=rp2.PIO.JOIN_TX)
def _stream():
    out(pins, 4).side(0)[7]
    nop().side(1)[7]

def run(rate, left):
    inp = sys.stdin.buffer
    sm = rp2.StateMachine(0, _stream, freq=16 * rate, out_base=Pin(17), sideset_base=Pin(21))
    bufs = [bytearray(BLOCK), bytearray(BLOCK)]
    mvs = [memoryview(b) for b in bufs]
    dma = [rp2.DMA(), rp2.DMA()]
    def ctrl(i, chain):
        return dma[i].pack_ctrl(size=0, inc_read=True, inc_write=False, treq_sel=0,
                                chain_to=dma[i ^ 1 if chain else i].channel)
    def load(i):
        nonlocal left
        n = min(BLOCK, left)
        if n:
            sys.stdout.write("R\n")
            k = 0
            while k < n:
                k += inp.readinto(mvs[i][k:n])
            left -= n
            dma[i].config(read=bufs[i], write=TXF0, count=n, ctrl=ctrl(i, True), trigger=False)
        return n
    micropython.kbd_intr(-1)            # the stream is binary: 0x03 is data
    try:
        if load(0):
            more = load(1)
            if not more:
                dma[0].ctrl = ctrl(0, False)
            sm.active(1)
            dma[0].active(1)
            cur = 0
            while True:
                while dma[cur].active():
                    time.sleep_ms(1)
                if not more:
                    break
                more = load(cur)
                if not more:
                    dma[cur ^ 1].ctrl = ctrl(cur ^ 1, False)
                cur ^= 1
            time.sleep_ms(2)
    finally:
        micropython.kbd_intr(3)
        sm.active(0)
        dma[0].close(); dma[1].close()
    sys.stdout.write("DONE\n")
'''


def main():
    path = sys.argv[1]
    port = sys.argv[2] if len(sys.argv) > 2 else "/dev/cu.usbmodem12201"
    blob = open(path, "rb").read()
    magic, samples, rate = struct.unpack_from("<4sII", blob, 0)
    assert magic == b"uADP", "not a uADPCM file"
    body = blob[12:]
    t = SerialTransport(port, baudrate=115200)
    t.enter_raw_repl()
    t.exec_raw_no_follow(BOARD + "\nrun(%d, %d)\n" % (rate, len(body)))
    ser = t.serial
    sent, line, t0 = 0, b"", None
    print("%s: %d samples at %d Hz, %.0f s" % (path, samples, rate, samples / rate), flush=True)
    while True:
        c = ser.read(1)
        if not c:
            continue
        if c != b"\n":
            line += c
            continue
        text, line = line.strip(), b""
        if text == b"R":
            if t0 is None:
                t0 = time.time()
            ser.write(body[sent:sent + 16384])
            sent += 16384
            if (sent // 16384) % 20 == 0:
                print("  %3.0f s sent, %.0f s elapsed" % (min(sent, len(body)) * 2 / rate, time.time() - t0), flush=True)
        elif text == b"DONE":
            print("played %d bytes in %.1f s" % (len(body), time.time() - t0), flush=True)
            break
        elif b"Traceback" in text or b"Error" in text:
            print(text.decode(errors="replace"), flush=True)
            print(ser.read(2000).decode(errors="replace"), flush=True)
            break
    t.exit_raw_repl()
    t.close()


if __name__ == "__main__":
    main()
