# The web player

A page that turns a music file into a uADPCM stream and plays it through `tt_um_pettit_adpcm`
on a Tiny Tapeout demo board, over Web Serial. Nothing is installed and nothing leaves the
computer: the decoding, the conversion and the encoder all run in the browser.

It is published at **https://kdp1965.github.io/uadpcm-player/** (the repository
[kdp1965/uadpcm-player](https://github.com/kdp1965/uadpcm-player) is a copy of this folder; `./publish.sh`
updates a checkout of it). To run it from here:

```sh
python3 -m http.server 8000 --bind 127.0.0.1 --directory web     # then open http://127.0.0.1:8000
```

or open `web/index.html` directly. Web Serial needs Chrome or Edge on a computer.

## What it does

1. **Connect** opens the board's USB serial port, takes over its MicroPython REPL and loads a
   small player onto it (in RAM: nothing is installed on the board).
   - On the **FPGA breakout** it checks that the board has this design's bitstream
     (`/bitstreams/tt_um_pettit_adpcm.bin`, compared by size and CRC) and uploads the one in
     `bitstream.js` if it is missing. It asks first if the FPGA is running another design or if
     a different bitstream of the same name is already there.
   - On a board with a **chip**, it enables the project of that name in the shuttle.
   - If a **Tiny Tapeout QSPI Pmod** is on the `uio` port it finds the flash (by its JEDEC ID)
     and each PSRAM (by writing a location, reading it back and restoring it).
2. **Drop a file** (mp3, m4a, wav, flac, ogg, or a `.ua` made by `tools/audio2ua.py`). It is
   decoded, mixed to mono, cut, trimmed, levelled, limited, faded and encoded; every setting
   re-runs the conversion, and the waveform shows what the chip will play. *Preview here* plays
   exactly that through the computer; *Download .ua* saves the stream.
   *Auto boost* raises the level until the given percentage of the samples is over the
   limiter's ceiling, then backs off until the limiter reduces less than 0.8% of the song by
   more than 1 dB (`tools/audio2ua.py --autoboost` does only the first part).
   The **ready-made songs** under the drop zone are the `.ua` files in `songs/`: a click loads
   one into the same viewer, to stream, save or download. They are fetched, so the page must be
   served for them (not opened as a file). To change the list, add or remove files in `songs/`
   and run `python3 mksongs.py > songs/songs.js` in `web/`.
3. **Play on chip** streams it. Click the waveform to choose where to start; *Stop* fades out.
4. **Save to board** writes the stream to the Pmod's flash or to one of its PSRAMs, verified
   block by block. The songs listed under *Songs on the board* are then played by the board on
   its own, read from the Pmod, with the page only showing progress and a *Stop*. A song can be
   renamed or deleted, on the flash as well: only the 4 KiB directory is rewritten.
5. **Pause** stops the codes: the chip holds its output and its state, and **Resume** carries on
   from the same sample. It works for a stream and for a song the board is playing.
6. **Disconnect** (or closing the page) while something is playing stops it first.

## Files

| file | |
|------|---|
| `index.html`, `app.js` | the page |
| `uadpcm.js` | the codec, bit for bit the same as `tools/uadpcm.py`; the `.ua` file; the song library's directory |
| `dsp.js` | trim, auto level, look-ahead limiter, fades (as `tools/audio2ua.py`) |
| `board.js` | the serial protocol and, in it, the MicroPython program that runs on the board |
| `songs/`, `mksongs.py` | the ready-made songs and the script that lists them in `songs/songs.js` |
| `bitstream.js` | the FPGA bitstream, generated: `make -C fpga web` |

`uadpcm.js`, `dsp.js` and `board.js` also load in Node (`require`), which is how they are tested.

## The board side

The player on the board is a PIO state machine that puts one 4-bit code on `ui[3:0]` and pulses
`ui[4]` per sample, fed by two DMA channels chained to each other; Python refills the buffer
that is not playing. The pins are taken from the board's SDK, so the same code serves the
RP2350 FPGA breakout and the demo boards.

- **Streaming**: the board asks for a block (`R`), the page answers with a 2-byte length and up
  to 4096 bytes (8192 samples); length 0 ends the stream. If the page goes away the board gives
  up after 4 s.
- **Pause**: between blocks the page may send `FF FF`; the board stops the state machine that
  clocks the codes out (the DMA waits behind it) until two more bytes, `FE FF`, arrive.
- **The Pmod** is driven from the RP2 with a second PIO as plain SPI at 8 MHz (`uio0` flash CS,
  `uio1` MOSI, `uio2` MISO, `uio3` SCK, `uio6`/`uio7` the PSRAMs' CS). The micro tile has no
  `uio`, so the chip is not involved. PSRAM is read and written in 512-byte bursts.
- **The library** is a 4 KiB directory at the start of each store (`uALB`, then up to 102
  entries of name, offset, length, rate and sample count) and the streams after it at 4
  KiB-aligned offsets. On the flash that means address 0 upward: the page asks before it
  writes to a flash that has no library yet.

## Not there yet

- MIDI files (convert them with `tools/audio2ua.py` and drop the `.ua`).
- Recognising the ttsky26e chip by its shuttle and tile: at present any board whose shuttle has
  a project of the configured name is accepted.
