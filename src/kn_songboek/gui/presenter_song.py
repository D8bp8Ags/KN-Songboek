"""What the presenter says about one song: the info panel (song_panel, which shows everything in it),
the facts used in the panel, the export and the PDF (song_facts, song_info), and the panel settings in
words. A part of MainPresenter (it inherits SongDetails); kept apart only to keep presenter.py readable."""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from ..core import KN7Error
from ..formats import songdata
from .i18n import has_key, size_text

Slot = Tuple[int, int]          # (folder, song)
FAIL = object()                 # returned by MainPresenter._guard when the call raised


class SongDetails:
    """Mixed into MainPresenter; uses its session, t() and settings."""

    def _seq_lines(self, d) -> List[str]:
        def count(n, one, many):
            return self.t(one) if n == 1 else self.t(many, n=n)

        out = []
        for q in d["sequencer"]:
            if q["tracks"]:
                line = self.t("cont_seq_line", tempo=q["tempo"] or "?", beats=count(q["beats"], "cont_beat", "cont_beats"),
                              notes=count(q["notes"], "cont_note", "cont_notes"))
                out.append("%s  ·  %s" % (q["name"], line) if q["name"] else line)
        return out

    def _pad_name(self, x) -> str:
        return (x["name"] or self.t("cont_user_pad", n=x["user"])) if x["user"] else self.t("cont_builtin_pad")

    def _kn5000(self, slot: Slot) -> bool:
        """True when one of the song's files is a KN5000 file (container.KN5000_MAGIC)."""
        from ..formats import container
        s = self.session
        try:
            files = s.song_details(*slot)["files"]
            for f in files.values():
                if f.get("bytes") and s.planned().read(f["path"])[:4] in container.KN5000_MAGIC:
                    return True
        except Exception:
            pass
        return False

    def say(self, text) -> str:
        """A core text (core.errors.Text, e.g. a rhythm label) in the user's language; plain text as it is."""
        key = getattr(text, "key", "")
        return self.t("txt." + key, **text.values) if key and has_key("txt." + key) else str(text)

    def song_panel(self, slot: Slot) -> Optional[Dict[str, object]]:
        """Everything in the song, for the info panel's sections: the Reg Banks with every button (name,
        rhythm, tempo, chord mode, the sounds on R1/R2/L), the recording, composer styles, pads, own
        sounds, the home page picture, files and what could not be read. Read quietly (no error
        windows): the panel fills itself while the user clicks through songs. None if unreadable."""
        t, s = self.t, self.session
        try:
            d = s.song_details(*slot)
        except (KN7Error, OSError, ValueError, KeyError):
            return None
        cmp = self._cmp_part(d)
        banks = [self._panel_bank(b, cmp) for b in d.get("panel_memories", [])]
        saved = ("" if not banks else t("saved_all", n=len(banks)) if len(banks) > songdata.SONG_BANKS
                 else t("saved_three"))
        styles = [(x["number"], x["name"] or t("noname"), [v for v in x["variations"] if v]) for x in d.get("styles", [])]
        pads = [{"number": b["number"], "name": b["name"] or t("noname"),
                 "pads": [(x["number"], bool(x["user"]), self._pad_name(x)) for x in b["pads"]]}
                for b in (d["pads"]["banks"] if d.get("pads") else [])]
        snd = d.get("sounds")
        own = [(i, n) for i, n in enumerate(snd["sounds"], 1) if n] if snd else []
        files = [(ext, size_text(x["bytes"]) if x["bytes"] is not None else t("cont_missing"))
                 for ext, x in d["files"].items()]
        return {"banks": banks, "saved": saved, "recording": self._seq_lines(d), "styles": styles, "pads": pads,
                "own_sounds": own, "drum_kit": snd.get("drum_kit") if snd else None, "has_sounds": bool(snd),
                "bmp": self._quiet_bmp(slot, d), "files": files,
                "errors": [(t("cont_unreadable", ext=ext), self.say(e)) for ext, e in d.get("errors", {}).items()]}

    def _quiet_bmp(self, slot: Slot, d) -> Optional[bytes]:
        if "home_page" not in d:
            return None
        try:
            return self.session.home_page_bmp(*slot)
        except (KN7Error, OSError, ValueError, KeyError):
            return None

    def _cmp_part(self, d) -> Optional[bytes]:
        """The song's CMP unpacked (it names the MEMORY rhythms), or None."""
        from ..formats import container
        f = d["files"].get("CMP")
        if not (f and f["bytes"]):
            return None
        try:
            return container.parse(self.session.planned().read(f["path"]), "CMP").parts[0]
        except Exception:                            # only costs MEMORY rhythm names
            return None

    def _panel_bank(self, b, cmp) -> Dict[str, object]:
        mems = [self._panel_memory(m, cmp) for m in b["memories"]]
        return {"label": b.get("label") or str(b["number"]), "name": b["name"],
                "used": sum(1 for m in mems if m["filled"]),          # a button without a name still has settings
                "named": sum(1 for m in mems if m["name"]), "memories": mems}

    def _panel_memory(self, m, cmp) -> Dict[str, object]:
        from ..formats.rhythm import decode
        t = self.t
        sounds = []
        for x in m.get("sounds") or []:
            ps = songdata.PartSound(**x)
            kind = songdata.sound_kind(ps) or t("sound_bank", msb=ps.msb, lsb=ps.lsb, n=ps.program + 1)
            sounds.append((ps.part, t("part_long_" + ps.part), kind, ps.volume))
        rhythm = ""
        if m.get("rhythm"):
            try:
                rhythm = self.say(decode(m["rhythm"], cmp).label)
            except Exception:
                rhythm = ""
        return {"number": m["number"], "name": m["name"], "tempo": m["tempo"], "rhythm": rhythm,
                "filled": bool(m["name"] or m.get("rhythm") or m.get("sounds") or m["tempo"]),
                "settings": self.settings_groups(m.get("settings") or []),
                "basic": self.settings_groups(m.get("settings") or [], basic=True),
                "chord": t("chord_%d" % m["chord"]) if m.get("chord") in songdata.CHORD_MODES else "",
                "sounds": sounds}

    def song_facts(self, slot: Slot, details=None, all_banks=None) -> Dict[str, str]:
        """What the song files say, as {field: text}: rhythm, meter, tempo, model, recorded, chord, banks,
        inside. One place for the info panel and the song list (CSV/PDF), so they always agree."""
        s = self.session
        d = details if details is not None else s.song_details(*slot)
        seq = d["sequencer"]
        q = next((x for x in seq if x.get("rhythm") or x.get("tempo")), None) or {}
        banks = all_banks if all_banks is not None else s.panel_banks(*slot)
        return {"rhythm": self.say(q.get("rhythm") or ""), "meter": q.get("meter") or "",
                "tempo": str(q["tempo"]) if q.get("tempo") else "", "model": self._model(slot, seq),
                "recorded": self._recorded(seq), "chord": self._chord_text(banks),
                "chord_short": self._chord_short(banks),
                "banks": " · ".join("%s: %s" % (b.label or b.number, self._bank_title(b))
                                    for b in banks if any(m.name for m in b.memories)),
                "inside": ", ".join(songdata.set_titles(banks))}

    def _model(self, slot: Slot, seq) -> str:
        return next((x["model"] for x in seq if x.get("model")), "") or ("KN5000" if self._kn5000(slot) else "")

    def _recorded(self, seq) -> str:
        if not seq:
            return ""
        return self.t("yes") if any(x.get("notes") for x in seq) else self.t("no")

    def _where_used(self, slot: Slot) -> List[Tuple[str, str]]:
        """The favourites and song lists that hold the song, as info rows."""
        s, t, rows = self.session, self.t, []
        favs = []
        for bi, bank in enumerate(s.db.favorites, 1):
            for pi, v in enumerate(bank.items, 1):
                dec = s.db.favorites[0].decode_item(v)
                if dec and dec[0] != "smf" and (dec[1] + 1, dec[2] + 1) == tuple(slot):
                    favs.append(t("info_fav_val", bank=bi, n=pi))
        if favs:
            rows.append((t("favorites"), ", ".join(favs)))
        lists = [str(n) for n, pl in enumerate(s.playlists(), 1) if tuple(slot) in [tuple(x) for x in pl]]
        if lists:
            rows.append((t("song_lists"), ", ".join(lists)))
        return rows

    def song_info(self, slot: Slot, banks: bool = True) -> Optional[Tuple[str, List[Tuple[str, str]]]]:
        """(name, [(label, value)]) for the info panel next to the songs: where it is, rhythm, time,
        tempo, whether something is recorded, and in which favourites and song lists it is. banks=False:
        without the Reg Bank and file rows (the panel shows those in sections of their own)."""
        s, t = self.session, self.t
        if s is None or not s.db.song(slot[0] - 1, slot[1] - 1).used:
            return None
        d = s.song_details(*slot)                        # only reads the small SQT file
        f = s.db.folders[slot[0] - 1]
        rows = [(t("info_where"), t("info_where_val", f=slot[0], name=f.name or t("noname"), n=slot[1]))]
        all_banks = s.panel_banks(*slot)
        x = self.song_facts(slot, d, all_banks)
        for key, label in (("rhythm", "info_rhythm"), ("meter", "info_meter"), ("tempo", "info_tempo"),
                           ("model", "info_model"), ("recorded", "info_recorded")):
            if x[key]:
                rows.append((t(label), x[key]))
        if all_banks and banks:                          # which Reg Banks the song brings, and what is in them
            rows.extend(self._bank_rows(all_banks))
        if x["chord"]:                                   # TRAX1 = fingered, 1FINGR = one finger, or a mix
            rows.append((t("info_chord"), x["chord"]))
        titles = s.set_titles(*slot)                     # a diskette's full set: the songs it has settings for
        if titles:
            rows.append((t("info_inside"), t("inside_n", n=len(titles), names=", ".join(titles))))
        rows += self._where_used(slot)
        if banks:
            rows.append((t("info_files"), " ".join(d["files"])))
        return str(d["name"]), rows

    NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")

    BASIC_GROUPS = ("style", "keys")         # what a player sets by hand; the rest only in "Uitgebreid"

    def settings_groups(self, settings, basic: bool = False) -> List[Tuple[str, List[Tuple[str, str, bool]]]]:
        """A panel memory's other settings (formats/panelsettings.py) as [(group heading, [(label, value,
        sure)])], in the order read. An on/off that belongs to a depth ("chorus" + "chorus_on") goes in
        the depth's value. basic: only the sure settings a player sets by hand (style and keyboard)."""
        t = self.t
        if basic:
            settings = [x for x in settings if x["sure"] and x["group"] in self.BASIC_GROUPS]
        switch = {(x["group"], x["key"][:-3]): x["value"] for x in settings if x["key"].endswith("_on")
                  and any(y["group"] == x["group"] and y["key"] == x["key"][:-3] for y in settings)}
        groups: Dict[str, List[Tuple[str, str, bool]]] = {}
        for x in settings:
            g, k = x["group"], x["key"]
            if k.endswith("_on") and (g, k[:-3]) in switch:
                continue
            if g == "seq":
                part, _, what = k.partition("_")
                label = t("set_seq_part", n=part[1:]) + ("" if not what else " " + t("set_volume"))
            else:
                label = t("set_" + k)
            value = self._setting_value(x)
            if (g, k) in switch:
                value += " (%s)" % t("on" if switch[(g, k)] else "off")
            groups.setdefault(g, []).append((label, value, bool(x["sure"])))
        return [(t("grp_" + g), rows) for g, rows in groups.items()]

    def _setting_value(self, x) -> str:
        t, v, fmt = self.t, x["value"], x["fmt"]
        if x["key"] == "sound" or (x["group"] == "seq" and isinstance(v, str)):
            prog, lsb, msb = (int(n) for n in str(v).split("/"))
            ps = songdata.PartSound("", prog, lsb, msb, 0)
            return songdata.sound_kind(ps) or t("sound_bank", msb=msb, lsb=lsb, n=prog + 1)
        if fmt == "onoff":
            return t("on" if v else "off")
        if fmt == "plus1":
            return str(v + 1)
        if fmt in ("signed", "signed24", "signed128"):
            n = v - {"signed": 64, "signed24": 24, "signed128": 128}[fmt]
            return "%+d" % n if n else "0"
        if fmt == "pan":
            n = v - 64
            return t("pan_centre") if n == 0 else ("%s %d" % (t("pan_left") if n < 0 else t("pan_right"), abs(n)))
        if fmt == "channel":
            return t("off") if v == 0xFF else str(v + 1)
        if fmt == "note":
            return "%s%d (%d)" % (self.NOTE_NAMES[v % 12], v // 12 - 1, v)
        return str(v)

    def _sounds_text(self, sounds) -> str:
        """"  ·  R1 Flute, R2 String Ensemble 1, L Warm Pad" for one button's parts. The GM name says what
        kind of sound it is; a bank we cannot name shows its numbers (bank 16, nr 5)."""
        parts = []
        for s in sounds:
            s = s if isinstance(s, songdata.PartSound) else songdata.PartSound(**s)
            kind = songdata.sound_kind(s) or self.t("sound_bank", msb=s.msb, lsb=s.lsb, n=s.program + 1)
            parts.append("%s %s" % (self.t("part_" + s.part), kind))
        return "  ·  " + ", ".join(parts) if parts else ""

    def _chord_text(self, banks) -> str:
        """"zelf spelen (fingered)", or for a mix of modes over the buttons: "gemengd: 4 knoppen één
        vinger (one finger), 4 knoppen zelf spelen (fingered)"."""
        count = songdata.chord_counts(banks)
        if len(count) <= 1:
            return "".join(self.t("chord_%d" % k) for k in count)
        parts = [self.t("chord_n_1" if count[k] == 1 else "chord_n", n=count[k], mode=self.t("chord_%d" % k)) for k in sorted(count)]
        return self.t("chord_mixed", parts=", ".join(parts))

    def _chord_short(self, banks) -> str:
        """The chord mode in a word or two, for a printed list: "zelf spelen", or "gemengd" when the buttons differ."""
        modes = sorted(songdata.chord_counts(banks))
        return self.t("chord_s_mixed") if len(modes) > 1 else "".join(self.t("chord_s_%d" % k) for k in modes)

    def _bank_rows(self, banks) -> List[Tuple[str, str]]:
        """Info panel rows for the song's Reg Banks: how it was saved, then per bank its name and how
        many of the 8 buttons hold a registration. Same layout for 3 BANK songs and full ALL sets."""
        t = self.t
        full = len(banks) > songdata.SONG_BANKS
        rows = [(t("info_saved_with"), t("saved_all", n=len(banks)) if full else t("saved_three"))]
        for b in banks:
            used = [m.name for m in b.memories if m.name]
            if not used:
                rows.append((t("info_bank", bank=b.label), t("bank_empty")))
                continue
            name = b.name or max(set(used), key=used.count)
            rows.append((t("info_bank", bank=b.label), t("bank_used", name=name, n=len(used))))
        return rows
