"""tools/privacy_check.py: private info and card data are found, ordinary project text is not."""
import codecs
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import privacy_check as pc  # noqa: E402


def git(root, *args, stdin=None):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@localhost", *args], cwd=root,
                          input=stdin, capture_output=True, text=True, check=True).stdout


class RuleTests(unittest.TestCase):
    def test_card_files_are_found(self):
        for path in ("PRIVATE/TECHNICS/KN7000/KN7000MN.INF", "x/TFLD001/01001KN7.SQT", "a/b.LSW", "song.pmt",
                     "kaart.img", "backups/k.zip", ".coverage", "src/kn_songboek.egg-info/PKG-INFO", ".privacy-words"):
            self.assertTrue(pc.check_path(path), path)

    def test_ordinary_files_pass(self):
        for path in ("src/kn_songboek/formats/inf.py", "docs/nl/img/1-start.png", "README.md", "LICENSE"):
            self.assertEqual(pc.check_path(path), [], path)

    def test_private_text_is_found(self):
        for text in ("open /Volumes/Data/KN7000", "kopie: SD-kopie-2024-01-01", "mail jan@voorbeeld.nl",
                     "C:\\Users\\Piet\\Documents", "/Users/piet/Music", "/Volumes/KN7000/PRIVATE"):
            self.assertTrue(pc.check_text(text), text)
        for rot13 in (pc.OTHER_PROGRAMS, pc.OUTSIDE_SOURCES, pc.AI_TOOLS, pc.OLD_NAME):              # every name, also inside a sentence
            for name in codecs.decode(rot13, "rot13").split(","):
                text = "zoals %s ook doet" % name.lower()
                self.assertTrue(pc.check_text(text), text)

    def test_ordinary_text_passes(self):
        for text in ('return ["/Volumes"]', 'rename_volume("/Volumes/NO NAME", "feest")', "kn_songboek@localhost",
                     "Speler <1+speler@users.noreply.github.com>", "KN_SONGBOEK_REAL_CARD=/pad/naar/kaartkopie",
                     'MAGIC = b"KN7000 SDDIR INF"', "https://example.org/kn_songboek"):
            self.assertEqual(pc.check_text(text), [], text)

    def test_ai_tools_in_commits_and_pictures(self):
        tool, firm = codecs.decode(pc.AI_TOOLS, "rot13").split(",")
        trailer = "Co-Authored-By: %s <noreply@%s.com>" % (tool, firm.lower())
        self.assertTrue(pc.check_text(trailer))
        self.assertTrue(pc.check_text("Co-Authored-By: Iemand <1+iemand@users.noreply.github.com>"))
        self.assertTrue(pc.check_text("https://%s.ai/code/session_1" % tool.lower()))
        self.assertTrue(pc.check_blob("docs/x.png", b"\x89PNG\0\0" + firm.encode() + b"\0"))

    def test_png_metadata(self):
        def chunk(kind, body=b""):
            return len(body).to_bytes(4, "big") + kind + body + b"\0\0\0\0"
        clean = pc.PNG_MAGIC + chunk(b"IHDR", b"\0" * 13) + chunk(b"pHYs", b"\0" * 9) + chunk(b"IDAT", b"x") + chunk(b"IEND")
        self.assertEqual(pc.check_blob("docs/x.png", clean), [])
        tagged = clean[:-12] + chunk(b"tEXt", b"Software\0iets") + chunk(b"caBX", b"\0") + chunk(b"IEND")
        found = pc.check_blob("docs/x.png", tagged)
        self.assertEqual(len(found), 1)
        self.assertIn("tEXt, caBX", found[0])

    def test_own_words_and_card_bytes(self):
        self.assertTrue(pc.check_text("Gemaakt door Jansen", ["jansen"]))
        self.assertTrue(pc.check_blob("docs/img/x.png", b"\x89PNG\0\0KN7000 SDDIR INF\0"))
        self.assertEqual(pc.check_blob("docs/img/x.png", b"\x89PNG\0\0plaatje\0"), [])
        self.assertEqual(pc.check_blob(pc.SELF, b"SD-kopie-2024 /Volumes/Data/x"), [])     # itself
        self.assertTrue(pc.check_blob(pc.SELF, b"schijf Jansen", ["jansen"]))    # own words: also there
        self.assertTrue(pc.check_text("/Volumes/Jansen/x en Jansen1", ["jansen"]))
        self.assertEqual(pc.check_text("${jansenFolder}", ["jansen"]), [])        # part of a longer word


class GitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        git(self.root, "init", "-q")
        with open(os.path.join(self.root, "README.md"), "w") as f:
            f.write("schoon\n")
        git(self.root, "add", ".")
        git(self.root, "commit", "-qm", "begin")

    def tearDown(self):
        self.tmp.cleanup()

    def commit(self, name, text, msg="iets"):
        os.makedirs(os.path.dirname(os.path.join(self.root, name)) or self.root, exist_ok=True)
        with open(os.path.join(self.root, name), "w") as f:
            f.write(text)
        git(self.root, "add", name)
        git(self.root, "commit", "-qm", msg)
        return git(self.root, "rev-parse", "HEAD").strip()

    def test_tree_history_and_push(self):
        self.assertEqual(pc.check_tree(self.root), [])
        bad = self.commit("notes.md", "kaart in /Volumes/Data/KN7000\n")
        self.assertTrue(pc.check_tree(self.root))
        os.remove(os.path.join(self.root, "notes.md"))
        git(self.root, "commit", "-qam", "weg")
        self.assertEqual(pc.check_tree(self.root), [])                 # gone now ...
        head = git(self.root, "rev-parse", "HEAD").strip()
        commits = pc.pushed_commits(["refs/heads/main %s refs/heads/main %s" % (head, pc.ZERO)], self.root)
        self.assertIn(bad, commits)
        self.assertTrue(pc.check_commits(commits, self.root))          # ... but still in what a push sends
        self.assertEqual(pc.pushed_commits(["(delete) %s refs/heads/x %s" % (pc.ZERO, head)], self.root), [])

    def test_commit_message_and_own_words(self):
        with open(os.path.join(self.root, pc.WORDS_FILE), "w") as f:
            f.write("# eigen woorden\nPietersen\n")
        c = self.commit("a.txt", "ok\n", msg="voor Pietersen")
        self.assertTrue(any("bericht" in p for p in pc.check_commits([c], self.root)))

    def test_install_writes_the_hook(self):
        path = pc.install(self.root)
        with open(path) as f:
            self.assertIn("--pre-push", f.read())
        self.assertTrue(os.access(path, os.X_OK))


class RepositoryTest(unittest.TestCase):
    def test_this_repository_is_clean_now(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if not os.path.isdir(os.path.join(root, ".git")):
            self.skipTest("not a git checkout")
        self.assertEqual(pc.check_tree(root), [])


if __name__ == "__main__":
    unittest.main()
