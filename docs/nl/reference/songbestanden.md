# Referentie: songbestanden en containers

*Bron: openbare formaatdocumentatie (diskettebestanden, opslag); de SD-schrijfroutines
in programma 941 (`SavePmt_HD` e.d., `FmmSlideComp`). Implementatie: `src/kn_songboek/formats/container.py`.*

De SD-bestanden gebruiken dezelfde containers als de diskettebestanden van de KN7000. De eerste byte `J`
staat voor de KN7000 (de KN6000 gebruikt `I`).

Gevonden op een echte kaart (15-11-2026, 2672 songbestanden, alle zonder fouten uitgepakt):

| magic | bestanden | inhoud |
|-------|-----------|--------|
| `J KD` | CMP, PMT, MSP, TM, SQT, LSW | LZSS (hieronder) |
| `JK D` | EFC | precies als `J KD` met één deel |
| `I KD` / `IK D` | CMP, PMT, MSP, TM, SQT / EFC van KN6000-songs | zelfde koppen, elk deel raw deflate + adler32 |
| `ZZ\0\0` | LSW van KN6000-songs | onverpakt |
| `SSW-ACT-V01` | ACT | tekst (presentatiescript) |

De KN7000 speelt KN6000-songs (`I KD`) gewoon af; KN Songboek leest ze ook (`kind = "ID"`).

## `J KD`, één deel (CMP, PMT, MSP, TM; EFC als `JK D`)

| offset | type | veld |
|------:|------|------|
| 0x00 | 4 bytes | `J KD` |
| 0x04 | u16 big-endian | versie = 1 |
| 0x06 | u16 big-endian | flags (0) |
| 0x08 | u32 LE | 0 |
| 0x0C | u32 LE | uitgepakte grootte |
| 0x10 | … | LZSS-stroom |

## `J KD`, twee delen (SQT, LSW)

| offset | type | veld |
|------:|------|------|
| 0x08 | u32 LE | grootte deel 1 (uitgepakt) |
| 0x0C | u32 LE | grootte deel 2 |
| 0x10 | u32 LE | gecomprimeerde grootte deel 1 |
| 0x14 | u32 LE | gecomprimeerde grootte deel 2 |
| 0x18 | … | stroom 1, direct gevolgd door stroom 2 |

SQT-flags zijn 0x000F of 0x00F0.

## LZSS (`J KD`)

- Een vlagbyte, dan 8 items, laagste bit eerst. Bit 1 = één letterlijke byte.
- Bit 0 = verwijzing van 2 bytes `lo, hi`: ringpositie `lo | (hi >> 3) << 8` (13 bits, **absoluut**),
  lengte `(hi & 7) + 3` (3..10).
- Ring van 8192 bytes, gevuld met 0x00; de eerste byte wordt op 0x1FF6 geschreven.
- Geen eindmarkering: de header geeft de grootte.
- Technics gebruikte Okumura's LZSS.C (binaire zoekboom, N = 8192, F = 10, THRESHOLD = 2). Onze encoder
  (`formats/lzss_tree.py`) volgt hetzelfde algoritme, dus dezelfde keuzes bij gelijke treffers: uitpakken en
  opnieuw inpakken geeft **byte voor byte hetzelfde bestand** (zeker: gecontroleerd op alle `J KD`- en
  `JK D`-bestanden van een echte kaart, ook de header; test `RealCardEncoderTests`).

## `J K\1` (AST, CST)

`+4` u32 LE uitgepakte grootte. De stroom begint op 0x10 (AST) of 0x30 (CST; daarvoor een style-header).
Raw deflate van zlib 1.0.4, zonder de 2-byte zlib-header, gevolgd door een adler32 big-endian.

## `JK \0` (HMP, FAV, MD)

Niet gecomprimeerd.

## Inhoud (samenvatting)

- **SQT deel 1**: 1 of 10 songrecords van 0x8E0 bytes die met `ZZZZ` beginnen, met de 10-song-vlag en de
  modelhandtekening `01 0D`. Op +0xD0 een trackdirectory van 16 tracks, op +0x140 een volledige panel memory.
  **Deel 2**: cellen van 256 bytes (flags, vorige, volgende, 251 databytes) met de events.
- **SQT in detail** (zelf nagemeten op een echte kaart, gelezen door `formats/sqt.py`, CLI `show`):
  - deel 1, per song: `ZZZZ`, byte +4 = 1 als de song in gebruik is, +5 = `01 0D` (KN7000; `01 0A` =
    KN6000 met records van 0x870 bytes), op +0xD0 16 × {u8 flags, u16le eerste cel} (1-based, `FFFF` = leeg),
    op +0x100 de naam (16 tekens, `_` als nooit benoemd);
  - deel 2: een spoor is de keten van cellen vanaf zijn eerste cel (u16 op +3 = volgende, `FFFF` = laatste);
  - events: `81` = tel, `82` = einde spoor (zonder tickbyte); alle andere events zijn een tickbyte (0-95 binnen
    de tel) plus status: `80` tempo (+2), `84` maat, `85`/`86` ritme start/stop (+0), overige `8n` (+2),
    `9n` noot (+4: toets, aanslag, duur in ticks, duur in tellen), `An` partparameter (+6), `B0` controller (+3),
    `Cn` programma (+3), `Dn` aftertouch (+1), `En` pitch bend (+2), `F1`/`F2`/`F3` (+5/+6/+7);
  - op de kaart van de gebruiker (2026-11-15): 256 SQT's met alleen instellingen, 4 met opgenomen sporen
    (alle sporen compleet gelezen), 4 KN6000-SQT's zonder events.
- **Inhoud van de andere bestanden** (nagemeten op een echte kaart, 315 KN7000- en 43 KN6000-songs, alle
  zonder fouten gelezen door `formats/songdata.py`; CLI `show`, app: het paneel rechts):
  - **PMT** (na de container): `JK \0` (KN6000 `IK \0`), op +0x0C `P`; vanaf +0x10 3 banken van elk een
    banknaam (16 tekens) en 8 panel memories van 0x750 bytes (KN6000: 0x700). Een memory is een reeks
    tag/lengte-blokken tot `FF`, dezelfde als de panel memory in een SQT: `0x40` naam, `0x42` ritme en tempo
    (u16le op +8 van de data), `0x00`–`0x0F` parts, `0x10`–`0x12` R1/R2/L, `0x1B` akkoord, `0x1F` baspedaal.
  - **CMP**: `TCMP`, header van 0x70 bytes, dan 3 styles van 0x80 bytes: naam (16 bytes, 13 tekens gebruikt),
    4 variatienamen van 16 bytes, op +0x50 20 variatienummers; daarna 60 variaties van 0xE0 bytes en de
    eventstromen. Variatierecord *v* staat op 0x1F0 + 0xE0·*v* met op +0x10 maten − 1 en op +0x11 de maat
    (tellen − 1 in bit 0-2). Zie [Maatsoort](#maatsoort).
  - **MSP**: `TPAD`, header van 0x70 bytes, 5 banken van 0x30 bytes (naam, 6 pads van 3 bytes: nummer, soort,
    `0x10` = eigen pad), dan 18 eigen pads van 0x60 bytes die met hun naam beginnen.
  - **TM**: `KN7000 SOUND RAM` (of `KN6000`), 40 klanken van 0x2C8 bytes die met hun naam beginnen, daarna de
    eigen drumkit.
  - **HMP**: 0x18C-byte record + BMP van 160×100. *Niet op de echte kaart aanwezig: we halen de BMP eruit op
    zijn `BM`-kop, nog niet getest op een echt bestand.*
- **SD_SOUND** (`formats/sdsound.py`, CLI `sdsound`; betekenis nog niet bevestigd, de kaart had geen MIDI-bestanden):
  - `SD_SOUND.TKM`: 16 records van 0x200 bytes, `S4 00 00 00 01 00 03` en een naam van 16 tekens
    (`________________` = leeg; op de kaart namen als `020165GM`).
  - `SD_SOUND.PLM`: `S1SD-SOUND`, op 0x24 `S2 00 00`, daarna u16 big-endian tot `0000`: `80nn` (16 stuks, in een
    eigen volgorde) en `C0nn` (17 t/m 999), samen 999 plaatsen.
- **AST**: één volledig custom-data-image (IC21) na inflate.

## Maatsoort

Een song slaat geen maatsoort op. Die volgt uit het **ritme** dat in de panel memory van de song staat
(SQT-record +0x140, blok `0x42`): de eerste 3 bytes van dat blok zijn een 24-bitsgetal, little-endian
(tempo staat in hetzelfde blok op +8). Gelezen door `formats/rhythm.py`.

| bits 20-22 (bron) | onderste bits | waar de maat staat |
|---|---|---|
| 0 = ingebouwd ritme | style-ID (12 bits) | in de ritmetabel van het keyboard (`formats/rhythm_table.py`) |
| 1 = COMPOSER MEMORY | style 0-2 | in de eigen `.CMP` van de song: variatie 1 van die style, byte +0x11 |
| 2 = CUSTOM | slot 0-19 | in het interne flashgeheugen van het keyboard; **niet op de kaart**, dus onbekend |

- **Ingebouwde ritmes.** De firmware vouwt een style-ID tot indexpositie `((id & 0xF00) >> 1) | (id & 0x7F)`;
  die wijst naar een style in de ritme-ROM (IC18, 169 styles) of de table-ROM (51+1 styles), of één keer naar een
  andere positie. Elk variatierecord begint met *maten − 1* en *tellen − 1*. Alle 20 variaties van een style
  hebben hetzelfde aantal tellen.
- **Het keyboard kent alleen tellen per maat.** Van de 220 ritmes hebben er 15 drie tellen (de walsen: Waltz,
  German Waltz, Musette Waltz, Gospel 3/4, …), de rest vier. Ook "Polka 2/4", "USA March 6/8" en "Bossa 2/2"
  zijn als patronen van 4 tellen opgeslagen. KN Songboek toont daarom *tellen*/4, behalve als de ritmenaam zelf een
  maat noemt (dan die).
- **Opnames geven geen extra informatie.** Het SQT-event `84` (maat) komt in de opnames op de kaart van de
  gebruiker en in de fabriekssongs niet voor; alleen `81` (tel). Maten tellen uit de opname kan dus niet.
- **Bron.** De tabel is gegenereerd door `tools/gen_rhythm_table.py` uit de ritmedata van de KN7000,
  zoals beschreven in openbare documentatie.
  Alleen feiten (naam, aantal tellen, index) zijn overgenomen, geen code (ADR-0004). Gecontroleerd: alle 169
  IC18-styles en 52 table-ROM-verwijzingen geven via de index hun eigen naam terug. De rest is nog niet op de
  echte kaart nagemeten.
