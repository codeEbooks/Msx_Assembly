#!/usr/bin/env python3
"""pack53.py - the three packers of chapter 53, and their unpackers in Python.

    rlem(data)      RUNS WITH A MARKER. The first byte is the marker, the
                    byte the data uses least. Every other byte stands for
                    itself, except the marker, which starts a run: marker,
                    count, byte, a run of 4 to 255 of that byte; marker, 1,
                    marker is the marker once; marker, 0 is the end
    rlec(data)      RUNS AND COUNTS. A count byte, then: 1 to 127, that many
                    bytes as they are; 128 to 255, one byte that repeats
                    (count - 128) + 3 times, 3 to 130; 0, the end
    lz(data)        COPIES. A count byte, then: 1 to 127, that many bytes as
                    they are; 128 to 255, a byte, a distance back less one,
                    1 to 256, and (count - 128) + 3 bytes, 3 to 130, copied
                    from that far back in what is already unpacked, never
                    more bytes than the distance; 0, the end

    unrlem, unrlec, unlz    the way back, to check each packer

Each packer is greedy: it takes the longest run, or the longest copy, it
finds where it stands; lz looks back 256 bytes, and of the longest copies
takes the nearest. The copy is never longer than its distance, so that the bytes it copies are
whole before it starts: the unpacker of chapter 53 reads them back from the
VRAM, a copy at a time.
"""
from collections import Counter

RLEM_MIN = 4                            # rlem: a run of 4 or more
RLEC_MIN, RLEC_MAX = 3, 130             # rlec: runs of 3 to 130
LIT_MAX = 127                           # rlec and lz: bytes as they are
LZ_MIN, LZ_MAX = 3, 130                 # lz: copies of 3 to 130
LZ_FAR = 256                            # lz: from 1 to 256 bytes back


def marker(data):
    """the byte the data uses least, the lowest of them if several"""
    c = Counter(data)
    return min(range(256), key=lambda b: (c[b], b))


def rlem(data):
    mk = marker(data)
    out, i = [mk], 0
    while i < len(data):
        b, n = data[i], 1
        while i + n < len(data) and data[i + n] == b and n < 255:
            n += 1
        if n >= RLEM_MIN or b == mk:
            if b == mk and n < RLEM_MIN:
                n = 1
            out += [mk, n, b]
        else:
            out += [b] * n
        i += n
    return out + [mk, 0]


def unrlem(packed):
    mk, out, i = packed[0], [], 1
    while True:
        b = packed[i]
        if b != mk:
            out.append(b)
            i += 1
        elif packed[i + 1] == 0:
            return out
        else:
            out += [packed[i + 2]] * packed[i + 1]
            i += 3


def run_at(data, i, most):
    n = 1
    while i + n < len(data) and data[i + n] == data[i] and n < most:
        n += 1
    return n


def rlec(data):
    out, lit, i = [], [], 0

    def flush():
        while lit:
            part = lit[:LIT_MAX]
            del lit[:LIT_MAX]
            out.extend([len(part)] + part)
    while i < len(data):
        n = run_at(data, i, RLEC_MAX)
        if n >= RLEC_MIN:
            flush()
            out += [128 + n - RLEC_MIN, data[i]]
            i += n
        else:
            lit.append(data[i])
            i += 1
    flush()
    return out + [0]


def unrlec(packed):
    out, i = [], 0
    while packed[i]:
        c = packed[i]
        if c < 128:
            out += packed[i + 1:i + 1 + c]
            i += 1 + c
        else:
            out += [packed[i + 1]] * (c - 128 + RLEC_MIN)
            i += 2
    return out


def longest(data, i, seen):
    """the longest copy for position i: (length, distance), the nearest of
    the longest; SEEN: the positions before i, by their first three bytes"""
    best, dist = 0, 0
    for j in reversed(seen.get(bytes(data[i:i + LZ_MIN]), [])):
        d = i - j
        if d > LZ_FAR:
            break
        most = min(LZ_MAX, d, len(data) - i)
        n = 0
        while n < most and data[j + n] == data[i + n]:
            n += 1
        if n > best:
            best, dist = n, d
            if n == LZ_MAX:
                break
    return best, dist


def lz(data):
    out, lit, seen, i = [], [], {}, 0

    def flush():
        while lit:
            part = lit[:LIT_MAX]
            del lit[:LIT_MAX]
            out.extend([len(part)] + part)

    def note(k):
        if k + LZ_MIN <= len(data):
            seen.setdefault(bytes(data[k:k + LZ_MIN]), []).append(k)
    while i < len(data):
        n, d = longest(data, i, seen) if i + LZ_MIN <= len(data) else (0, 0)
        if n >= LZ_MIN:
            flush()
            out += [128 + n - LZ_MIN, d - 1]
            for k in range(i, i + n):
                note(k)
            i += n
        else:
            lit.append(data[i])
            note(i)
            i += 1
    flush()
    return out + [0]


def unlz(packed):
    out, i = [], 0
    while packed[i]:
        c = packed[i]
        if c < 128:
            out += packed[i + 1:i + 1 + c]
            i += 1 + c
        else:
            n, d = c - 128 + LZ_MIN, packed[i + 1] + 1
            assert n <= d <= len(out)
            out += out[len(out) - d:len(out) - d + n]
            i += 2
    return out


PACKERS = {"rlem": (rlem, unrlem), "rlec": (rlec, unrlec), "lz": (lz, unlz)}


def tokens(packed, kind):
    """the parts of a packed stream: (what, bytes it gives, bytes it takes),
    what "lit", "run", "copy" or "end" """
    out = []
    if kind == "rlem":
        mk, i = packed[0], 1
        while True:
            if packed[i] != mk:
                out.append(("lit", 1, 1))
                i += 1
            elif packed[i + 1] == 0:
                return out + [("end", 0, 2)]
            else:
                out.append(("run", packed[i + 1], 3))
                i += 3
    i = 0
    while packed[i]:
        c = packed[i]
        if c < 128:
            out.append(("lit", c, 1 + c))
            i += 1 + c
        elif kind == "rlec":
            out.append(("run", c - 128 + RLEC_MIN, 2))
            i += 2
        else:
            out.append(("copy", c - 128 + LZ_MIN, 2))
            i += 2
    return out + [("end", 0, 1)]


if __name__ == "__main__":
    import pic53
    for name, data in (("patterns", pic53.PATTERNS), ("colours", pic53.COLOURS)):
        for kind, (pack, unpack) in PACKERS.items():
            p = pack(data)
            assert unpack(p) == list(data)
            print(name, kind, len(p))
