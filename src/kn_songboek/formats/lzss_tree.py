"""LZSS encoder that produces the same bytes as Technics' own (the 'J KD' containers).

The keyboard's files are compressed with the classic binary-search-tree LZSS of Haruhiko Okumura
(LZSS.C, 1989), with a ring of N = 8192 bytes, longest match F = 10 and THRESHOLD = 2, the ring
filled with zero bytes and the first byte written at N - F. This is our own implementation of that
published algorithm (ADR-0004): the same tree, the same tie-breaking, so the output is byte-identical.

Stream layout (the decoder is container.lzss_decode): a flag byte for 8 items, low bit first,
1 = literal byte, 0 = reference of two bytes lo, hi with ring position lo | (hi >> 3) << 8 and
length (hi & 7) + 3.
"""
from __future__ import annotations

N = 8192            # ring size
F = 10              # longest match
THRESHOLD = 2       # shorter matches are stored as literals
NIL = N             # "no node"


def encode(data: bytes) -> bytes:
    n_in = len(data)
    if n_in == 0:
        return b""
    text = bytearray(N + F - 1)                 # ring plus a copy of its first F-1 bytes
    lson = [NIL] * (N + 1)
    rson = [NIL] * (N + 257)                    # N+1 .. N+256: one tree root per first byte
    dad = [NIL] * (N + 1)
    match = [0, 0]                              # [position, length] set by insert()

    def insert(r: int) -> None:
        cmp = 1
        p = N + 1 + text[r]
        rson[r] = lson[r] = NIL
        match[1] = 0
        while True:
            if cmp >= 0:
                if rson[p] != NIL:
                    p = rson[p]
                else:
                    rson[p] = r
                    dad[r] = p
                    return
            else:
                if lson[p] != NIL:
                    p = lson[p]
                else:
                    lson[p] = r
                    dad[r] = p
                    return
            i = 1
            while i < F:
                cmp = text[r + i] - text[p + i]
                if cmp != 0:
                    break
                i += 1
            if i > match[1]:
                match[0] = p
                match[1] = i
                if i >= F:
                    break
        # a full match: r takes p's place in the tree
        dad[r] = dad[p]
        lson[r] = lson[p]
        rson[r] = rson[p]
        dad[lson[p]] = r
        dad[rson[p]] = r
        if rson[dad[p]] == p:
            rson[dad[p]] = r
        else:
            lson[dad[p]] = r
        dad[p] = NIL

    def delete(p: int) -> None:
        if dad[p] == NIL:
            return
        if rson[p] == NIL:
            q = lson[p]
        elif lson[p] == NIL:
            q = rson[p]
        else:
            q = lson[p]
            if rson[q] != NIL:
                while rson[q] != NIL:
                    q = rson[q]
                rson[dad[q]] = lson[q]
                dad[lson[q]] = dad[q]
                lson[q] = lson[p]
                dad[lson[p]] = q
            rson[q] = rson[p]
            dad[rson[p]] = q
        dad[q] = dad[p]
        if rson[dad[p]] == p:
            rson[dad[p]] = q
        else:
            lson[dad[p]] = q
        dad[p] = NIL

    out = bytearray()
    code = bytearray(1)
    mask = 1
    s, r = 0, N - F
    pos = 0                                     # next input byte
    length = min(F, n_in)
    text[r:r + length] = data[:length]
    pos = length
    for i in range(1, F + 1):
        insert(r - i)
    insert(r)
    while length > 0:
        if match[1] > length:
            match[1] = length
        if match[1] <= THRESHOLD:
            match[1] = 1
            code[0] |= mask
            code.append(text[r])
        else:
            mp, ml = match
            code.append(mp & 0xFF)
            code.append(((mp >> 8) << 3) | (ml - (THRESHOLD + 1)))
        mask = (mask << 1) & 0xFF
        if mask == 0:
            out += code
            code = bytearray(1)
            mask = 1
        last = match[1]
        i = 0
        while i < last and pos < n_in:
            c = data[pos]
            pos += 1
            delete(s)
            text[s] = c
            if s < F - 1:
                text[s + N] = c
            s = (s + 1) & (N - 1)
            r = (r + 1) & (N - 1)
            insert(r)
            i += 1
        while i < last:
            i += 1
            delete(s)
            s = (s + 1) & (N - 1)
            r = (r + 1) & (N - 1)
            length -= 1
            if length:
                insert(r)
    if len(code) > 1:
        out += code
    return bytes(out)
