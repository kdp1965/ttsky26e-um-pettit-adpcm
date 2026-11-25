## How it works

Micro ADPCM is a streaming audio decoder that fits a Tiny Tapeout **micro tile**: 70.38 x 51.68 um
of sky130, a quarter of a 1x1 tile, with only `clk`, `rst_n`, `ui_in` and `uo_out`. The host sends
one 4-bit code per sample; the chip decodes it to 16 bits and plays it as 1 MHz PWM. 58 flip-flops
and about 150 gates.

### The codec

A full IMA ADPCM decoder needs an 89-entry step table and a 16-bit adder with clamps, which is
more than the tile holds. The codec here ("uADPCM") keeps IMA's predictor update and replaces the
table by arithmetic on the step itself. The code is `{sign, m[2:0]}`:

    pred = pred -/+ (step/8 + (m2 ? step : 0) + (m1 ? step/2 : 0) + (m0 ? step/4 : 0))
    step = m2 ? step + step >> (3 - m[1:0])        times 1.125, 1.25, 1.5 or 2
              : step - step/16                      which stops at 15 by itself

The predictor is 16 bits (reset to 0x8000), the step 16 bits (reset to 16). The decoder has no
clamps: the encoder (`tools/uadpcm.py`) simulates it and never emits a code that would overflow.
On the song it was tried with it measures the same signal-to-noise ratio as IMA ADPCM (37.6 dB
against 37.5 dB).

### The datapath

Everything is bit-serial. The predictor and the step are two 16-bit shift registers that rotate
all the time, least significant bit first, once every 16 clocks. One full adder adds or
subtracts a tap of the step register (the step shifted right by the tap's position) to whichever
register is being updated as it goes by. A sample is five passes: four for the predictor's four
terms and one for the step, 80 clocks, after at most 16 clocks of waiting for a pass to start.

### The output

With a 32 MHz clock two rotations are one 1 MHz PWM period. At its start the registers are back
in place: the top 5 bits of the predictor become the duty, and the next 5 feed a first-order
sigma-delta whose carry lengthens the pulse by one clock, so the average over 32 periods carries
10 bits.

## How to test

Connect the Tiny Tapeout audio Pmod so that its input is `uo[7]`, set the clock to 32 MHz and
reset (16 clocks or more). The output idles at 50% duty.

For every sample the host puts the code on `ui[3:0]`, then raises `ui[4]` (STROBE), and leaves
the code there for at least 3.5 microseconds (112 clocks) after the rising edge. The strobe is
synchronized in the chip, so the host needs no relation to its clock; the sample rate is
whatever the host's strobe rate is (up to about 250 kHz; the encoder's default is 31250 Hz).

| Pin | Function |
|-----|----------|
| `ui[3:0]` | CODE: `ui[3]` sign (1 = down), `ui[2:0]` magnitude |
| `ui[4]`   | STROBE: a rising edge takes the code |
| `uo[7]`   | PWM audio, 1 MHz |
| `uo[6]`   | the predictor going by, bit 0 first, 16 clocks a turn (bit 0 is on the pin two clocks before the PWM rises) |
| `uo[5]`   | BUSY: a code is waiting or being decoded |
| `uo[4:0]` | the PWM duty: the top 5 bits of the sample |

To make a stream: `python3 tools/uadpcm.py encode song.wav song.ua` (a 16-bit WAV at the rate
it should play at; `afconvert -f WAVE -d LEI16@31250 -c 1 song.m4a song.wav` makes one on
macOS), and `python3 tools/uadpcm.py decode song.ua check.wav` writes exactly what the chip will
play. `host/play_ua.py` is a MicroPython player for the demo board's RP2: a two-instruction PIO
program fed by two chained DMA channels. The design and the player have been run on the Tiny
Tapeout FPGA breakout (`fpga/`), where 70,124 consecutive samples matched the reference decoder.

There is no resynchronisation in the stream: a lost or repeated code shifts everything after
it, until the next reset. A code of 0 sent many times lets the step fall back to its minimum.

## External hardware

[Tiny Tapeout audio Pmod](https://github.com/MichaelBell/tt-audio-pmod) (or any low-pass filter
and amplifier) on `uo[7]`.
