# Tools: from a music file to a uADPCM stream

| file | what it does | needs |
|------|--------------|-------|
| `audio2ua.py` | the converter: mp3 / m4a / wma / flac / ogg / wav / MIDI to `.ua`, with trimming, level, limiter, fades and resampling | numpy, scipy; `afconvert` (macOS) or `ffmpeg` for compressed input |
| `uadpcm.py` | the codec itself: encoder, reference decoder, `.ua` reader and writer, signal-to-noise measurement | nothing |
| `mid2wav.py` | renders a MIDI file to a WAV with a small software synthesizer (`audio2ua.py` calls it for `.mid` input) | numpy, mido |

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python audio2ua.py song.mp3                           # -> song.ua at 31250 Hz
.venv/bin/python audio2ua.py song.m4a out.ua --trim --autoboost --wav check.wav
.venv/bin/python audio2ua.py song.wma -c left --start 19 --end 46
.venv/bin/python audio2ua.py tune.mid
python3 uadpcm.py decode song.ua check.wav                      # exactly what the chip will play
python3 uadpcm.py snr song.wav --seconds 20                     # uADPCM against IMA ADPCM
```

`.wma` and `.ogg` need `ffmpeg`; `afconvert` covers mp3, m4a/AAC, aiff, caf and flac.

## The pipeline of audio2ua.py

1. **Decode** to 16-bit PCM (`afconvert`, then `ffmpeg` if that fails); `.wav` is read directly
   and `.mid` is rendered by `mid2wav.py`.
2. **Channel**: `-c mix` (default), `left` or `right`.
3. **Cut**: `--start`, and `--end` or `--duration`, in seconds.
4. **Trim** (`--trim [S]`): leading and trailing silence, anything below `--trim-floor` dB
   (default -45) of the peak, is capped at S seconds (0.5).
5. **Level**: `--gain` (default 0.9), then `--boost DB`, or `--autoboost [PCT]`, which finds
   the boost that leaves PCT% (5) of the samples above the limiter's ceiling. The chip's
   output is a 10-bit PWM whose noise floor is fixed relative to full scale, so every dB of
   level is a dB of signal-to-noise.
6. **Limiter** (`--limit [CEILING]`, default 0.98, on with `--autoboost`): a look-ahead peak
   limiter, `--limit-lookahead` 2 ms and `--limit-release` 80 ms. It reports how much it
   touched; if most of the song is reduced by more than 1 dB, use a smaller `--autoboost`
   percentage.
7. **Fade** (`--fade`, default 0.05 s) in and out, and `--tail` (0.05 s) of silence at the
   end, so that a stream starts and ends at mid-scale with a small step.
8. **Resample** to `--rate` (default 31250 Hz: 32 MHz / 1024, one sample every 32 PWM
   periods) with a polyphase anti-aliasing filter.
9. **Encode**, then decode with the reference decoder and print the signal-to-noise ratio.

## The .ua file

| offset | size | content |
|--------|------|---------|
| 0 | 4 | `uADP` |
| 4 | 4 | number of samples (codes), little-endian |
| 8 | 4 | sample rate in Hz, little-endian |
| 12 | (samples + 1) / 2 | the codes, two to a byte: the first in bits 3:0, the second in bits 7:4 |

A code is `{sign, m2, m1, m0}`; the decoder starts from predictor 0x8000 and step 16. The
arithmetic is in the docstring of `uadpcm.py` and in [the datasheet](../docs/info.md). The
host shifts each byte out to `ui[3:0]` low nibble first, so the body of the file is the
stream.
