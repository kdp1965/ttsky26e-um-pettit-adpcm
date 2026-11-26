#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""mid2wav.py FILE.mid OUT.wav [RATE] - render a MIDI file to a mono 16-bit
WAV with a small software synthesizer, ready for audio2ua.py (which also
takes a .mid directly and calls this).

Channel timbres: even channels get a decaying piano-like additive tone, odd
channels a detuned sustained pad.  Full polyphony and note durations are
honoured.  RATE defaults to 31250 Hz, the rate the streams play at.

Needs mido and numpy (pip install -r requirements.txt).
"""
import sys
import wave

import numpy as np

DEFAULT_RATE = 31250


def render(path, rate=DEFAULT_RATE):
    """The MIDI file as float samples in [-1, 1] at `rate`, and the note count."""
    import mido
    evs, active, t = [], {}, 0.0
    for msg in mido.MidiFile(path):
        t += msg.time
        if msg.type == 'note_on' and msg.velocity > 0:
            active[(msg.channel, msg.note)] = (t, msg.velocity)
        elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
            k = (msg.channel, msg.note)
            if k in active:
                t0, v = active.pop(k)
                evs.append((t0, t, msg.note, v, msg.channel))
    if not evs:
        sys.exit("error: no notes found in %s" % path)

    dur = max(e[1] for e in evs) + 2.0
    mix = np.zeros(int(dur * rate))
    for t0, t1, note, vel, ch in evs:
        f = 440.0 * 2 ** ((note - 69) / 12)
        length = t1 - t0
        rel = 0.35 if ch % 2 else 0.25
        ns = int((length + rel) * rate)
        tt = np.arange(ns) / rate
        x = np.zeros(ns)
        if ch % 2 == 0:                     # piano-like
            for h in range(1, 9):
                if f * h > rate * 0.45:
                    break
                x += np.sin(2 * np.pi * f * h * tt) / (h ** 1.5)
            env = np.exp(-tt / 0.9) * np.minimum(tt / 0.004, 1.0)
            env[tt > length] *= np.exp(-(tt[tt > length] - length) / 0.08)
            amp = 1.0
        else:                               # sustained pad
            for d in (-0.15, 0.15):
                fd = f * 2 ** (d / 100)
                for h in (1, 2, 3):
                    if fd * h > rate * 0.45:
                        break
                    x += np.sin(2 * np.pi * fd * h * tt) / (h ** 2) * 0.5
            env = np.minimum(tt / 0.15, 1.0)
            env[tt > length] *= np.exp(-(tt[tt > length] - length) / rel)
            amp = 0.5
        i0 = int(t0 * rate)
        end = min(i0 + ns, len(mix))
        mix[i0:end] += (x * env * (vel / 127.0) * amp)[:end - i0]
    return mix / (np.abs(mix).max() * 1.05), len(evs)


def main():
    if len(sys.argv) not in (3, 4):
        sys.exit(__doc__)
    rate = int(sys.argv[3]) if len(sys.argv) == 4 else DEFAULT_RATE
    mix, notes = render(sys.argv[1], rate)
    with wave.open(sys.argv[2], "w") as fo:
        fo.setnchannels(1)
        fo.setsampwidth(2)
        fo.setframerate(rate)
        fo.writeframes((mix * 32767).astype("<i2").tobytes())
    print("rendered %.1f s (%d notes) at %d Hz -> %s" % (len(mix) / rate, notes, rate, sys.argv[2]))


if __name__ == "__main__":
    main()
