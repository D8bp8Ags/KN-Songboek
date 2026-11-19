# Referentie: indeling van de SD-kaart

*Bron: KN7000-programma build 941, strings in `data_02.s` (na adres 0x4868DE74) en de routines
genoemd per regel. Zekerheid: **zeker** tenzij anders vermeld.*

## Bestandssysteem

FAT16, door het keyboard geformatteerd (FORMAT SD). Het keyboard spreekt de kaart aan als station `C:`;
de diskette is `A:`.

## Mappen

| Pad | Inhoud | Bron |
|-----|--------|------|
| `\PRIVATE\TECHNICS\KN7000\KN7000MN.INF` | muziekdatabase, zie [kn7000mn-inf.md](kn7000mn-inf.md) | `func_48561023` |
| `\PRIVATE\TECHNICS\KN7000\KN7000MN.BAK` | reservekopie (na een save door het keyboard identiek aan de INF; op een echte kaart die met een ander programma was bewerkt was het de vorige versie), wordt geladen als de INF onleesbaar is | `func_4856102C`, `func_48562429` |
| `\PRIVATE\TECHNICS\KN7000\TFLD001` … `TFLD099` | de 99 mappen, elk maximaal 20 songs | `func_48560F53` |
| `\PRIVATE\TECHNICS\KN7000\CUSTOM\*.CST` | custom styles | `func_48561035` |
| `\IMEXPORT\` | import/export: SMF `*.MID`, `*.CST` | `func_4856107A` |
| `\DCIM\` | foto's van een camera (picture viewer) | `func_48561071` |
| `\PRIVATE\TECHNICS\DATA\` | SP-7001-plug-in: `BASEEXT.XAP`, `CTDV10KL.CDF` | openbare documentatie |
| `\SD_SOUND\` | SD-SOUND: lijstbestanden `SD_SOUND.PLM` (kop `S1SD-SOUND`, 2560 bytes) en `SD_SOUND.TKM` (kop `S4`, 8192 bytes); max. 999 items | echte kaart, `func_4855E867` |
| `\PRIVATE\TECHNICS\KN7000\*.LCK` | leeg vergrendelbestand van een ander programma; KN Songboek negeert het | echte kaart |

## Bestandsnamen van een Technics-song

```
\PRIVATE\TECHNICS\KN7000\TFLD<fff>\<ss><base>.<EXT>

fff   map 001..099
ss    plaats in de map 01..20
base  6 tekens uit het songrecord; leeg = "<fff>KN7"        (func_4855F04E)
EXT   één van de 14 typen hieronder                          (func_4852F882)

voorbeeld: \PRIVATE\TECHNICS\KN7000\TFLD001\02001KN7.SQT
```

Het songnummer staat **vooraan** (bevestigd op een echte kaart, 15-11-2026; tot versie 0.2 stond het
hier verkeerd om). De base reist mee met de song: een song die uit map 9 komt kan in TFLD017 staan als
`01009KN7.*`. Op de echte kaart kwamen ook eigen bases voor, zoals `SLUCIA` → `01SLUCIA.*`.

Een song is dus een **groep bestanden met dezelfde naam en verschillende extensies**. Welke er horen,
staat in het typemasker van het songrecord.

## De 14 bestandstypen

| bit | ext | inhoud | container | zekerheid |
|----:|-----|--------|-----------|-----------|
| 0 | LSW | huidig panel + per ritme 8 klankverwijzingen | `J KD`, 2 delen | zeker |
| 1 | PMT | panel memory-banken | `J KD` | zeker |
| 2 | SQT | sequencer-songs | `J KD`, 2 delen | zeker |
| 3 | CMP | composer-styles (TCMP) | `J KD` | zeker |
| 4 | TM | sound edit / custom sounds | `J KD` | zeker (echte kaart) |
| 5 | MSP | music-stylist pads (TPAD) | `J KD` | zeker |
| 6 | EFC | effect memory | `JK D` (zelfde opbouw en LZSS als `J KD`) | zeker (echte kaart) |
| 7 | MD | music-database-instellingen | `JK \0`, niet gecomprimeerd | zeker |
| 8 | FAV | favorieten | `JK \0` | zeker |
| 9 | HMP | homepage (0x18C-record + BMP 160×100) | `JK \0` | zeker |
| 10 | AST | custom data (de firmware noemt het RCM) | `J K\1`, deflate | zeker |
| 11 | SQF | wordt niet door de KN7000 zelf opgeslagen | onbekend | afgeleid |
| 12 | SEQ | wordt niet door de KN7000 zelf opgeslagen | onbekend | afgeleid |
| 13 | ACT | Slide Show (handleiding p.77): `SSW-ACT-V01`, `<SLIDESHOW>` met per USER-plaatje `<SSW NO=k IMG="…">`, optioneel `<ACTION>`-dia's; het keyboard schrijft hem bij elke sequencer-save, de plaatjes als JPG/BMP naast de song | tekst | zeker (echte kaart: 260 stuks, alle 42 bytes, zonder plaatjes) |

Het keyboard slaat bij **SD SAVE → TECHNICS FORMAT** deze 11 typen op, in deze volgorde (tabel
`func_48562906_Table_2`): EFC, TM, LSW, PMT, MSP, CMP, SQT, MD, FAV, HMP, AST. Vóór het overschrijven van
een plaats verwijdert het eerst alle bestanden waarvan de bit gezet is.

## Verwante pagina's

- [KN7000MN.INF byte voor byte](kn7000mn-inf.md)
- [Songbestanden en containers](songbestanden.md)
