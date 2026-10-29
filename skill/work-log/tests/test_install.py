import os
import plistlib
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import SKILL_ROOT

INSTALL_SH = SKILL_ROOT.parent.parent / "install.sh"


class InstallBase(unittest.TestCase):
    """HOME and every tool install.sh asks about are stand-ins."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        self.stub("python3", 'case "$*" in *version_info\\ \\<*) exit 0;; *-V*) echo "Python 3.12.1";; esac\nexit 0\n')
        self.stub("osascript", "echo false\n")
        self.stub("swift", 'echo "swift must not run in these checks" >&2; exit 99\n')

    def stub(self, name: str, body: str) -> None:
        path = self.bin / name
        path.write_text(f"#!/bin/sh\n{body}", encoding="utf-8")
        path.chmod(0o755)

    def install(self, *args: str) -> subprocess.CompletedProcess:
        env = {"HOME": str(self.home), "PATH": f"{self.bin}:/usr/bin:/bin", "TMPDIR": str(self.tmp)}
        return subprocess.run(["zsh", str(INSTALL_SH), "--no-open", *args], env=env, capture_output=True,
                              text=True, timeout=60)


class InstallChecksTest(InstallBase):
    """Checks that stop install.sh before it builds anything."""

    def test_rejects_unsafe_prefix_values(self):
        for prefix in ("", "/", "-x"):
            with self.subTest(prefix=prefix):
                r = self.install("--prefix", prefix)
                self.assertEqual(r.returncode, 2, r.stderr)
                self.assertIn("--prefix", r.stderr)

    def test_old_python_on_the_run_path_stops_the_install(self):
        self.stub("python3", 'case "$*" in *-V*) echo "Python 3.9.6";; esac\nexit 1\n')
        r = self.install("--prefix", str(self.tmp / "Apps"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("Python 3.11", r.stderr)
        self.assertIn("Command Line Tools", r.stderr)
        self.assertFalse((self.tmp / "Apps").exists())

    def test_foreign_app_at_the_target_is_left_alone(self):
        app = self.tmp / "Apps" / "WorkLog.app" / "Contents"
        app.mkdir(parents=True)
        with open(app / "Info.plist", "wb") as f:
            plistlib.dump({"CFBundleIdentifier": "com.example.Other"}, f)
        r = self.install("--prefix", str(self.tmp / "Apps"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("com.example.Other", r.stderr)
        self.assertTrue((app / "Info.plist").exists())

    def test_running_collection_stops_the_install(self):
        self.stub("osascript", "echo true\n")
        (self.home / "Library" / "Logs" / "work-log" / ".lock").mkdir(parents=True)
        r = self.install("--prefix", str(self.tmp / "Apps"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("collection is running", r.stderr)



class InstallLinksTest(InstallBase):
    """Full runs with a stand-in build: swift reports a fake binary and codesign does nothing."""

    def setUp(self):
        super().setUp()
        build = self.tmp / "build"
        build.mkdir()
        (build / "WorkLog").write_text("#!/bin/sh\n", encoding="utf-8")
        (build / "WorkLog").chmod(0o755)
        self.stub("swift", f'case "$*" in *--show-bin-path*) echo "{build}";; esac\nexit 0\n')
        self.stub("codesign", "exit 0\n")
        self.apps = self.tmp / "Apps"
        self.links = [self.home / ".agents" / "skills" / "work-log", self.home / ".claude" / "skills" / "work-log"]

    def test_both_links_are_created_and_a_rerun_keeps_them(self):
        r = self.install("--prefix", str(self.apps))
        self.assertEqual(r.returncode, 0, r.stderr)
        for link in self.links:
            self.assertTrue(link.is_symlink(), link)
            self.assertEqual(Path(os.readlink(link)), SKILL_ROOT)
        self.assertTrue((self.apps / "WorkLog.app" / "Contents" / "MacOS" / "WorkLog").exists())
        again = self.install("--prefix", str(self.apps))
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertNotIn("Previous link target", again.stdout)
        for link in self.links:
            self.assertEqual(Path(os.readlink(link)), SKILL_ROOT)

    def test_a_link_pointing_elsewhere_is_replaced_and_its_target_printed(self):
        for i, link in enumerate(self.links):
            link.parent.mkdir(parents=True)
            link.symlink_to(self.tmp / f"old-{i}")
        r = self.install("--prefix", str(self.apps))
        self.assertEqual(r.returncode, 0, r.stderr)
        for i, link in enumerate(self.links):
            self.assertEqual(Path(os.readlink(link)), SKILL_ROOT)
            self.assertIn(f"Previous link target: {self.tmp / f'old-{i}'}", r.stdout)

    def test_a_real_directory_at_either_link_is_refused_before_any_change(self):
        for real in self.links:
            with self.subTest(real=real):
                for link in self.links:
                    if link.is_symlink():
                        link.unlink()
                (real / "keep").mkdir(parents=True)
                r = self.install("--prefix", str(self.apps))
                self.assertEqual(r.returncode, 1)
                self.assertIn(str(real), r.stderr)
                self.assertIn("not a symlink", r.stderr)
                self.assertTrue((real / "keep").is_dir())
                self.assertFalse(self.apps.exists())
                for link in self.links:
                    self.assertFalse(link.is_symlink(), link)
                (real / "keep").rmdir()
                real.rmdir()


if __name__ == "__main__":
    unittest.main()
