# Meewerken aan KN Songboek

De app heet **KN Songboek**. Je start hem met `kn-songboek`; de opdrachtregel is `kn-songboek-cli`. De
Python-package heet `kn_songboek`.

## Opzetten

```bash
uv sync --extra gui --extra dev
uv run kn-songboek
```

## Controles

Draai alle controles vóór elke commit:

```bash
uv run python tools/check.py           # lint (ruff), types (mypy), privacycontrole en alle tests
uv run python tools/check.py --fast    # zonder de tests van het venster
```

Tests tegen een kopie van een echte kaart. Die kopie staat buiten de repository en komt er nooit in:

```bash
KN_SONGBOEK_REAL_CARD=/pad/naar/kaartkopie uv run python tools/check.py
```

## Regels

- **Nooit kaartinhoud in git.** Geen songbestanden, geen kaart- of diskette-images, geen songnamen van echte
  kaarten. Tests en schermafbeeldingen maken hun eigen demokaarten met verzonnen namen
  (`tools/make_screenshots.py`).
- **Geen privé-gegevens**, zoals eigen paden, namen of e-mailadressen.
- **Geen code van anderen overnemen.** Alle formaatcode is zelf geschreven (ADR-0004).
- Wijzigingen komen in [CHANGELOG.md](CHANGELOG.md). Plannen en afgevinkte punten staan in [ROADMAP.md](ROADMAP.md).

## Privacycontrole vóór elke push

Installeer de controle eenmalig. Daarna draait hij vóór elke `git push`:

```bash
python3 tools/privacy_check.py --install
```

Hij stopt de push als er kaart- of diskettebestanden, eigen paden, e-mailadressen of andere privé-dingen in
staan. Eigen woorden, zoals namen en kaartnamen, zet je in `.privacy-words` in de hoofdmap. Dat bestand gaat zelf
nooit mee. Je kunt de controle ook zelf starten:

```bash
python3 tools/privacy_check.py             # de bestanden zoals ze nu zijn
python3 tools/privacy_check.py --history   # alle commits
```

## Naar GitHub

De geschiedenis op de eigen computer gaat niet mee naar GitHub. De tak `public` krijgt alleen de bestanden van
`main`, zoals ze nu zijn, met één nieuwe commit per keer. Op GitHub heet die tak `main`:

```bash
python3 tools/github_snapshot.py -m "Wat er veranderd is" --push
```

Zonder `--push` wordt alleen de tak bijgewerkt; pushen is dan `git push -u origin public:main` (links de tak
hier, rechts de naam op GitHub). De privacycontrole draait vóór elke push.

De commits op GitHub krijgen de naam en het e-mailadres die in git voor deze map staan. Gebruik als e-mail het
privé-adres dat GitHub je geeft (*Settings › Emails*), dan blijft je echte adres verborgen:

```bash
git config user.name "jouw-github-naam"
git config user.email "NNN+jouw-github-naam@users.noreply.github.com"
```

## De app bouwen (.app en .exe)

GitHub bouwt de app zelf bij elke push naar `main` (`.github/workflows/build.yml`): eerst de controles op macOS
en Windows, dan de app voor Mac (Apple-chip en Intel) en Windows, en daarna een korte proef of de gebouwde app
start en de handleiding vindt. De bestanden staan bij *Actions* › de run › *Artifacts* (alleen met een
GitHub-account). Een uitgave voor iedereen: *Actions* › *Bouwen en testen* › *Run workflow* met het vinkje
*Uitgave maken*, of een tag zoals `v0.3.0`. Dan komen de bestanden op de *Releases*-pagina, met uitleg voor
het openen. Verhoog eerst `__version__` in `src/kn_songboek/__init__.py`.

Zelf bouwen kan ook, op de computer waarvoor je bouwt (een Mac bouwt geen .exe):

```bash
pip install ".[gui]" pyinstaller pillow
python tools/build_app.py --zip      # resultaat in dist/
```

## Documentatie

- Handleiding voor gebruikers: [docs/nl/handleiding.md](docs/nl/handleiding.md) en [docs/en/manual.md](docs/en/manual.md)
- Alles over het kaartformaat: [docs/nl/reference](docs/nl/reference)
- Architectuur en besluiten: [docs/nl/explanation](docs/nl/explanation) en [docs/nl/decisions](docs/nl/decisions)
- Als website: `uv run --extra docs mkdocs serve`
