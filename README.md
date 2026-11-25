![](../../workflows/gds/badge.svg) ![](../../workflows/docs/badge.svg) ![](../../workflows/test/badge.svg) ![](../../workflows/fpga/badge.svg)

# Micro ADPCM: a streaming audio decoder in a Tiny Tapeout micro tile

The host streams 4-bit ADPCM codes, one a sample; the chip decodes them to 16 bits with a
bit-serial datapath (one full adder) and plays them as 1 MHz sigma-delta dithered PWM. 58
flip-flops in the experimental sky130 **micro tile** (70.38 x 51.68 um; `tiles: "micro"`).

- [The datasheet](docs/info.md): the codec, the datapath, the host's protocol
- [src/tt_um_pettit_micro3.v](src/tt_um_pettit_micro3.v): the design, one file
- [tools/uadpcm.py](tools/uadpcm.py): encoder, reference decoder, converters (no dependencies)
- [host/play_ua.py](host/play_ua.py): MicroPython PIO + DMA player for the demo board's RP2
- [host/stream_ua.py](host/stream_ua.py): plays a file of any length by streaming it from a computer over the board's USB port
- [fpga/](fpga/): the design on the Tiny Tapeout FPGA breakout (iCE40UP5K), where it has been run
- [HARDEN.md](HARDEN.md): the local LibreLane runs

## Make and hear a stream

```sh
afconvert -f WAVE -d LEI16@31250 -c 1 song.m4a song.wav      # macOS; any 16-bit WAV will do
python3 tools/uadpcm.py encode song.wav song.ua --gain 0.9   # also takes a prism-tui IMA ADPCM .bin
python3 tools/uadpcm.py decode song.ua check.wav             # exactly what the chip will play
python3 tools/uadpcm.py snr song.wav --seconds 20            # against IMA ADPCM
```

## Simulation

```sh
cd test
make                              # RTL: 3000 samples streamed in, every clock against test/model.py
make GATES=yes                    # the same on gate_level_netlist.v (needs PDK_ROOT)
PERIOD=1024 SAMPLES=400 make      # at the real 31250 Hz strobe rate
```

## On the FPGA breakout

```sh
cd fpga && make && make upload PORT=/dev/cu.usbmodemXXXX     # OSS CAD Suite and mpremote on the PATH
mpremote cp host/play_ua.py :/play_ua.py + cp clip.ua :/clip.ua
```

then, on the board, the six lines at the top of `host/play_ua.py`; or, for a song that does not
fit the board's flash, `python3 host/stream_ua.py song.ua /dev/cu.usbmodemXXXX` on the computer. Checked on 2026-11-25 with a
logic analyser on `uo_out`: 70,124 consecutive samples of a song, the duty after every code equal
to the reference decoder's, a code every 32.00 us with no gap between DMA blocks.

## Hardening locally

```sh
cd harden
make harden TAG=rc2        # runs/rc2/final/{gds,lef,pnl,...}; python3 metrics.py runs/rc2
make synth TAG=s1          # synthesis only (seconds): the area
```
