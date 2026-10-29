import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import date
from pathlib import Path

from helpers import SCRIPTS, SKILL_ROOT, cli_env

from runlog import report_summary, summarize

FIXTURES = SKILL_ROOT.parent.parent / "fixtures"
RUN_SH = SCRIPTS / "run.sh"
CODEX_TOKENS = 24763 + 122 + 30100 + 478
EXPECTED_KEYS = ["startedAt", "endedAt", "trigger", "provider", "result", "reason", "costUsd", "tokens", "summary", "logPath"]


class SummarizeTest(unittest.TestCase):
    def test_summarize_claude_fixture(self):
        self.assertEqual(
            summarize("claude", FIXTURES / "claude-result.json"),
            {"costUsd": 0.97, "tokens": None, "summary": "Wrote 2 days to the monthly log.", "isError": False},
        )

    def test_summarize_codex_fixture(self):
        self.assertEqual(
            summarize("codex", FIXTURES / "codex-events.jsonl"),
            {"costUsd": None, "tokens": CODEX_TOKENS, "summary": "Wrote 2 days to the monthly log.",
             "isError": False},
        )

    def test_summarize_missing_output_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            for provider in ("claude", "codex"):
                self.assertTrue(summarize(provider, Path(tmp) / "none")["isError"])

    def test_summarize_codex_failed_turn_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "events.jsonl"
            out.write_text('{"type":"turn.failed","error":{"message":"x"}}\n', encoding="utf-8")
            self.assertTrue(summarize("codex", out)["isError"])

    def test_summary_is_the_first_report_line_without_markdown(self):
        self.assertEqual(report_summary("\n## **10/29** collected, `0` warnings.\n\n| table |"), "10/29 collected, 0 warnings.")
        self.assertEqual(len(report_summary("x" * 500)), 200)
        self.assertIsNone(report_summary(None))

    def test_fixture_runs_use_spec_keys(self):
        for line in (FIXTURES / "runs.jsonl").read_text(encoding="utf-8").splitlines():
            self.assertEqual(list(json.loads(line)), EXPECTED_KEYS)


class RunShTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.stubs = self.tmp / "bin"
        self.stubs.mkdir()
        self.logs = self.tmp / "logs"
        self.env = {
            **cli_env(self.tmp),
            "WORKLOG_LOG_DIR": str(self.logs),
            "WORKLOG_PATH": f"{self.stubs}:{Path(sys.executable).parent}:/usr/bin:/bin",
            "WORKLOG_TRIGGER": "schedule",
        }

    def write_settings(self, folder: Path, provider: str) -> None:
        folder.mkdir(parents=True)
        (self.home / "settings.json").write_text(
            json.dumps({"logFolder": str(folder), "provider": provider}), encoding="utf-8"
        )

    def run_sh(self) -> subprocess.CompletedProcess:
        return subprocess.run(["zsh", str(RUN_SH)], env=self.env, capture_output=True, text=True, timeout=60)

    def run_lines(self) -> list[str]:
        return (self.home / "runs.jsonl").read_text(encoding="utf-8").splitlines()

    def last_run(self) -> dict:
        lines = self.run_lines()
        self.assertEqual(len(lines), 1)
        return json.loads(lines[-1])

    def write_stub(self, name: str, body: str) -> None:
        stub = self.stubs / name
        stub.write_text(f"#!/bin/sh\n{body}", encoding="utf-8")
        stub.chmod(0o755)

    def test_run_sh_with_space_in_log_folder(self):
        self.write_settings(self.tmp / "My Vault" / "log", "claude")
        stub = self.stubs / "claude"
        stub.write_text(
            f'#!/bin/sh\npython3 "{SCRIPTS}/state.py" record-write\ncat "{FIXTURES}/claude-result.json"\n',
            encoding="utf-8",
        )
        stub.chmod(0o755)
        proc = self.run_sh()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        record = self.last_run()
        self.assertEqual(list(record), EXPECTED_KEYS)
        self.assertEqual((record["result"], record["provider"], record["trigger"]), ("succeeded", "claude", "schedule"))
        self.assertEqual((record["costUsd"], record["summary"]), (0.97, "Wrote 2 days to the monthly log."))

    def test_run_sh_fails_when_nothing_was_written(self):
        self.write_settings(self.tmp / "vault", "claude")
        stub = self.stubs / "claude"
        stub.write_text(f'#!/bin/sh\ncat "{FIXTURES}/claude-result.json"\n', encoding="utf-8")
        stub.chmod(0o755)
        proc = self.run_sh()
        self.assertEqual(proc.returncode, 1, proc.stderr)
        record = self.last_run()
        self.assertEqual((record["result"], record["reason"]), ("failed", "Nothing was written during this run"))

    def test_run_sh_lock_busy_records_skipped(self):
        self.write_settings(self.tmp / "vault", "claude")
        (self.logs / ".lock").mkdir(parents=True)
        marker = self.tmp / "invoked"
        self.write_stub("claude", f'touch "{marker}"\n')
        proc = self.run_sh()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        record = self.last_run()
        self.assertEqual((record["result"], record["reason"]), ("skipped", "Another run is in progress"))
        self.assertEqual((record["provider"], record["trigger"]), ("claude", "schedule"))
        self.assertEqual((record["costUsd"], record["tokens"], record["summary"]), (None, None, None))
        self.assertFalse(marker.exists())

    def test_run_sh_record_write_failure_exits_1(self):
        self.write_settings(self.tmp / "vault", "claude")
        (self.home / "runs.jsonl").mkdir()
        self.write_stub(
            "claude", f'python3 "{SCRIPTS}/state.py" record-write\ncat "{FIXTURES}/claude-result.json"\n'
        )
        proc = self.run_sh()
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertIn("run record write failed", (self.logs / "run.log").read_text(encoding="utf-8"))

    def test_run_sh_codex_passes_skill_name_unexpanded(self):
        self.write_settings(self.tmp / "vault", "codex")
        stub = self.stubs / "codex"
        stub.write_text(
            f'#!/bin/sh\nprintf "%s\\n" "$@" > "{self.tmp}/args"\n'
            f'python3 "{SCRIPTS}/state.py" record-write\ncat "{FIXTURES}/codex-events.jsonl"\n',
            encoding="utf-8",
        )
        stub.chmod(0o755)
        proc = self.run_sh()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual((self.tmp / "args").read_text(encoding="utf-8").splitlines()[-1], "$work-log")
        self.assertEqual(self.last_run()["tokens"], CODEX_TOKENS)

    def recording_claude(self, extra: str = "") -> Path:
        """A claude stub that saves its arguments and working directory, then reports a write."""
        record = self.tmp / "claude-call"
        self.write_stub("claude", f'printf "%s\\n" "$@" > "{record}.args"\npwd > "{record}.cwd"\n{extra}'
                                  f'python3 "{SCRIPTS}/state.py" record-write\ncat "{FIXTURES}/claude-result.json"\n')
        return record

    def test_claude_runs_with_dont_ask_and_absolute_script_rules(self):
        folder = self.tmp / "vault"
        self.write_settings(folder, "claude")
        record = self.recording_claude()
        proc = self.run_sh()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        args = (record.parent / "claude-call.args").read_text(encoding="utf-8").splitlines()
        cwd = (record.parent / "claude-call.cwd").read_text(encoding="utf-8").strip()
        self.assertEqual(args[args.index("--permission-mode") + 1], "dontAsk")
        scripts = SCRIPTS.resolve()
        for script in ("settings", "state", "write_day", "extract_sessions", "suggestions"):
            self.assertIn(f"Bash(python3 {scripts}/{script}.py:*)", args)
        for rule in ("Read", "Skill(work-log)", f"Edit(/{folder.resolve()}/**)", f"Edit(/{cwd}/**)",
                     "mcp__plugin_slack_slack__slack_read_thread"):
            self.assertIn(rule, args)
        for banned in ("Bash(python3:*)", "Bash(cp:*)", "Bash(S=*)", "Edit", "Bash"):
            self.assertNotIn(banned, args)
        context = args[args.index("--append-system-prompt") + 1]
        self.assertIn(str(scripts), context)
        self.assertIn(cwd, context)

    def test_provider_runs_in_a_fresh_directory_that_is_removed(self):
        self.write_settings(self.tmp / "vault", "claude")
        marker = self.tmp / "planted-module-ran"
        # A provider that can write its working directory plants a module the post-run python would import
        record = self.recording_claude(f'echo \'open("{marker}", "w")\' > json.py\n')
        proc = self.run_sh()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        cwd = Path((record.parent / "claude-call.cwd").read_text(encoding="utf-8").strip())
        self.assertNotEqual(cwd.resolve(), self.logs.resolve())
        self.assertFalse(cwd.exists())
        self.assertFalse(marker.exists())

    def test_stopped_run_removes_its_working_directory(self):
        # The app stops a run with SIGTERM to the process group, removes the lock and records the stop itself
        for sig, lock_left in ((signal.SIGTERM, True), (signal.SIGINT, False)):
            with self.subTest(sig=sig.name):
                shutil.rmtree(self.tmp / "vault", ignore_errors=True)
                shutil.rmtree(self.logs, ignore_errors=True)
                (self.home / "runs.jsonl").unlink(missing_ok=True)
                self.write_settings(self.tmp / "vault", "claude")
                cwd_file = self.tmp / "claude-call.cwd"
                cwd_file.unlink(missing_ok=True)
                self.write_stub("claude", f'pwd > "{cwd_file}.tmp" && mv "{cwd_file}.tmp" "{cwd_file}"\nsleep 30\n')
                proc = subprocess.Popen(["zsh", str(RUN_SH)], env=self.env, start_new_session=True,
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                deadline = time.monotonic() + 20
                while not cwd_file.exists() and time.monotonic() < deadline:
                    time.sleep(0.05)
                self.assertTrue(cwd_file.exists(), "the provider never started")
                cwd = Path(cwd_file.read_text(encoding="utf-8").strip())
                self.assertTrue(cwd.is_dir())
                os.killpg(proc.pid, sig)
                proc.wait(timeout=20)
                self.assertFalse(cwd.exists())
                self.assertEqual((self.logs / ".lock").exists(), lock_left)
                self.assertFalse((self.home / "runs.jsonl").exists())

    def test_logs_and_data_are_private(self):
        self.write_settings(self.tmp / "vault", "claude")
        self.recording_claude()
        self.assertEqual(self.run_sh().returncode, 0)
        for d in (self.logs, self.home):
            self.assertEqual(stat.S_IMODE(d.stat().st_mode), 0o700, d)
        for f in [*self.logs.glob("*.json"), *self.logs.glob("*.err"), self.home / "runs.jsonl"]:
            self.assertEqual(stat.S_IMODE(f.stat().st_mode), 0o600, f)

    def test_log_folder_must_be_dedicated(self):
        for folder in (Path.home(), self.tmp, Path("/")):
            with self.subTest(folder=folder):
                (self.home / "runs.jsonl").unlink(missing_ok=True)
                (self.home / "settings.json").write_text(
                    json.dumps({"logFolder": str(folder), "provider": "claude"}), encoding="utf-8")
                marker = self.tmp / "invoked"
                self.write_stub("claude", f'touch "{marker}"\n')
                proc = self.run_sh()
                self.assertEqual(proc.returncode, 1, proc.stderr)
                self.assertEqual(self.last_run()["reason"], "Log folder must be a dedicated folder")
                self.assertFalse(marker.exists())

    def test_default_log_folder_is_created_private(self):
        fake_home = self.tmp / "user"
        fake_home.mkdir()
        self.env["HOME"] = str(fake_home)
        (self.home / "settings.json").write_text(json.dumps({"provider": "claude"}), encoding="utf-8")
        self.recording_claude()
        proc = self.run_sh()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        folder = fake_home / "WorkLog"
        self.assertTrue(folder.is_dir())
        self.assertEqual(stat.S_IMODE(folder.stat().st_mode), 0o700)

    def test_missing_chosen_log_folder_is_not_created(self):
        folder = self.tmp / "chosen"
        (self.home / "settings.json").write_text(json.dumps({"logFolder": str(folder), "provider": "claude"}),
                                                 encoding="utf-8")
        self.recording_claude()
        proc = self.run_sh()
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertEqual(self.last_run()["reason"], "Log folder not accessible")
        self.assertFalse(folder.exists())

    def test_old_logs_are_pruned_and_text_logs_trimmed(self):
        self.write_settings(self.tmp / "vault", "claude")
        self.recording_claude()
        self.logs.mkdir()
        now = time.time()
        for name, age_days in (("old.json", 8), ("old.err", 7.5), ("recent.json", 6.5)):
            path = self.logs / name
            path.write_text("x", encoding="utf-8")
            os.utime(path, (now - age_days * 86400, now - age_days * 86400))
        line = "x" * 600
        for name in ("run.log", "app-runner.log"):
            (self.logs / name).write_text("".join(f"{i} {line}\n" for i in range(2000)), encoding="utf-8")
        self.assertEqual(self.run_sh().returncode, 0)
        self.assertEqual(sorted(p.name for p in self.logs.glob("old.*")), [])
        self.assertTrue((self.logs / "recent.json").exists())
        for name in ("run.log", "app-runner.log"):
            lines = (self.logs / name).read_text(encoding="utf-8").splitlines()
            self.assertLessEqual(len(lines), 1005, name)
            self.assertIn(f"1999 {line}", lines)
            self.assertNotIn(f"999 {line}", lines)

    def test_old_python_stops_before_anything_runs(self):
        self.write_settings(self.tmp / "vault", "claude")
        self.write_stub("python3", "exit 1\n")
        marker = self.tmp / "invoked"
        self.write_stub("claude", f'touch "{marker}"\n')
        proc = self.run_sh()
        self.assertEqual(proc.returncode, 1)
        self.assertIn("Python 3.11", (self.logs / "run.log").read_text(encoding="utf-8"))
        self.assertFalse((self.home / "runs.jsonl").exists())
        self.assertFalse(marker.exists())

    def test_day_written_with_warnings_is_reported(self):
        folder = self.tmp / "vault"
        self.write_settings(folder, "claude")
        day = self.tmp / "day.json"
        day.write_text(json.dumps({"date": date.today().isoformat(), "warnings": ["Slack collection failed: x"],
                                   "projects": []}), encoding="utf-8")
        self.write_stub("claude", f'python3 "{SCRIPTS}/write_day.py" day --json "{day}" >/dev/null\n'
                                  f'cat "{FIXTURES}/claude-result.json"\n')
        proc = self.run_sh()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        record = self.last_run()
        self.assertEqual((record["result"], record["reason"]), ("succeeded", "Completed with warnings"))

    def test_skill_path_with_spaces_is_refused_for_claude(self):
        copy = self.tmp / "my skill"
        shutil.copytree(SKILL_ROOT / "scripts", copy / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
        self.write_settings(self.tmp / "vault", "claude")
        self.write_stub("claude", "exit 0\n")
        proc = subprocess.run(["zsh", str(copy / "scripts" / "run.sh")], env=self.env, capture_output=True,
                              text=True, timeout=60)
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertEqual(self.last_run()["reason"], "Skill path must not contain spaces")

    def test_run_sh_missing_provider_records_failure(self):
        self.write_settings(self.tmp / "vault", "codex")
        proc = self.run_sh()
        self.assertEqual(proc.returncode, 1, proc.stderr)
        record = self.last_run()
        self.assertEqual((record["result"], record["provider"], record["reason"]), ("failed", "codex", "Provider not found"))


class EnvShTest(unittest.TestCase):
    def path_from(self, **env) -> list[str]:
        base = {k: v for k, v in os.environ.items() if k not in ("WORKLOG_PATH", "WORKLOG_EXTRA_PATH")}
        proc = subprocess.run(["zsh", "-fc", 'source "$1"; print -r -- "$PATH"', "_", str(SCRIPTS / "env.sh")],
                              env={**base, **env}, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout.strip().split(":")

    def test_extra_path_goes_first_and_defaults_follow(self):
        path = self.path_from(WORKLOG_EXTRA_PATH="/opt/tools/bin:/opt/other/bin")
        self.assertEqual(path[:2], ["/opt/tools/bin", "/opt/other/bin"])
        self.assertIn("/usr/local/bin", path)
        self.assertIn("/opt/homebrew/bin", path)

    def test_worklog_path_replaces_everything(self):
        self.assertEqual(self.path_from(WORKLOG_PATH="/only/here", WORKLOG_EXTRA_PATH="/ignored"), ["/only/here"])


if __name__ == "__main__":
    unittest.main()
