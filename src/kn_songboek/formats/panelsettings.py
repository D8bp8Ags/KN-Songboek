"""Every setting of a panel memory that we can name, read from its tag/length blocks.

A panel memory (a registration button) is the keyboard's live panel state. Which byte holds which
setting comes from public documentation of the panel memory records and of the firmware's own
parameter table (read only; own code). Each setting
says whether its meaning is sure: "sure" = a named firmware routine reads or shows it as that
setting; not sure = the place is known but what the number means (the names of effect types,
pedal functions, TECHNI-CHORD types, the EQ scale ...) is not.

Each setting is a dict, so it travels through asdict() and JSON unchanged:
    group   "style", "keys", "volumes", "R1"/"R2"/"L"/..., "effects", "eq", "pedals", "midi"
    key     what it is ("variation", "split_point" ...): the front end names it
    value   int, bool or str
    fmt     how to show the value: "plain", "plus1" (0-based -> 1-based), "signed" (64 = 0),
            "signed24" (24 = 0), "signed128" (128 = 0), "note" (MIDI key), "onoff", "pan" (64 = centre), "channel" (0-15,
            FF = off), "drawbars"
    sure    bool
"""
from __future__ import annotations

from typing import Dict, List

# part records (72 bytes): tag -> part name
PART_TAGS = {0x10: "R1", 0x11: "R2", 0x12: "L", 0x1B: "CHORD", 0x1F: "BPEDAL"}
SEQ_PARTS = {t: "P%d" % (t + 1) for t in range(16)}
# 4-byte entries of the accompaniment parts, in this order
ACCOMP_TAGS = {0x13: "acc1", 0x14: "acc2", 0x15: "acc3", 0x16: "acc4", 0x17: "acc5", 0x18: "bass",
               0x19: "drums1", 0x1A: "drums2"}


def _s(group: str, key: str, value, fmt: str = "plain", sure: bool = True) -> dict:
    return {"group": group, "key": key, "value": value, "fmt": fmt, "sure": sure}


def _part(group: str, d: bytes, sounds: bool) -> List[dict]:
    """One part record: effects, pan, tone and tuning; the sound itself only when sounds is set
    (R1/R2/L are shown with their sound elsewhere)."""
    out: List[dict] = []
    if len(d) < 0x3C:
        return out
    if sounds:
        out.append(_s(group, "sound", "%d/%d/%d" % (d[0] & 0x7F, d[1], d[2])))
        out.append(_s(group, "volume", d[3] & 0x7F))
    out.append(_s(group, "reverb", d[0x0E] & 0x7F))
    out.append(_s(group, "chorus", d[0x0D] & 0x7F))
    out.append(_s(group, "chorus_on", bool(d[0x0D] & 0x80), "onoff"))
    out.append(_s(group, "multi", d[0x0C] & 0x7F))
    out.append(_s(group, "multi_on", bool(d[0x0C] & 0x80), "onoff"))
    out.append(_s(group, "dsp", d[0x0B] & 0x7F))
    out.append(_s(group, "dsp_on", bool(d[0x0B] & 0x80), "onoff"))
    out.append(_s(group, "pan", d[0x1C], "pan"))
    out.append(_s(group, "sustain", bool(d[4] & 0x08), "onoff"))
    out.append(_s(group, "mono", bool(d[4] & 0x80), "onoff"))
    out.append(_s(group, "portamento", d[0x0F] & 0x7F))
    out.append(_s(group, "portamento_on", bool(d[0x0F] & 0x80), "onoff"))
    for off, key in ((0x10, "resonance"), (0x11, "release"), (0x12, "attack"), (0x13, "cutoff"),
                     (0x14, "decay"), (0x15, "vib_rate"), (0x16, "vib_depth"), (0x17, "vib_delay")):
        out.append(_s(group, key, d[off], "signed"))
    out.append(_s(group, "coarse_tune", d[0x1D], "signed"))
    out.append(_s(group, "fine_tune", d[0x1E], "signed"))
    out.append(_s(group, "bend_range", d[0x1F]))
    if d[2] == 34:                                   # a drawbar organ sound: its nine drawbars
        bars = [d[0x26] & 0x0F, d[0x26] >> 4, d[0x27] & 0x0F, d[0x27] >> 4, d[0x28] & 0x0F, d[0x28] >> 4,
                d[0x29] & 0x0F, d[0x29] >> 4, d[0x2A] & 0x0F]
        out.append(_s(group, "drawbars", "".join(str(min(b, 8)) for b in bars), "plain", sure=False))
    out.append(_s(group, "tremulant", d[0x23] & 0x07, sure=False))
    out.append(_s(group, "midi_channel", d[0x3B], "channel"))
    return out


def settings(blocks: Dict[int, bytes]) -> List[dict]:
    """All settings of one panel memory, from {tag: block data}, group by group."""
    out = _style(blocks) + _keys(blocks) + _volumes(blocks)
    for tag, group in PART_TAGS.items():
        if tag in blocks:
            out += _part(group, blocks[tag], sounds=tag not in (0x10, 0x11, 0x12))
    return out + _effects(blocks) + _eq(blocks) + _pedals(blocks) + _midi(blocks)


def _style(blocks: Dict[int, bytes]) -> List[dict]:
    out: List[dict] = []
    b42, b44, b41 = blocks.get(0x42, b""), blocks.get(0x44, b""), blocks.get(0x41, b"")
    if len(b42) >= 8:
        out.append(_s("style", "variation", (b42[7] >> 4) & 0x03, "plus1"))
        out.append(_s("style", "techni_on", bool(b42[4] & 0x40), "onoff", sure=False))
        out.append(_s("style", "tempo_sync", b42[6] & 0x0F, sure=False))
    if len(b44) >= 5:
        out.append(_s("style", "techni_type", b44[4] & 0x0F, sure=False))
    if len(b41) >= 5:
        out.append(_s("style", "left_hold", bool(b41[3] & 0x01), "onoff"))
        out.append(_s("style", "on_bass", bool(b41[3] & 0x02), "onoff"))
        out.append(_s("style", "conductor", b41[0] & 0x07, sure=False))
    return out


def _keys(blocks: Dict[int, bytes]) -> List[dict]:
    out: List[dict] = []
    b44, b41 = blocks.get(0x44, b""), blocks.get(0x41, b"")
    if len(b44) >= 3:
        out.append(_s("keys", "split_point", b44[1], "note"))
        out.append(_s("keys", "split_mode", b44[0] & 0x03, sure=False))
        out.append(_s("keys", "transpose", b44[2], "signed"))
        out.append(_s("keys", "tremolo", bool(b44[0] & 0x04), "onoff"))
    if len(b41) >= 5:
        out.append(_s("keys", "r_octave", b41[4], "signed"))
    return out


def _volumes(blocks: Dict[int, bytes]) -> List[dict]:
    out = [_s("volumes", key, blocks[tag][0] & 0x7F) for tag, key in ACCOMP_TAGS.items() if blocks.get(tag)]
    b46, b44 = blocks.get(0x46, b""), blocks.get(0x44, b"")
    if len(b46) >= 2:
        out.append(_s("volumes", "pad_volume", b46[0] & 0x7F))
        out.append(_s("volumes", "pad_bank", b46[1], "plus1"))
    if len(b44) >= 14:
        out += [_s("volumes", "apc_reverb%d" % (i + 1), x & 0x7F, sure=False) for i, x in enumerate(b44[12:20])]
    return out


def _effects(blocks: Dict[int, bytes]) -> List[dict]:
    b4c = blocks.get(0x4C, b"")
    if len(b4c) < 14:
        return []
    return ([_s("effects", "reverb_on", bool(b4c[0] & 0x80), "onoff"),
             _s("effects", "eq_on", bool(b4c[0] & 0x20), "onoff", sure=False)]
            + [_s("effects", "effect%d" % (i + 1), (b4c[2 + 2 * i] & 0x7F) | (b4c[3 + 2 * i] & 0x7F) << 7, sure=False)
               for i in range(6)])


def _eq(blocks: Dict[int, bytes]) -> List[dict]:
    b4d = blocks.get(0x4D, b"")
    if len(b4d) < 13:
        return []
    return [_s("eq", key, b4d[off], "signed24", sure=False)
            for off, key in ((1, "eq_low"), (4, "eq_mid1"), (7, "eq_mid2"), (10, "eq_mid3"), (12, "eq_high"))]


def _pedals(blocks: Dict[int, bytes]) -> List[dict]:
    b48 = blocks.get(0x48, b"")
    if len(b48) < 10:
        return []
    return [_s("pedals", key, b48[off], sure=False)
            for off, key in ((2, "expr_pedal"), (4, "fsw1"), (5, "fsw2"), (6, "fc_sw1"), (7, "fc_sw2"), (8, "fc_sw3"),
                             (9, "fc_sw4"))]


def _midi(blocks: Dict[int, bytes]) -> List[dict]:
    """The MIDI control channel and the sequencer parts."""
    b43 = blocks.get(0x43, b"")
    out = [_s("midi", "control_channel", b43[0], "channel")] if b43 else []
    for tag, group in SEQ_PARTS.items():
        if tag in blocks and len(blocks[tag]) >= 4:
            d = blocks[tag]
            out.append(_s("seq", group, "%d/%d/%d" % (d[0] & 0x7F, d[1], d[2])))
            out.append(_s("seq", group + "_volume", d[3] & 0x7F))
    return out
