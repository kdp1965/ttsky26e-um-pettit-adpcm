![](../../workflows/gds/badge.svg) ![](../../workflows/docs/badge.svg) ![](../../workflows/test/badge.svg)

# Micro ADPCM: a streaming audio decoder in a Tiny Tapeout micro tile

The host streams 4-bit ADPCM codes, one a sample; the chip decodes them to 16 bits with a
bit-serial datapath (one full adder) and plays them as 1 MHz sigma-delta dithered PWM. 58
flip-flops in the experimental sky130 **micro tile** (70.38 x 51.68 um; `tiles: "micro"`).

- [The datasheet](docs/info.md): the codec, the datapath, the host's protocol
- [src/tt_um_pettit_micro3.v](src/tt_um_pettit_micro3.v): the design, one file
- [tools/uadpcm.py](tools/uadpcm.py): encoder, reference decoder, converters (no dependencies)
- [host/play_ua.py](host/play_ua.py): MicroPython PIO + DMA player for the demo board (not yet run on hardware)
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

## Hardening locally

```sh
cd harden
make harden TAG=rc2        # runs/rc2/final/{gds,lef,pnl,...}; python3 metrics.py runs/rc2
make synth TAG=s1          # synthesis only (seconds): the area
```
