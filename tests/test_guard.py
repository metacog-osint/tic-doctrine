"""The guard blocks a term it holds only as a hash, in added lines and in file names."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from tic_doctrine import guard  # noqa: E402

# Built in two parts so this file does not itself trip the guard.
CANARY = "tic-guard-" + "canary"


class GuardTest(unittest.TestCase):
    def test_canary_is_in_the_shipped_list(self):
        self.assertIn(guard.digest(CANARY), guard.BLOCKED)

    def test_added_line_with_blocked_term_fails(self):
        diff = f"+++ b/notes.md\n@@ -0,0 +7,2 @@\n+a clean line\n+see {CANARY} here\n"
        hits = [(p, n) for p, n, text in guard.added_lines(diff) if guard.blocked(text)]
        self.assertEqual(hits, [("notes.md", 8)])

    def test_removed_line_is_ignored(self):
        diff = f"--- a/notes.md\n+++ b/notes.md\n@@ -3 +3 @@\n-see {CANARY} here\n+clean now\n"
        self.assertFalse([1 for _, _, text in guard.added_lines(diff) if guard.blocked(text)])

    def test_file_name_is_checked(self):
        diff = f"+++ b/docs/{CANARY}.md\n@@ -0,0 +1 @@\n+clean\n"
        hits = [(p, n) for p, n, text in guard.added_lines(diff) if guard.blocked(text)]
        self.assertEqual(hits, [(f"docs/{CANARY}.md", 0)])

    def test_drive_paths_normalise_across_forms(self):
        want = frozenset({guard.digest("q:/canaryfolder")})
        for line in ("q:\\canaryfolder\\x", "Q:/CanaryFolder/x", "q:\\\\canaryfolder", "cd /q/canaryfolder/x"):
            self.assertTrue(guard.blocked(line, want), line)

    def test_clean_text_passes(self):
        self.assertFalse(guard.blocked("https://example.com/a/b and ordinary words, 12:30 UTC"))


if __name__ == "__main__":
    unittest.main()
