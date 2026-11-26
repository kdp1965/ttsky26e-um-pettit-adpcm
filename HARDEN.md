# Harden log

Local LibreLane 3.0.2 runs (`harden/`, sky130A open_pdks 8afc834) of tt_um_pettit_adpcm on the
micro tile. The recipe is `src/config.json`: drive strength 1 cells allowed in synthesis
(`src/no_synth.cells`), target density 88%, hold margins 0.04 / 0.03 ns, a one-cluster clock
tree, and a 31 ns clock period.

## Why bit-serial (2026-11-25)

A conventional parallel ADPCM decoder of the table-driven (IMA) kind was estimated at well over
the tile: its 89 x 15-bit step table alone
is some 800 um2 of logic, the 16-bit add with clamps 350, the delta's three adders 600. Two
16-bit shift registers that rotate continuously cost 640 um2 of flops and no logic at all (no
enables, no muxes: D is the neighbour's Q), and one full adder does every operation. 16-bit
registers rather than 12 because 2 x 16 clocks is one 32-clock PWM period: the registers are
back in place exactly when the PWM takes its duty, so nothing needs a shift enable.

## Runs

| run | synth um2 | result |
|-----|-----------|--------|
| rc1 | 1994 | clean, 88.1% utilization, router 4 iterations |
| rc2 | 1994 | the top module renamed tt_um_pettit_adpcm, nothing else: the same numbers; gate-level test and precheck pass |
| rc3 | 2014 | mid-scale output in reset, and the inverted PWM on uo[6] in place of the serial predictor: clean, 88.2% utilization, a longer route (15 violation counts in the router's trail against rc2's 7) |

rc1: standard cells 2641 um2, of which timing repair buffers 480 (hold buffers: a shift register
is 32 flop-to-flop paths with nothing between) and clock buffers 113; wire 5491 um; route DRC,
Magic DRC, LVS and antenna 0; 3 max-slew warnings; setup +19.8 ns at max_ss against the 31 ns
period; hold +0.064 ns at min_ff (+0.235 at tt), on top of LibreLane's 0.25 ns clock
uncertainty. Gate-level simulation of rc1's netlist: 3000 samples, 388,096 clocks, 0
mismatches. tt-support-tools precheck (main, micro rules): pass.

rc3 (2026-11-25): in reset the PWM flop toggles every clock (16 MHz at 50%) and the duty
register is set to 16, loaded from the predictor only once the constants are in; `uo[6]` is
`~pwm`. 20 um2 more logic. Standard cells 2644 um2, timing repair buffers 469, wire 5956 um;
route DRC, Magic DRC, LVS and antenna 0; 8 max-slew warnings; setup +19.4 ns, hold +0.060 ns.
The router's trail is 15 violation counts long where rc2's is 7: the tile is close to its limit. Gate-level
simulation: 3000 samples, 388,096 clocks, 0 mismatches. Precheck: pass. On the FPGA breakout
with a logic analyser: through a 1 s reset the output stays at 50.0 to 50.1% high (3.2 million
edges per 100 ms: the 16 MHz toggle) with the duty pins at 16, `uo[6]` is the complement
throughout, and a streamed clip decodes exactly (84,908 samples, 0 differences).

Not promoted: `gds/` is not in the repository; the GitHub gds action builds its own.

## On the FPGA (2026-11-25)

`fpga/` builds the design for the Tiny Tapeout FPGA breakout (iCE40UP5K, FabricFox pinout) with
its own 4-port top: tt-support-tools' `tt_fpga.py` instantiates `uio_*` and `ena`, which a micro
tile project does not have, so the template's fpga workflow cannot build it; .github/workflows/fpga.yaml here runs make -C fpga instead. 123 logic cells,
48 MHz. Run at 32 MHz with `host/play_ua.py` streaming 10 s of a song from the RP2350B and a
Saleae Logic Pro 16 on `uo_out` at 125 MS/s: the duty after each of 70,124 consecutive codes
equals the reference decoder's top 5 bits; a code every 32.00 us. The first player restarted one
DMA channel per block and left a 172 us pause at each block boundary (the PIO waits, nothing is
lost); two channels chained to each other removed it.

A whole 218 s song (3.4 MB, more than the board's flash holds) was then played through a speaker
with `host/stream_ua.py`, which sends the file over the board's USB serial port a 16 KiB block at
a time, as the board asks for them.
