import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import SKILL_ROOT

BOOTSTRAP_SH = SKILL_ROOT.parent.parent / "bootstrap.sh"


class BootstrapTest(unittest.TestCase):
    """bootstrap.sh is fed on stdin like `curl … | zsh`; the repo is a local one whose install.sh only records its arguments."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        self.stub("xcode-select", "exit 0\n")
        self.calls = self.tmp / "install-calls"
        self.origin = self.tmp / "origin"
        self.git("init", "-q", "-b", "main", str(self.origin))
        self.commit("install.sh", f'#!/bin/zsh\nprint -r -- "${{0:A:h}} $*" >> "{self.calls}"\n', executable=True)
        self.target = self.home / ".local" / "share" / "work-log"

    def stub(self, name: str, body: str) -> None:
        path = self.bin / name
        path.write_text(f"#!/bin/sh\n{body}", encoding="utf-8")
        path.chmod(0o755)

    def git(self, *args: str, cwd: Path | None = None) -> str:
        env = {"HOME": str(self.home), "PATH": "/usr/bin:/bin", "GIT_CONFIG_NOSYSTEM": "1",
               "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}
        return subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True).stdout

    def commit(self, name: str, content: str, executable: bool = False) -> None:
        path = self.origin / name
        path.write_text(content, encoding="utf-8")
        if executable:
            path.chmod(0o755)
        self.git("add", name, cwd=self.origin)
        self.git("commit", "-q", "-m", f"add {name}", cwd=self.origin)

    def bootstrap(self, *args: str, url: str | None = None) -> subprocess.CompletedProcess:
        env = {"HOME": str(self.home), "PATH": f"{self.bin}:/usr/bin:/bin", "TMPDIR": str(self.tmp),
               "GIT_CONFIG_NOSYSTEM": "1", "WORKLOG_REPO_URL": url or str(self.origin)}
        return subprocess.run(["zsh", "-s", "--", *args], input=BOOTSTRAP_SH.read_text(encoding="utf-8"),
                              env=env, capture_output=True, text=True, timeout=60)

    def install_calls(self) -> list[str]:
        return self.calls.read_text(encoding="utf-8").splitlines() if self.calls.exists() else []

    def test_first_run_clones_into_the_install_folder_and_passes_arguments_on(self):
        r = self.bootstrap("--no-open", "--prefix", "/x/Apps")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.target / ".git").is_dir())
        self.assertEqual(self.install_calls(), [f"{self.target.resolve()} --no-open --prefix /x/Apps"])

    def test_rerun_fast_forwards_the_clone_before_installing(self):
        self.assertEqual(self.bootstrap().returncode, 0)
        self.commit("NEW", "new\n")
        r = self.bootstrap()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.target / "NEW").exists())
        self.assertEqual(len(self.install_calls()), 2)

    def test_folder_that_is_not_a_clone_of_the_repo_is_left_alone(self):
        other = self.tmp / "other"
        self.git("init", "-q", str(other))
        for setup in ("plain folder", "other clone"):
            with self.subTest(setup=setup):
                if setup == "plain folder":
                    (self.target / "keep").mkdir(parents=True)
                else:
                    self.git("clone", "-q", str(other), str(self.target))
                r = self.bootstrap()
                self.assertEqual(r.returncode, 1)
                self.assertIn(str(self.target), r.stderr)
                self.assertEqual(self.install_calls(), [])
                subprocess.run(["rm", "-rf", str(self.target)], check=True)

    def test_missing_command_line_tools_stops_before_cloning(self):
        self.stub("xcode-select", "exit 2\n")
        r = self.bootstrap()
        self.assertEqual(r.returncode, 1)
        self.assertIn("xcode-select --install", r.stderr)
        self.assertFalse(self.target.exists())


if __name__ == "__main__":
    unittest.main()
