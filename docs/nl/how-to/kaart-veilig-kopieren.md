# How-to: een SD-kaart veilig kopiëren

1. Schakel het keyboard uit en neem de kaart eruit.
2. Zet het schuifje op de kaart op **LOCK** (alleen lezen).
3. Steek de kaart in de kaartlezer en kopieer **de hele kaart** (alle mappen, ook `PRIVATE`) naar een nieuwe map,
   bijvoorbeeld `KN7000-kopie-2026-11-15`.
4. Maak ook een zip van die map en bewaar die apart. Dat is je terugvaloptie.
5. Controleer de kopie: `kn-songboek-cli check KN7000-kopie-2026-11-15`.
6. Werk alleen op de kopie. Zet het resultaat pas terug op de kaart (schuifje weer van LOCK) als `check` in orde is.

Tip voor gevorderden: een volledige schijfimage bewaart ook het FAT-formaat zelf; de opdrachtregel kan er direct
mee werken (de app niet). Zie [Werken met een kaartimage](kaartimage.md).
