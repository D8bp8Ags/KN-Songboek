# Hoe het formaat is achterhaald

Het formaat van de muziekdatabase is niet gepubliceerd. Daarom is de **firmware van het keyboard** zelf als
bron gebruikt: wat het keyboard leest en schrijft, is per definitie juist.

## Bron

- Openbare documentatie van de KN7000-programma-ROM (MN10300, build 941), met namen en datatabellen.
- Openbare formaatdocumentatie (opslag, diskettecontainers, LZSS, panel memory, songs, styles).

Het SD-databasegedeelte was daarin **niet** beschreven. Alleen het SRAM-symbool
`FAVORITES_SRAM ('KN7000 SDDIR INF')` en de favorietenbanken waren benoemd.

## Werkwijze

1. Strings zoeken: `KN7000 SDDIR INF`, `C:\PRIVATE\TECHNICS\KN7000`, `KN7000MN.INF`, `TFLD`, `KN7`.
2. De routines volgen die deze strings gebruiken (`func_48561023` en verder) tot de lees- en schrijfroutines
   (`func_4856225F`, `func_48562464`): die lezen/schrijven 0xD620 bytes vanaf 0x50083D72.
3. Alle code zoeken die in dat geheugenbereik leest of schrijft, en per routine bepalen welke velden het gebruikt:
   - vermenigvuldigingen met 0x1F0 en 0x18 met grenzen 0x63 en 0x14 → 99 mappen × 20 songs;
   - 16 bytes kopiëren vanaf het begin van een record → naam;
   - 6 bytes vanaf +0x10 en de routine die `nnn` + `KN7` maakt → bestands-base;
   - een u16 op +0x16 die per bit getest wordt tegen een tabel met 14 extensies → typemasker;
   - `memset` bij formatteren: 0xBFE0, 0x78 (0xFF), 0x550, 0x1078 (0xFF) → de vier gebieden;
   - sorteerroutine + tabel van 128 u16 + 0x7BC paren → alfabetische index.
4. Controle: de som van alle gebieden is precies 0xD620; de prototype-code leest/schrijft dat byte-trouw.

## Zekerheid per onderdeel

| Onderdeel | Zekerheid | Opmerking |
|-----------|-----------|-----------|
| Grootte, handtekening, mappen, songrecords | zeker | direct in code |
| Bestandsnamen en 14 extensies | zeker | |
| Favorietenbanken en itemcodering | zeker | |
| Alfabetische index | zeker | echte kaart byte voor byte nagebouwd |
| Songlijsten bij 0xBFE0 | afgeleid | gedrag duidelijk; dat het de "playlists" zijn is afgeleid |
| Containers TM en EFC | zeker | TM = `J KD`, EFC = `JK D` (echte kaart) |
| SQF, SEQ, ACT | afgeleid | KN7000 schrijft ze niet zelf |
| Tekenset namen | deels | echte kaart: alleen ASCII; opvulling met spaties, `_` of nullen door elkaar |
| Map van SD-SOUND-bestanden en hun lijst | deels | `\SD_SOUND\SD_SOUND.PLM` en `.TKM`; inhoud nog niet ontleed |
| LZSS op echte bestanden | zeker | alle 2672 bestanden van een echte kaart uitgepakt; inpakken en weer uitpakken geeft hetzelfde |
| Bestandsnaam `<ss><base>` | zeker | echte kaart; in 0.2 stond het omgekeerd |
| KN6000-songs (`I KD`) | zeker | deflate; 43 songs op de echte kaart |
