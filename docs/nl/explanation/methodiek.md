# Gekozen methodiek: documentatie en CLI + GUI

Dit document legt uit welke gangbare werkwijzen we volgen en waarom. Onderzocht op 15 november 2026.

## Documentatie

| Methode | Wat het is | Hoe wij het gebruiken |
|---------|-----------|------------------------|
| **Diátaxis** | Documentatie in vier soorten: tutorials (leren), how-to's (een taak doen), referentie (opzoeken), uitleg (begrijpen). Gebruikt door o.a. Canonical/Ubuntu, Django en NumPy. | Mappenstructuur van `docs/`. Elk document is één soort. |
| **arc42** | Sjabloon met 12 secties voor architectuurdocumentatie (doelen, randvoorwaarden, context, strategie, bouwstenen, runtime, …, risico's, begrippen). | `explanation/architectuur.md`, ingekort tot wat bij een klein project nuttig is. |
| **ADR / MADR** | Architecture Decision Records: per beslissing een kort document met context, keuze en gevolgen (Michael Nygard; Markdown-variant MADR). | `docs/nl/decisions/NNNN-titel.md`. |
| **Docs-as-code** | Documentatie in Markdown in dezelfde git-repository, mee in elke wijziging en review. | Alles in `docs/`; een wijziging aan het formaat zonder docs-update wordt niet geaccepteerd. |
| **Keep a Changelog + SemVer** | Een leesbaar `CHANGELOG.md` per versie (Added/Changed/Fixed); versienummers MAJOR.MINOR.PATCH. | `CHANGELOG.md`; versie in `pyproject.toml`. |
| **Bronvermelding per veld** | Gebruikelijk in reverse-engineeringprojecten: elk veld met adres en zekerheid. | Kolommen "Bron" en "zekerheid" in de referentie. |

**Waarom niet één groot document?** Iemand die snel een offset wil opzoeken, wil geen uitleg lezen, en een
beginner wil geen byte-tabellen. Diátaxis scheidt die behoeften. Voor wie toch alles in één bestand wil, maakt
`tools/bundle_docs.py` één samengevoegd document (`KN7000-documentatie.md`).

## CLI en GUI uit dezelfde kern

| Werkwijze | Wat het is | Hoe wij het gebruiken |
|-----------|-----------|------------------------|
| **Ports and adapters** (hexagonaal, Alistair Cockburn) | De applicatiekern kent alleen interfaces (*ports*); techniek zit in verwisselbare *adapters*. | `Storage`-protocol als port; map/geheugen/FAT-image als adapters; CLI en GUI als adapters aan de andere kant. |
| **Functionele kern, imperatieve schil** | Pure functies voor de logica, bijwerkingen aan de rand. | `formats/` is puur; alleen `storage/` doet I/O. |
| **Service-/use-caselaag** | Elke gebruikersactie is één methode in de kern; front-ends bevatten geen logica. | `CardSession`: `move_song`, `rename_song`, … |
| **Command-pattern** | Elke bewerking is een object dat terug te draaien is. | Snapshot + geplande bestandsoperaties per bewerking: undo, dry-run, voortgang. |
| **Model-View-Presenter** | Bij GUI's: de view is dom, de presenter beslist en is testbaar zonder scherm. Gangbaar bij Qt naast MVVM. | `gui/presenter.py` (getest met een nep-view) + `gui/qt_app.py`. |
| **Observer** | De kern meldt wijzigingen; de GUI luistert. | `CardSession.on_change`. |
| **CLI-richtlijnen (clig.dev)** | Subcommando's, `--help`, `--json` voor scripts, `--dry-run`, duidelijke exitcodes, fouten op stderr. | `cli/main.py`. |
| **src-layout + pyproject.toml** | Aanbevolen door de Python Packaging User Guide: code onder `src/`, zodat tests de geïnstalleerde versie testen. | `src/kn_songboek`, `pyproject.toml` met `kn_songboek` en `kn-songboek` als commando's. |

**Waarom PySide6?** Volwassen, native uiterlijk op Windows/macOS/Linux, goede tree/table-widgets voor 99 mappen
× 20 songs, slepen en neerzetten, LGPL-licentie en de officiële Qt-binding. Alternatieven: Tkinter (kaal, geen
installatie nodig), een lokale webinterface (FastAPI + browser; makkelijk op afstand, meer onderdelen), Textual
(terminal-GUI). Door de MVP-scheiding kan later een tweede front-end zonder de kern te wijzigen.

## Bronnen

- Diátaxis: https://diataxis.fr · https://ubuntu.com/blog/diataxis-a-new-foundation-for-canonical-documentation
- arc42: https://arc42.org/overview · https://docs.arc42.org/home/
- ADR: https://www.martinfowler.com/bliki/ArchitectureDecisionRecord.html · MADR: https://github.com/adr/madr
- Ports & adapters: https://herbertograca.com/2017/09/14/ports-adapters-architecture/
- Scheiding UI/logica en MVP/MVVM bij Qt: https://ics.com/blog/heres-why-you-should-separate-ui-business-logic-your-application · https://mantidproject.github.io/developer/MVPTutorial/Introduction.html
- src-layout: https://packaging.python.org/discussions/src-layout-vs-flat-layout/
- CLI-richtlijnen: https://clig.dev
- Keep a Changelog: https://keepachangelog.com · SemVer: https://semver.org
