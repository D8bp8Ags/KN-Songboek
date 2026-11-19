# Tutorial: eerste stappen

In deze les bekijk je de songs op je KN7000-kaart en hernoem je één song, zonder risico voor je kaart.
Tijd: 10 minuten. Nodig: Python 3.9 of nieuwer, een SD-kaartlezer en de KN7000-SD-kaart.

## 1. Installeren

```
cd KN-Songboek
pip install -e .            # of: pip install -e ".[gui]" voor de grafische versie
kn-songboek-cli --version
```

## 2. Een kopie van de kaart maken

Werk nooit direct op de enige kaart. Kopieer de hele kaart naar een map op je computer, bijvoorbeeld
`~/KN7000-kopie` (zie [how-to: kaart veilig kopiëren](../how-to/kaart-veilig-kopieren.md)).

## 3. Kijken wat erop staat

```
kn-songboek-cli ls ~/KN7000-kopie
```

Je ziet per map (TFLD001 …) de songs met hun nummer en de bestanden die erbij horen (SQT, PMT, …).

## 4. Controleren

```
kn-songboek-cli check ~/KN7000-kopie
```

`0 issue(s)` betekent dat database en bestanden overeenkomen.

## 5. Eerst proberen, dan doen

```
kn-songboek-cli rename-song ~/KN7000-kopie 1 2 "MY WAY" --dry-run
kn-songboek-cli rename-song ~/KN7000-kopie 1 2 "MY WAY"
kn-songboek-cli ls ~/KN7000-kopie
```

## 6. Terug naar het keyboard

Kopieer de map `PRIVATE` terug naar de kaart, steek de kaart in het keyboard en open SD LOAD. De song heet nu
"MY WAY". Klaar: je hebt je eerste wijziging gemaakt.

Volgende stap: [songs beheren](../how-to/songs-beheren.md).
