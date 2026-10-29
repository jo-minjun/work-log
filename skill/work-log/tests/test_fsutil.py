import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import helpers  # noqa: F401  (puts scripts on sys.path)

import fsutil


class AtomicWriteTextTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)

    def test_creates_missing_parent_and_writes_owner_only(self):
        path = self.base / "a" / "b" / "file.json"
        fsutil.atomic_write_text(path, "hello")
        self.assertEqual(path.read_text(encoding="utf-8"), "hello")
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_failed_replace_leaves_old_file_and_no_temp(self):
        path = self.base / "file.json"
        path.write_text("old", encoding="utf-8")
        with mock.patch("fsutil.os.replace", side_effect=OSError("boom")), self.assertRaises(OSError):
            fsutil.atomic_write_text(path, "new")
        self.assertEqual(path.read_text(encoding="utf-8"), "old")
        self.assertEqual([p.name for p in self.base.iterdir()], ["file.json"])


if __name__ == "__main__":
    unittest.main()
