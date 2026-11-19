"""Run every check in one go: ruff (lint), mypy (types of formats/ and storage/), privacy and the tests.

    python tools/check.py            all checks
    python tools/check.py --fast     skip the GUI tests (no PySide6 needed)
    uv run --extra dev --extra gui python tools/check.py      with uv, installs what is needed

A tool that is not installed is reported and skipped, so the script also works on a bare Python.
Set KN_SONGBOEK_REAL_CARD to a copy of a real card to include the real-card tests.
Exit code 0 only when everything that ran passed.
"""
import importlib.util
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def have(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def run(title: str, cmd, env=None) -> bool:
    print("\n== %s: %s" % (title, " ".join(cmd)), flush=True)
    ok = subprocess.run(cmd, cwd=ROOT, env=env).returncode == 0
    print("== %s: %s" % (title, "ok" if ok else "FAILED"), flush=True)
    return ok


def main(argv) -> int:
    fast = "--fast" in argv
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([os.path.join(ROOT, "src"), os.path.join(ROOT, "tests")]))
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    results = {}
    for title, module, cmd in (("lint", "ruff", [sys.executable, "-m", "ruff", "check"]),
                               ("types", "mypy", [sys.executable, "-m", "mypy"])):
        if have(module):
            results[title] = run(title, cmd)
        else:
            print("\n== %s: skipped (%s not installed; pip install %s)" % (title, module, module))
    results["privacy"] = run("privacy", [sys.executable, os.path.join(ROOT, "tools", "privacy_check.py")])
    if fast or not have("PySide6"):
        if not fast:
            print("\n== GUI tests skipped: PySide6 not installed")
        env["KN_SONGBOEK_NO_GUI_TESTS"] = "1"
    if have("pytest"):
        cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"]
    else:
        cmd = [sys.executable, "-m", "unittest", "discover", "-q", "-s", "tests", "-t", "tests"]
    results["tests"] = run("tests", cmd, env)
    print("\nSummary: " + ", ".join("%s %s" % (k, "ok" if v else "FAILED") for k, v in results.items()))
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
