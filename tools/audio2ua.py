#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""audio2ua.py - convert a music file to a uADPCM stream (.ua) for
tt_um_pettit_adpcm.

    audio2ua.py song.mp3                       # -> song.ua, 31250 Hz
    audio2ua.py song.m4a out.ua --autoboost --trim
    audio2ua.py song.wma -c mix --start 19 --end 46 --wav check.wav
    audio2ua.py tune.mid                       # rendered by mid2wav.py first

The input is anything the system decoder understands (.mp3, .m4a/AAC, .wma,
.flac, .ogg, .aiff, ...), a .wav (read directly) or a .mid (rendered with
the synthesizer of mid2wav.py).  Decoding uses `afconvert` (built into
macOS) and falls back to `ffmpeg`, which is the one that knows .wma and
.ogg.

The pipeline: decode -> pick a channel (or mix them) -> cut --start/--end ->
--trim silence -> gain (--gain, --boost or --autoboost) -> look-ahead peak
limiter (--limit) -> fade in and out -> resample to --rate with a polyphase
anti-aliasing filter -> uADPCM encode (uadpcm.py) -> decode again with the
reference decoder and report the signal-to-noise ratio.

Why the level matters: the chip's output is a 10-bit PWM whose noise floor
is fixed relative to full scale, so every dB of level is a dB of
signal-to-noise.  --autoboost finds the gain that leaves a few percent of
the samples above the limiter's ceiling and lets the limiter hold those.

Needs numpy and scipy (pip install -r requirements.txt); mido as well for
.mid input.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from math import gcd

import numpy as np
import scipy.signal as sig

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import uadpcm  # noqa: E402

DEFAULT_RATE = 31250          # 32 MHz / 1024: one sample every 32 PWM periods


def decode_to_wav(src, dst_wav):
    """Decode an audio file to 16-bit PCM WAV with afconvert or ffmpeg."""
    tried = []
    if shutil.which("afconvert"):
        tried.append(["afconvert", "-f", "WAVE", "-d", "LEI16", src, dst_wav])
    if shutil.which("ffmpeg"):
        tried.append(["ffmpeg", "-y", "-v", "error", "-i", src, "-acodec", "pcm_s16le", dst_wav])
    if not tried:
        sys.exit("error: need afconvert (macOS) or ffmpeg to decode compressed audio")
    for cmd in tried:
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            return
    sys.exit("error: decoding %r failed:\n%s" % (src, res.stderr.strip()))


def read_wav(path, channel):
    """(float samples in [-1, 1], rate) for one channel or the mix of all.

    scipy.io.wavfile rather than the stdlib wave module: afconvert writes
    WAVE_FORMAT_EXTENSIBLE headers for some sources, which wave rejects.
    """
    import warnings
    from scipy.io import wavfile
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", wavfile.WavFileWarning)
        rate, data = wavfile.read(path)
    if data.dtype == np.int16:
        data = data.astype(np.float64) / 32768.0
    elif data.dtype == np.int32:
        data = data.astype(np.float64) / 2147483648.0
    elif data.dtype == np.uint8:
        data = (data.astype(np.float64) - 128.0) / 128.0
    else:
        data = data.astype(np.float64)
    if data.ndim == 1:
        return data, rate
    if channel == "mix":
        return data.mean(axis=1), rate
    return data[:, 0 if channel == "left" else min(1, data.shape[1] - 1)], rate


def trim_silence(audio, rate, keep_s, floor_db):
    """Cap leading and trailing silence (below floor_db of the peak) at keep_s."""
    peak = float(np.max(np.abs(audio))) if len(audio) else 0.0
    if peak <= 0.0:
        return audio, 0.0, 0.0
    loud = np.nonzero(np.abs(audio) > peak * 10.0 ** (floor_db / 20.0))[0]
    keep = int(keep_s * rate)
    a = max(0, int(loud[0]) - keep)
    b = min(len(audio), int(loud[-1]) + keep + 1)
    return audio[a:b], a / rate, (len(audio) - b) / rate


def limit_peaks(audio, rate, ceiling, look_ms, release_ms):
    """Look-ahead peak limiter: holds |audio| at or below `ceiling` with a
    gain that starts to fall `look_ms` before a peak arrives (a short ramp,
    not a step) and recovers exponentially with a `release_ms` time
    constant.  Prints how much it touched: a few percent of the samples
    reduced by a few dB is inaudible, tens of percent is squashed."""
    from scipy.ndimage import minimum_filter1d
    n = max(1, int(look_ms * rate / 1000))
    need = minimum_filter1d(np.minimum(1.0, ceiling / np.maximum(np.abs(audio), 1e-9)), size=2 * n + 1)
    g = np.empty_like(need)
    a = float(np.exp(-1000.0 / (release_ms * rate)))
    cur = 1.0
    for i, v in enumerate(need.tolist()):       # instant attack, exponential release
        cur = v if v < cur else 1.0 - (1.0 - cur) * a
        g[i] = cur
    g = np.convolve(np.pad(g, n, mode="edge"), np.ones(n) / n, mode="same")[n:-n]
    g = np.minimum(g, need)
    red = -20.0 * np.log10(np.maximum(g, 1e-6))
    print("limiter: ceiling %.2f, peak %.2f -> %.2f; %.2f%% of samples reduced, %.1f s by more than 1 dB, max %.1f dB"
          % (ceiling, np.abs(audio).max(), np.abs(audio * g).max(), np.mean(red > 0.1) * 100.0,
             np.sum(red > 1.0) / rate, red.max()))
    return audio * g


def fade_edges(audio, rate, fade_s):
    """Raised-cosine fade in and out: the stream starts and ends at mid-scale."""
    n = min(int(fade_s * rate), len(audio) // 2)
    if n > 0:
        w = 0.5 - 0.5 * np.cos(np.linspace(0.0, np.pi, n))
        audio = audio.copy()
        audio[:n] *= w
        audio[-n:] *= w[::-1]
    return audio


def main():
    p = argparse.ArgumentParser(description="Convert a music file to a uADPCM stream (.ua) for tt_um_pettit_adpcm.")
    p.add_argument("input", help="audio file: .mp3 .m4a .wma .flac .ogg .aiff .wav ..., or .mid")
    p.add_argument("output", nargs="?", help="output .ua (default: the input's name with .ua)")
    p.add_argument("-c", "--channel", choices=["left", "right", "mix"], default="mix",
                   help="which channel to take, or the mix of all (default mix)")
    p.add_argument("-r", "--rate", type=int, default=DEFAULT_RATE,
                   help="sample rate of the stream in Hz (default %d; the host plays at whatever the file says)"
                        % DEFAULT_RATE)
    p.add_argument("-g", "--gain", type=float, default=0.9, help="input scale, 0..1 (default 0.9)")
    bg = p.add_mutually_exclusive_group()
    bg.add_argument("--boost", type=float, default=0.0, metavar="DB",
                    help="extra gain in dB after --gain; needs --limit so the peaks cannot clip")
    bg.add_argument("--autoboost", type=float, nargs="?", const=5.0, default=None, metavar="PCT",
                    help="the boost that leaves PCT%% of the samples above the limiter's ceiling (bare: 5), "
                         "with --limit on; pairs well with --trim so silence does not skew the statistics")
    p.add_argument("--limit", type=float, nargs="?", const=0.98, default=None, metavar="CEILING",
                   help="look-ahead peak limiter holding the audio at or below CEILING (bare: 0.98)")
    p.add_argument("--limit-lookahead", type=float, default=2.0, metavar="MS", help="limiter look-ahead (default 2)")
    p.add_argument("--limit-release", type=float, default=80.0, metavar="MS", help="limiter release (default 80)")
    p.add_argument("--fade", type=float, default=0.05, metavar="S",
                   help="fade in and out, seconds (default 0.05; 0 disables)")
    p.add_argument("--tail", type=float, default=0.05, metavar="S",
                   help="silence appended, in which the decoder's step falls back toward its minimum (default 0.05)")
    p.add_argument("--trim", type=float, nargs="?", const=0.5, default=None, metavar="S",
                   help="cap leading and trailing silence at S seconds (bare: 0.5)")
    p.add_argument("--trim-floor", type=float, default=-45.0, metavar="DB",
                   help="level counted as silence for --trim, dB below the peak (default -45)")
    p.add_argument("--start", type=float, default=0.0, help="start offset in seconds (default 0)")
    eg = p.add_mutually_exclusive_group()
    eg.add_argument("--duration", type=float, help="length in seconds from --start (default: to the end)")
    eg.add_argument("--end", type=float, help="end point in seconds")
    p.add_argument("--wav", metavar="OUT.wav", help="also write what the chip will play, as a WAV")
    args = p.parse_args()

    if not os.path.exists(args.input):
        sys.exit("error: no such file: %s" % args.input)
    if not 0.0 < args.gain <= 1.0:
        sys.exit("error: --gain must be in (0, 1]")
    if args.autoboost is not None:
        if not 0.0 < args.autoboost < 50.0:
            sys.exit("error: --autoboost percent must be in (0, 50)")
        if args.limit is None:
            args.limit = 0.98
    if args.limit is not None:
        if not 0.0 < args.limit <= 1.0:
            sys.exit("error: --limit ceiling must be in (0, 1]")
        if args.limit_lookahead <= 0 or args.limit_release <= 0:
            sys.exit("error: --limit-lookahead and --limit-release must be > 0")
    elif args.boost > 0:
        sys.exit("error: --boost raises the peaks; add --limit so they cannot clip")
    if args.boost < 0:
        sys.exit("error: --boost must be >= 0 (lower --gain instead)")
    if args.fade < 0 or args.tail < 0 or (args.trim is not None and args.trim < 0):
        sys.exit("error: --fade, --tail and --trim must be >= 0")
    if args.trim_floor >= 0:
        sys.exit("error: --trim-floor must be negative (dB below the peak)")
    if not 1000 <= args.rate <= 250000:
        sys.exit("error: --rate must be 1000..250000 Hz (the chip takes a code in at most 96 clocks of 32 MHz)")

    ext = os.path.splitext(args.input)[1].lower()
    if ext in (".mid", ".midi"):
        import mid2wav
        in_rate = max(args.rate, 44100)
        audio, notes = mid2wav.render(args.input, in_rate)
        print("rendered %d notes, %.1f s" % (notes, len(audio) / in_rate))
    else:
        tmp = None
        if ext == ".wav":
            wav_path = args.input
        else:
            fd, tmp = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            wav_path = tmp
            decode_to_wav(args.input, wav_path)
        try:
            audio, in_rate = read_wav(wav_path, args.channel)
        finally:
            if tmp:
                os.unlink(tmp)

    total_s = len(audio) / in_rate
    if args.start >= total_s:
        sys.exit("error: --start (%gs) is past the end of the file (%.1fs)" % (args.start, total_s))
    if args.end is not None:
        if args.end <= args.start:
            sys.exit("error: --end must be after --start")
        end_s = args.end
    else:
        end_s = args.start + args.duration if args.duration is not None else total_s
    audio = audio[int(args.start * in_rate):min(int(end_s * in_rate), len(audio))]
    if len(audio) < 2:
        sys.exit("error: the selected range contains no audio")

    if args.trim is not None:
        audio, cut0, cut1 = trim_silence(audio, in_rate, args.trim, args.trim_floor)
        if cut0 or cut1:
            print("trim: cut %.2f s leading, %.2f s trailing silence" % (cut0, cut1))

    if args.autoboost is not None:
        q = float(np.percentile(np.abs(audio), 100.0 - args.autoboost))
        args.boost = max(0.0, 20.0 * np.log10(args.limit / (args.gain * q))) if q > 0.0 else 0.0
        over = float(np.mean(np.abs(audio) * args.gain * 10.0 ** (args.boost / 20.0) > args.limit)) * 100.0
        print("autoboost: %+.1f dB (%.1f%% of samples above the %g ceiling)" % (args.boost, over, args.limit))

    audio = audio * (args.gain * 10.0 ** (args.boost / 20.0))
    if args.limit is not None:
        audio = limit_peaks(audio, in_rate, args.limit, args.limit_lookahead, args.limit_release)
    audio = fade_edges(audio, in_rate, args.fade)

    g = gcd(args.rate, in_rate)
    pcm = sig.resample_poly(audio, args.rate // g, in_rate // g)
    pcm = np.concatenate([pcm, np.zeros(int(args.tail * args.rate))])
    target = np.clip(np.round(pcm * 32767.0), -32768, 32767).astype(np.int64) + 32768
    print("%.2f s of audio -> %d samples at %d Hz; encoding ..." % (len(audio) / in_rate, len(target), args.rate))

    codes = uadpcm.encode(target.tolist())
    got = np.array(uadpcm.decode(codes), dtype=np.float64)
    ref = target.astype(np.float64)
    noise = float(np.mean((got - ref) ** 2))
    snr = 10.0 * np.log10(np.mean((ref - 32768.0) ** 2) / noise) if noise else float("inf")

    out = args.output or os.path.splitext(args.input)[0] + ".ua"
    uadpcm.write_ua(out, codes, args.rate)
    print("wrote %s: %d bytes (%.0f KiB), %.1f s, SNR %.1f dB"
          % (out, os.path.getsize(out), os.path.getsize(out) / 1024, len(codes) / args.rate, snr))
    if args.wav:
        uadpcm.write_wav(args.wav, args.rate, [int(v) - 32768 for v in got])
        print("wrote %s: what the chip will play" % args.wav)


if __name__ == "__main__":
    main()
