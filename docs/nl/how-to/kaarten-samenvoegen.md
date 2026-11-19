# How-to: twee kaarten samenvoegen

1. Maak van beide kaarten een kopie ([kaart veilig kopiëren](kaart-veilig-kopieren.md)).
2. Bekijk eerst wat er zou gebeuren:
   `kn-songboek-cli merge DOELKAART BRONKAART --dry-run`
3. Voer het uit: `kn-songboek-cli merge DOELKAART BRONKAART`
4. Controleer: `kn-songboek-cli check DOELKAART`

Elke song van de bronkaart komt in dezelfde map van de doelkaart, op de eerste vrije plaats. Is een map vol,
dan stopt het samenvoegen met een melding; verplaats dan eerst songs. Mapnamen van de bron worden overgenomen
als de doelmap nog geen naam heeft. Favorieten van de bronkaart worden (nog) niet meegenomen.
