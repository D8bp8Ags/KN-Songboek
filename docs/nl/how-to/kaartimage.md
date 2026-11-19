# How-to: werken met een kaartimage (alleen opdrachtregel)

De app zelf werkt niet met kaartimages: voor de KN7000-speler zijn de back-ups in de app (Meer → Back-up
terugzetten) de manier om een kaart veilig te stellen. Dit is voor gevorderden die met de opdrachtregel werken.

Een kaartimage is één bestand met de hele kaart erin, byte voor byte. KN Songboek leest en schrijft zo'n bestand
direct: je hoeft niets te koppelen, en het origineel blijft ongemoeid tot je de image terugzet.

## Een image maken

**macOS** (Terminal; zoek eerst het schijfnummer van de kaart met `diskutil list`, hier `disk4`):

```
diskutil unmountDisk /dev/disk4
sudo dd if=/dev/rdisk4 of=~/KN7000-2026-11-15.img bs=1m
diskutil eject /dev/disk4
```

Controleer het schijfnummer twee keer: `dd` vraagt niets en kan ook je harde schijf lezen of overschrijven.
Schijfhulpprogramma kan het ook (Archief → Nieuwe image → Image van "kaart", formaat **lezen/schrijven**);
gecomprimeerde of alleen-lezen `.dmg`'s kan KN Songboek niet openen.

**Windows**: Win32 Disk Imager, knop *Read*. **Linux**: `sudo dd if=/dev/sdX of=kaart.img bs=1M`.

## Ermee werken

Alle opdrachten nemen in plaats van een map ook een imagebestand:

```
kn-songboek-cli info  KN7000-2026-11-15.img
kn-songboek-cli ls    KN7000-2026-11-15.img
kn-songboek-cli move  KN7000-2026-11-15.img 3 5 7
```

Back-ups, herstel en dubbele songs werken op de opdrachtregel hetzelfde als bij een map.

## Terugzetten op de kaart

Met dezelfde tools in omgekeerde richting (`dd if=kaart.img of=/dev/rdisk4`). Dat overschrijft de **hele**
kaart; maak dus eerst een image van de huidige stand.

## Wat wordt ondersteund

- FAT12, FAT16 en FAT32; een image van de hele kaart (met partitietabel) of van alleen het volume.
- Lange bestandsnamen worden gelezen. Nieuwe bestanden krijgen 8.3-namen, zoals het keyboard ze ook maakt.
- Schrijfvolgorde: eerst de data, dan de FAT, dan de mapregel. Valt de stroom halverwege weg, dan blijven
  hooguit losse clusters over (die `chkdsk`/`fsck` opruimt), geen bestanden met onzin.
- Getest tegen `mkfs.fat`, `fsck.fat` en mtools (zie `tests/test_fatimage.py`).
