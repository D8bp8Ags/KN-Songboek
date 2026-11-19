"""MkDocs hooks: publish ROADMAP.md and CHANGELOG.md (which live in the repository root) with the docs,
and point the docs' links to them (`../ROADMAP.md`) at the published copies."""
import os
import re

from mkdocs.structure.files import File

ROOT_PAGES = ("ROADMAP.md", "CHANGELOG.md")


def on_files(files, config):
    root = os.path.dirname(os.path.abspath(config["config_file_path"]))
    for name in ROOT_PAGES:
        with open(os.path.join(root, name), encoding="utf-8") as fh:
            text = fh.read()
        text = re.sub(r"\]\(docs/", "](", text)                     # links into docs/ from the root
        files.append(File.generated(config, name, content=text))
    return files


def on_page_markdown(markdown, page, config, files):
    # docs/README.md links to ../ROADMAP.md; in the site that page sits next to ROADMAP.md
    depth = page.file.src_uri.count("/")
    for name in ROOT_PAGES:
        markdown = markdown.replace("](" + "../" * (depth + 1) + name, "](" + "../" * depth + name)
    return markdown
