# How-to: back-ups maken en terugzetten

KN Songboek maakt **vóór elke wijziging automatisch een back-up**: een zip van de map `PRIVATE/TECHNICS/KN7000`
(database en alle songs). De back-ups staan op je computer, niet op de kaart:

- macOS: `~/Library/Application Support/KN Songboek/backups/<kaartnaam>/`
- Linux: `~/.local/share/KN Songboek/backups/<kaartnaam>/`
- Windows: `%APPDATA%\KN Songboek\backups\<kaartnaam>\`

Een andere plek kies je met `--backup-dir MAP` of de omgevingsvariabele `KN_SONGBOEK_BACKUP_DIR`. Per kaart
blijven de laatste 10 bewaard (`--keep N`, 0 = alles bewaren). Hebben twee kaarten dezelfde naam (zoals
`NO NAME`), dan delen ze een map, maar het opruimen telt alleen back-ups met grotendeels dezelfde songs: de
back-ups van de andere kaart blijven staan. Een oude bibliotheekkopie die vervangen is, staat in
`<naam>-bibliotheek/`.

In de app: **Meer… → Back-ups…** toont alle back-ups met hun inhoud, en kan terugzetten op de open kaart, als
nieuwe kaart beginnen (om op een andere of lege kaart te zetten) of de back-up in de bibliotheek zetten.

## Zelf een back-up maken

```
kn-songboek-cli backup KAART
```

## Back-ups bekijken

```
kn-songboek-cli backups KAART
 1  2026-11-15 10:12:03   120 songs  …/KN7000-20261115-101203.zip
 2  2026-11-15 09:58:40   118 songs  …
```

## Een back-up terugzetten

1. Kijk eerst wat er gebeurt: `kn-songboek-cli restore KAART 2 --dry-run`
2. Zet terug: `kn-songboek-cli restore KAART 2`

Vóór het terugzetten maakt KN Songboek eerst een back-up van de huidige stand, dus ook een restore is
terug te draaien. Songbestanden die niet in de back-up zitten worden verwijderd; de rest van de kaart
(foto's, SD_SOUND) blijft onaangeroerd.

## De database herstellen uit de bestanden

Als `kn-songboek-cli check` fouten meldt (bijvoorbeeld na een onderbroken save of na handwerk op de computer):

```
kn-songboek-cli repair KAART --dry-run     # kijken wat er zou veranderen
kn-songboek-cli repair KAART               # uitvoeren (met back-up vooraf)
```

Songnamen komen uit de vorige database. KN7000-songbestanden bevatten zelf geen naam; een song die nergens
meer in een database stond, krijgt daarom de naam `SONG fff-ss`, die je daarna hernoemt.

## Een logboek bijhouden

```
kn-songboek-cli --log ~/kn-songboek.log move KAART 1 2 5
```

Elke bestandsoperatie komt met datum en tijd in het logboek.

## Controles vóór het schrijven

KN Songboek begint niet aan een wijziging als de kaart **schrijfbeveiligd** is (schuifje op LOCK) of als er
**te weinig ruimte** is. `kn-songboek-cli info KAART` toont vrije ruimte, aantal songs en waar de back-ups staan.
