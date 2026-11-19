"""Bundle README, docs/ (Diátaxis order), ROADMAP and CHANGELOG into one Markdown file.

    python tools/bundle_docs.py [OUTPUT]      default: KN7000-documentatie.md next to this repository
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORDER = [
    "README.md",
    "docs/README.md",
    "docs/nl/README.md",
    "docs/nl/handleiding.md",
    "docs/en/manual.md",
    "docs/nl/tutorials/eerste-stappen.md",
    "docs/nl/how-to/kaart-veilig-kopieren.md",
    "docs/nl/how-to/songs-beheren.md",
    "docs/nl/how-to/kaarten-samenvoegen.md",
    "docs/nl/how-to/back-up-en-herstel.md",
    "docs/nl/how-to/grafische-versie.md",
    "docs/nl/how-to/kaartimage.md",
    "docs/nl/how-to/bibliotheek.md",
    "docs/nl/reference/sd-kaart.md",
    "docs/nl/reference/kn7000mn-inf.md",
    "docs/nl/reference/songbestanden.md",
    "docs/nl/reference/cli.md",
    "docs/nl/reference/api.md",
    "docs/nl/explanation/architectuur.md",
    "docs/nl/explanation/reverse-engineering.md",
    "docs/nl/explanation/methodiek.md",
    "docs/nl/decisions/README.md",
]


def main(out=None):
    out = out or os.path.join(os.path.dirname(ROOT), "KN7000-documentatie.md")
    files = ORDER + sorted("docs/nl/decisions/" + f for f in os.listdir(os.path.join(ROOT, "docs/nl/decisions"))
                           if f[:4].isdigit()) + ["ROADMAP.md", "CHANGELOG.md"]
    parts = ["# KN7000 SD-database: alle documentatie\n\n*Gegenereerd uit de repository met tools/bundle_docs.py; "
             "bewerk de losse bestanden, niet dit bestand.*\n\n## Inhoud\n"]
    parts += ["- %s\n" % f for f in files]
    for f in files:
        with open(os.path.join(ROOT, f), encoding="utf-8") as fh:
            text = fh.read().strip()
        # demote headings one level so the bundle has a single H1
        text = "\n".join("#" + line if line.startswith("#") else line for line in text.splitlines())
        parts.append("\n\n---\n\n<!-- %s -->\n\n%s\n" % (f, text))
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("".join(parts))
    print(out)


if __name__ == "__main__":
    main(*sys.argv[1:])
