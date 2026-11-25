# The design on the Tiny Tapeout FPGA breakout (iCE40UP5K, FabricFox pinout):
#   make                 build/tt_um_pettit_micro3.bin   (yosys, nextpnr-ice40, icepack: OSS CAD Suite on the PATH)
#   make upload          copy it to the board's /bitstreams (mpremote, PORT=/dev/cu.usbmodem...)
# tt-support-tools' tt_fpga.py does the same for full-size projects; its top
# has the uio and ena ports that a micro tile project does not.
NAME = tt_um_pettit_micro3
FREQ ?= 32
PORT ?= auto
B = build
all: $(B)/$(NAME).bin
$(B)/$(NAME).bin: tt_fpga_top.v ../src/$(NAME).v tt_fpga_fabricfoxv2.pcf
	mkdir -p $(B)
	yosys -q -l $(B)/01-synth.log -DSYNTH -p 'read_verilog -sv tt_fpga_top.v ../src/$(NAME).v; synth_ice40 -top tt_fpga_top -json $(B)/$(NAME).json'
	nextpnr-ice40 -q -l $(B)/02-nextpnr.log --pcf-allow-unconstrained --seed 10 --freq $(FREQ) --package sg48 --up5k --asc $(B)/$(NAME).asc --pcf tt_fpga_fabricfoxv2.pcf --json $(B)/$(NAME).json
	icepack $(B)/$(NAME).asc $@
upload: $(B)/$(NAME).bin
	mpremote connect $(PORT) cp $< :/bitstreams/$(NAME).bin
clean:
	rm -rf $(B)
