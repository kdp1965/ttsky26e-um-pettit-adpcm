# Testbench

A [cocotb](https://docs.cocotb.org/en/stable/) bench that encodes a test signal with `tools/uadpcm.py`, streams it into the chip the way the host does, and checks every clock of `uo_out` against a cycle-exact model (`model.py`), the predictor after every sample against the codec's reference decoder, and the PWM's high time against the last sample.

```sh
make -B                 # RTL
make -B GATES=yes       # gate level: copy the hardened netlist to gate_level_netlist.v first (needs PDK_ROOT)
```
