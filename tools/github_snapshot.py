"""Make or update the branch for GitHub: the code as it is now, without the history of this computer.

    python3 tools/github_snapshot.py [-m "message"] [--push] [SOURCE] [TARGET]      default: main → public

The local history (on main and other branches) keeps everything. The branch TARGET gets one new commit
with exactly the files of SOURCE; its parent is the previous TARGET commit, so GitHub sees an ordinary,
growing history that never contains the old local commits. With --push it goes to GitHub straight away,
where it is called main (on this computer `main` keeps the full history, so the names differ):

    git push -u origin public:main

The pre-push hook (tools/privacy_check.py --install) checks it before it leaves. Nothing on the working
folder changes: only a branch is made or moved.
"""
from __future__ import annotations

import os
import subprocess
import sys
from typing import List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IDENTITY = ["-c", "user.name=KN Songboek", "-c", "user.email=kn-songboek@localhost"]   # only when git has no name


def identity(root: str) -> List[str]:
    """Commit as the name and e-mail set in git for this repository (for GitHub: your user name and the
    private address GitHub gives you, NNN+name@users.noreply.github.com); a stand-in only when none is set."""
    r = subprocess.run(["git", "config", "user.email"], cwd=root, capture_output=True, text=True)
    return [] if r.stdout.strip() else IDENTITY


def git(*args: str, root: str = ROOT, check: bool = True) -> str:
    r = subprocess.run(["git", *identity(root), *args], cwd=root, capture_output=True, text=True)
    if check and r.returncode:
        raise SystemExit(r.stderr.strip() or "git %s failed" % args[0])
    return r.stdout.strip() if r.returncode == 0 else ""


def snapshot(source: str = "main", target: str = "public", message: Optional[str] = None,
             root: str = ROOT) -> Optional[str]:
    """The new TARGET commit, or None when TARGET already has exactly SOURCE's files."""
    tree = git("rev-parse", source + "^{tree}", root=root)
    parent = git("rev-parse", "--verify", "-q", "refs/heads/" + target, root=root, check=False)
    if parent and git("rev-parse", parent + "^{tree}", root=root) == tree:
        return None
    if message is None:
        message = git("log", "-1", "--format=%s", source, root=root) if parent else "Eerste versie"
    args = ["commit-tree", tree, "-m", message] + (["-p", parent] if parent else [])
    commit = git(*args, root=root)
    git("update-ref", "refs/heads/" + target, commit, *([parent] if parent else []), root=root)
    return commit


def main(argv: List[str]) -> int:
    message = None
    if "-m" in argv:
        i = argv.index("-m")
        message = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    push = "--push" in argv
    argv = [a for a in argv if a != "--push"]
    source = argv[0] if argv else "main"
    target = argv[1] if len(argv) > 1 else "public"
    commit = snapshot(source, target, message)
    if commit is None:
        print("De tak %s heeft al precies de bestanden van %s." % (target, source))
    else:
        print("Tak %s bijgewerkt (%s) met de bestanden van %s." % (target, commit[:7], source))
    command = ["git", "push", "-u", "origin", "%s:main" % target]
    if not push:
        print("Naar GitHub: " + " ".join(command) + "   (of dit script met --push)")
        return 0
    return subprocess.run(command, cwd=ROOT).returncode     # the privacy check runs first (pre-push hook)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
