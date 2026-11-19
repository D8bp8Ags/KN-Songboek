"""tools/github_snapshot.py: the GitHub branch has the files of main, but none of its history."""
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import github_snapshot as gs  # noqa: E402


def git(root, *args):
    return subprocess.run(["git", *gs.IDENTITY, *args], cwd=root, capture_output=True, text=True,
                          check=True).stdout.strip()


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        git(self.root, "init", "-q", "-b", "main")
        self.write("a.txt", "oud privé\n")
        git(self.root, "add", ".")
        git(self.root, "commit", "-qm", "oud")

    def test_commits_as_the_name_set_in_git(self):
        git(self.root, "config", "user.name", "Speler")
        git(self.root, "config", "user.email", "1+speler@users.noreply.github.com")
        gs.snapshot(root=self.root)
        self.assertEqual(git(self.root, "log", "-1", "--format=%an <%ae> %cn", "public"),
                         "Speler <1+speler@users.noreply.github.com> Speler")

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, text):
        with open(os.path.join(self.root, name), "w") as f:
            f.write(text)

    def test_first_and_next_snapshot(self):
        old = git(self.root, "rev-parse", "HEAD")
        self.write("a.txt", "schoon\n")
        git(self.root, "commit", "-qam", "schoon")
        first = gs.snapshot(root=self.root)
        self.assertEqual(git(self.root, "rev-list", "public"), first)              # one commit, no history
        self.assertEqual(git(self.root, "show", "public:a.txt"), "schoon")
        r = subprocess.run(["git", "merge-base", "--is-ancestor", old, "public"], cwd=self.root)
        self.assertNotEqual(r.returncode, 0)                                       # old commit not in it
        self.assertIsNone(gs.snapshot(root=self.root))                            # nothing changed
        self.write("b.txt", "nieuw\n")
        git(self.root, "add", ".")
        git(self.root, "commit", "-qm", "nieuw bestand")
        second = gs.snapshot(root=self.root)
        self.assertEqual(git(self.root, "rev-list", "public").split(), [second, first])
        self.assertEqual(git(self.root, "log", "-1", "--format=%s", "public"), "nieuw bestand")
        self.assertEqual(git(self.root, "rev-parse", "--abbrev-ref", "HEAD"), "main")   # still on main


if __name__ == "__main__":
    unittest.main()
