"""Text: an English message with a key, for translation by a front end. Lives in the innermost
layer so formats and core can both use it."""
from __future__ import annotations


class Text(str):
    """An English message that also carries a key and its values, so a front end can say the same
    thing in its own language (gui/i18n.py has "err.<key>" and "step.<key>"). It is a str, so the CLI
    and logs keep working with the English text."""
    key: str
    values: dict

    def __new__(cls, key: str, english: str, **values):
        s = super().__new__(cls, english.format(**values))
        s.key, s.values = key, values
        return s
