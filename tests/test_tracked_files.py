import unittest

from scripts.check_tracked_files import blocked_file, contains_credential


class TrackedFilesTest(unittest.TestCase):
    def test_blocks_runtime_paths_and_recognizes_sqlite_contents(self):
        for path in ("snippets.json", "private/SNIPPETS.DB", ".env.production", "backup/data.sqlite3", ".pgpass"):
            self.assertTrue(blocked_file(path), path)
        for path in (".env.example", "vscode_extension/package-lock.json", "tests/synthetic.json"):
            self.assertFalse(blocked_file(path), path)
        self.assertTrue(contains_credential("renamed-data", b"SQLite format 3\x00"))

    def test_only_specific_dummy_connections_are_allowed(self):
        prefix = b"postgresql" + b"://"
        dummy = prefix + b"snippet_app:fixture-only@{url.hostname}:{url.port}/wp01_fixture"
        self.assertFalse(contains_credential("tests/test_authentication.py", dummy))
        self.assertTrue(contains_credential("other.py", dummy))
        self.assertTrue(contains_credential("tests/test_authentication.py", dummy + b"\n" +
                                            prefix + b"runtime:dummy-token@db.example.test/foo"))
        secret = b"sb_" + b"secret_" + b"x" * 25
        self.assertTrue(contains_credential(".env.example", secret))
