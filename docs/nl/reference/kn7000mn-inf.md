# Referentie: KN7000MN.INF

*Bron: KN7000-programma build 941, geanalyseerd aan de hand van openbare documentatie.
Implementatie: `src/kn_songboek/formats/inf.py`.*

## Algemeen

- Grootte precies **0xD620 = 54.816 bytes**. Getallen zijn **little-endian** (MN10300-processor).
- Het keyboard houdt de hele inhoud in batterij-SRAM vanaf adres 0x50083D72 (`FAVORITES_SRAM`) en schrijft
  die na elke SD-wijziging ongewijzigd terug (`func_4855EB95` = begin, `func_4855EB9E` = 0xD620 bytes).
- **Laden** (`func_4856225F`): eerst 16 bytes lezen en de handtekening vergelijken (`func_4855EC0B`), daarna
  de overige 0xD610 bytes. Mislukt dat, dan dezelfde poging met `KN7000MN.BAK` (`func_485622FD`). Mislukt
  ook dat, dan bouwt het keyboard een lege database en scant de kaart (`func_4855F2F2`, `func_4855F56A`).
- **Opslaan** (`func_48562464`): index opnieuw opbouwen; als er ruimte is de oude INF hernoemen naar BAK
  (`func_48565DB1`); de nieuwe INF schrijven en teruglezen (`func_4856239B`). Mislukt het teruglezen, dan wordt
  de nieuwe INF verwijderd en blijft de oude als BAK staan. Lukt het, dan wordt de BAK overschreven met
  **dezelfde** nieuwe inhoud. Na een geslaagde save door het keyboard zijn INF en BAK dus identiek: de BAK is
  een reservekopie, geen vorige versie. Op een echte kaart die het laatst met een ander
  programma op de computer was bewerkt, was de BAK wél de vorige versie: één song meer, verder gelijk. Voor echte versiegeschiedenis maakt KN Songboek zelf back-ups (zie roadmap).

## Overzicht

| offset | grootte | inhoud | zekerheid |
|-------:|--------:|--------|-----------|
| 0x0000 | 0x10 | handtekening `KN7000 SDDIR INF` | zeker |
| 0x0010 | 99 × 0x1F0 | maprecords (map 1..99) | zeker |
| 0xBFE0 | 0x78 | 3 songlijsten × 20 × (u8 map, u8 song) | afgeleid |
| 0xC058 | 40 × 0x22 | favorietenbanken | zeker |
| 0xC5A8 | 0x100 | u16 `first_index[128]` | zeker |
| 0xC6A8 | 1980 × 2 | alfabetische lijst (u8 map, u8 song); lege plaatsen = `FF FF` | zeker (echte kaart) |
| 0xD620 | | einde | |

## Maprecord (0x1F0 bytes)

| +off | grootte | veld |
|----:|-----:|------|
| 0x00 | 16 | mapnaam, aangevuld met spaties (leeg: nullen) |
| 0x10 | 20 × 0x18 | songrecords |

Adres van map *f* (0-based): `0x10 + f × 0x1F0` (`func_4855EBBE`).

## Songrecord (0x18 bytes)

| +off | grootte | veld |
|----:|-----:|------|
| 0x00 | 16 | songnaam, aangevuld met spaties |
| 0x10 | 6 | bestands-base, bv. `001KN7`; leeg = standaard (`func_4855EEEB`) |
| 0x16 | u16 | typemasker, bit *i* = bestand met extensie *i* bestaat (`func_4855F599`, `func_4855F631`) |

Adres van song *s* in map *f*: `0x10 + f × 0x1F0 + 0x10 + s × 0x18` (`func_4855EBDA`). Een plaats is leeg als
het typemasker 0 is. Verwijderen wist naam, base en masker (`func_4855F02D`).

## Songlijsten (0xBFE0, 0x78 bytes)

Drie lijsten van maximaal 20 verwijzingen `(u8 map, u8 song)`, 0-based. `FF FF` sluit een lijst af.
Het keyboard voegt in op de cursorpositie (`func_485614F6`), verwijdert en schuift op (`func_485615EB`), en
haalt een song uit alle drie lijsten als hij wordt verwijderd (`func_4856169B`). Bewerkingen gebeuren in een
werkkopie op 0x5009231E die bij bevestigen wordt teruggezet (`func_485612A0`, `func_485612CD`).
*Afgeleid:* dit zijn de afspeellijsten voor Technics-songs; hun namen staan niet in dit bestand.

## Favorietenbank (0x22 bytes, 40 stuks)

| +off | grootte | veld |
|----:|-----:|------|
| 0x00 | 16 | naam |
| 0x10 | 9 × u16 | items |

Itemwaarde: `0` = leeg; `(map+1) << 8 | (song+1)` = Technics-song (`func_48561D0E`);
`0x8000 | n` = item *n* uit de SD-SOUND-lijst (`func_48561D34`). Bij verwijderen van een song worden
verwijzingen gewist (`func_48561E86`, `func_48561EF5`).

## Alfabetische index (0xC5A8 en 0xC6A8)

Opgebouwd vóór elke save (`func_48561785`, `func_48561960`):

1. Alle 1980 plaatsen worden gekopieerd naar records van 0x1A bytes (songrecord + map + song).
2. Sorteren met qsort; vergelijking `func_48561870`: voorloopspaties overslaan, dan byte voor byte als
   *signed char*, stoppen bij NUL.
3. De lijst bij 0xC6A8 krijgt `(map, song)` in gesorteerde volgorde, voor **alle** plaatsen. Lege plaatsen
   staan als `FF FF` in de lijst en sorteren vooraan, zodat de gebruikte songs het **einde** van de lijst
   vullen. Op de echte kaart (358 songs) staan er 1622 keer `FF FF` en daarna de 358 songs.
4. `first_index[c]` = absolute positie in die lijst van de eerste naam die met teken *c* begint (1..127),
   anders 0xFFFF; lege plaatsen tellen niet mee. Voorbeeld: `first_index['A'] = 1677`.
   Tekens 0x8B en 0x8D krijgen positie 126 en 127. Na afloop wordt `first_index[0]` op 0 gezet.

KN Songboek bouwt de index van de echte kaart byte voor byte gelijk na (INF en BAK). qsort is niet stabiel:
bij gelijke namen kan de volgorde in theorie afwijken van het keyboard. Dat is onschadelijk,
want het keyboard bouwt de index bij de volgende save zelf opnieuw op.

## Grenzen

99 mappen (`cmp 0x63`), 20 songs per map (`cmp 0x14`), 40 favorietenbanken, 9 items per bank,
999 SD-SOUND-items (`cmp 0x3E7`), namen 16 tekens.
