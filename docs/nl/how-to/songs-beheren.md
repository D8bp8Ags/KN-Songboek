# How-to: songs hernoemen, verplaatsen, ordenen en verwijderen

Mappen 1–99, songs 1–20. Voeg `--dry-run` toe om eerst te zien wat er zou gebeuren.

| Taak | Opdracht |
|------|----------|
| Song hernoemen | `kn-songboek-cli rename-song KAART 3 5 "LA BAMBA"` |
| Map hernoemen | `kn-songboek-cli rename-folder KAART 3 "LATIN"` |
| Song naar map 7 (eerste vrije plaats) | `kn-songboek-cli move KAART 3 5 7` |
| Song naar map 7, plaats 1 | `kn-songboek-cli move KAART 3 5 7 1` |
| Song kopiëren | `kn-songboek-cli copy KAART 3 5 8` |
| Volgorde in een map wijzigen | `kn-songboek-cli swap KAART 3 1 5` |
| Hele map 1 naar map 20 | `kn-songboek-cli move-folder KAART 1 20` |
| Song verwijderen | `kn-songboek-cli delete KAART 3 5` |
| Zoeken | `kn-songboek-cli search KAART "WAY"` |

In de app sleep je een map in de mappenlijst, net als een nummer in een afspeellijst. Laat je hem los op de gele
lijn tussen twee mappen, dan komt hij daar te staan en schuiven de mappen ertussen één plaats op (opdrachtregel:
`kn-songboek-cli insert-folder KAART 8 3` zet map 8 vóór map 3). Laat je hem los op een lege map (geel kader), dan verhuist
hij daarheen met naam en alle songs op dezelfde plaatsen. Mappen ruilen kan alleen op de opdrachtregel
(`move-folder`). Het is steeds één stap die je met Ongedaan maken terugdraait.

Favorieten en songlijsten die naar een verplaatste song wijzen, worden automatisch aangepast. Bij verwijderen
worden ze gewist, net als op het keyboard.

## Dubbele songs opruimen

Wie ordent door songs naar meerdere mappen te kopiëren, heeft dezelfde song vaak een paar keer op de kaart.
Elke kopie kost ruimte en een van de 20 plaatsen in een map, en een aanpassing op het keyboard (tempo,
registraties, een opgenomen spoor) geldt alleen voor die ene kopie. Een favoriet of songlijst wijst naar
één song, dus dan speel je altijd de laatste versie.

```
kn-songboek-cli duplicates KAART                 # welke songs staan er meer dan eens op?
kn-songboek-cli dedupe KAART 12/3 --song-list 1  # 12/3 houden, kopieën weg, en 12/3 in songlijst 1 zetten
```

`duplicates` vergelijkt de bestanden byte voor byte. Songs met dezelfde naam maar een andere inhoud
(waarschijnlijk later aangepast) worden alleen getoond; die voegt KN Songboek nooit samen. In de grafische
versie: Extra → Dubbele songs…

In de grafische versie (`kn-songboek KAART`): selecteer een song en gebruik Rename (F2), Move (Ctrl+M) of
Delete. Undo (Ctrl+Z) werkt tot je op Save drukt.
