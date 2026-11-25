// SPDX-License-Identifier: Apache-2.0
// The Tiny Tapeout FPGA breakout's top (tt-support-tools fpga/tt_fpga_top.v)
// for a micro tile project: it has no uio_*, no ena.
`default_nettype none

module tt_fpga_top (
    input  wire [7:0] ui_in,
    output wire [7:0] uo_out,
    input  wire       clk,
    input  wire       rst_n
);
  tt_um_pettit_micro3 user_project (
      .ui_in (ui_in),
      .uo_out(uo_out),
      .clk   (clk),
      .rst_n (rst_n)
  );
endmodule
