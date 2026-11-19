import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

# Never write test back-ups into the user's real back-up folder.
import tempfile  # noqa: E402

os.environ["KN_SONGBOEK_BACKUP_DIR"] = tempfile.mkdtemp(prefix="kn_songboek-test-backups-")
