"""The commands people type: kn-songboek (the app) and kn-songboek-cli. The old names are gone."""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class CommandNameTests(unittest.TestCase):
    def test_only_the_new_command_names(self):
        with open(os.path.join(ROOT, "pyproject.toml"), encoding="utf-8") as f:
            text = f.read()
        names = re.findall(r'^([\w-]+)\s*=\s*"kn_songboek\.[\w.]+:main"', text, re.M)
        self.assertEqual(sorted(names), ["kn-songboek", "kn-songboek-cli"])

    def test_help_shows_the_new_name(self):
        from kn_songboek.cli import main
        with self.assertRaises(SystemExit), open(os.devnull, "w") as null:
            import contextlib
            with contextlib.redirect_stdout(null), contextlib.redirect_stderr(null):
                main.main(["--help"])
        import inspect
        self.assertIn('prog="kn-songboek-cli"', inspect.getsource(main))


if __name__ == "__main__":
    unittest.main()
