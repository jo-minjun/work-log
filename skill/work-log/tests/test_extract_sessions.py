import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from helpers import make_settings

from extract_sessions import commit_message, extract

D28, D29 = date(2026, 10, 28), date(2026, 10, 29)


def ev(type_, ts, cwd, **extra):
    e = {"type": type_, "timestamp": ts, "cwd": cwd, "sessionId": "s", "isSidechain": False}
    e.update(extra)
    return e


def user(ts, cwd, content, **extra):
    return ev("user", ts, cwd, message={"role": "user", "content": content}, **extra)


def assistant(ts, cwd, content, **extra):
    return ev("assistant", ts, cwd, message={"role": "assistant", "content": content}, **extra)


def write_session(root: Path, dirname: str, session_id: str, events, extra_lines=()):
    d = root / dirname
    d.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(e, ensure_ascii=False) for e in events] + list(extra_lines)
    (d / f"{session_id}.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


class ExtractSessionsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.root = base / "projects"
        self.work = base / "Projects" / "work"
        self.cfg = make_settings(base, [self.work])

    def tearDown(self):
        self.tmp.cleanup()

    def cwd(self, rel):
        return str(self.work / rel)

    def sessions(self, d=D28):
        return extract(self.cfg, d, self.root)["sessions"]

    def test_splits_session_at_kst_midnight(self):
        write_session(self.root, "p", "sid-1", [
            user("2026-10-28T14:50:00.000Z", self.cwd("checkout"), "밤 작업"),
            user("2026-10-28T15:30:00.000Z", self.cwd("checkout"), "자정 넘김"),
        ])
        s28, s29 = self.sessions(D28)[0], self.sessions(D29)[0]
        self.assertEqual((s28["start"], s28["end"]), ("23:50", "23:50"))
        self.assertEqual((s29["start"], s29["end"]), ("00:30", "00:30"))
        self.assertEqual(s28["prompts"], ["밤 작업"])
        self.assertEqual(s29["prompts"], ["자정 넘김"])

    def test_excludes_outside_include_path_and_prefix_lookalike(self):
        base = Path(self.tmp.name)
        write_session(self.root, "a", "sid-a", [user("2026-10-28T01:00:00Z", str(base / "Projects/me/x"), "개인")])
        write_session(self.root, "b", "sid-b", [user("2026-10-28T01:00:00Z", str(base / "Projects/work-other/x"), "비슷한 경로")])
        self.assertEqual(self.sessions(), [])

    def test_excludes_other_day_events_only(self):
        write_session(self.root, "p", "sid-1", [user("2026-10-26T01:00:00Z", self.cwd("checkout"), "이틀 전")])
        self.assertEqual(self.sessions(), [])

    def test_repo_from_subdir_and_worktree(self):
        write_session(self.root, "p", "sid-1", [user("2026-10-28T01:00:00Z", self.cwd("checkout/apps"), "a")])
        write_session(self.root, "q", "sid-2", [user("2026-10-28T02:00:00Z", self.cwd("checkout/.claude/worktrees/checkout/main-3"), "b")])
        self.assertEqual([s["repo"] for s in self.sessions()], ["checkout", "checkout"])

    def test_excludes_sidechain_events(self):
        write_session(self.root, "p", "sid-1", [
            user("2026-10-28T01:00:00Z", self.cwd("checkout"), "서브에이전트", isSidechain=True),
        ])
        write_session(self.root, "q", "sid-2", [
            user("2026-10-28T01:00:00Z", self.cwd("checkout"), "본 세션"),
            user("2026-10-28T01:05:00Z", self.cwd("checkout"), "서브에이전트", isSidechain=True),
        ])
        sessions = self.sessions()
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["prompts"], ["본 세션"])

    def test_excludes_work_log_sessions(self):
        cases = [
            [user("2026-10-28T01:00:00Z", self.cwd("checkout"), "/work-log 2026-10-27")],
            [user("2026-10-28T01:00:00Z", self.cwd("checkout"),
                  "<command-message>work-log</command-message>\n<command-name>/work-log</command-name>")],
            [user("2026-10-28T01:00:00Z", self.cwd("checkout"), "업무 로그 정리해줘"),
             assistant("2026-10-28T01:00:05Z", self.cwd("checkout"),
                       [{"type": "tool_use", "id": "t1", "name": "Skill", "input": {"skill": "work-log"}}])],
        ]
        for i, events in enumerate(cases):
            write_session(self.root, f"p{i}", f"sid-{i}", events)
        self.assertEqual(self.sessions(), [])

    def test_excludes_codex_skill_invocation(self):
        write_session(self.root, "p", "sid-1", [user("2026-10-28T01:00:00Z", self.cwd("checkout"), "$work-log 2026-10-27")])
        write_session(self.root, "q", "sid-2", [user("2026-10-28T02:00:00Z", self.cwd("checkout"), "explain $work-log usage")])
        self.assertEqual([s["sessionId"] for s in self.sessions()], ["sid-2"])

    def test_keeps_session_whose_compact_summary_quotes_work_log_command(self):
        write_session(self.root, "p", "sid-1", [
            user("2026-10-28T01:00:00Z", self.cwd("checkout"),
                 "요약: 제외 규칙은 <command-name>/work-log</command-name> 포함 여부다", isCompactSummary=True),
            user("2026-10-28T01:01:00Z", self.cwd("checkout"), "다시 ㄱㄱ"),
        ])
        self.assertEqual(self.sessions()[0]["prompts"], ["다시 ㄱㄱ"])

    def test_collects_title_branches_prompts(self):
        long_prompt = "가" * 400
        events = [
            user("2026-10-28T01:00:00Z", self.cwd("checkout"), "첫 요청", gitBranch="main"),
            user("2026-10-28T01:01:00Z", self.cwd("checkout"), "메타", isMeta=True, gitBranch="feat/x"),
            user("2026-10-28T01:02:00Z", self.cwd("checkout"), "<system-reminder>x</system-reminder>", gitBranch="main"),
            user("2026-10-28T01:03:00Z", self.cwd("checkout"),
                 [{"type": "tool_result", "tool_use_id": "t9", "content": "결과"}]),
            user("2026-10-28T01:04:00Z", self.cwd("checkout"), [{"type": "text", "text": "리스트 텍스트"}]),
            user("2026-10-28T01:04:30Z", self.cwd("checkout"), '  <pasted_content id="x">붙여넣은 요청</pasted_content>'),
            user("2026-10-28T01:05:00Z", self.cwd("checkout"), long_prompt),
            {"type": "ai-title", "aiTitle": "옛 제목", "sessionId": "s"},
            {"type": "ai-title", "aiTitle": "새 제목", "sessionId": "s"},
        ]
        events += [user(f"2026-10-28T02:{i:02d}:00Z", self.cwd("checkout"), f"p{i}") for i in range(35)]
        write_session(self.root, "p", "sid-1", events)
        s = self.sessions()[0]
        self.assertEqual(s["sessionId"], "sid-1")
        self.assertEqual(s["title"], "새 제목")
        self.assertEqual(s["branches"], ["main", "feat/x"])
        self.assertEqual(s["prompts"][:3], ["첫 요청", "리스트 텍스트", '<pasted_content id="x">붙여넣은 요청</pasted_content>'])
        self.assertEqual(len(s["prompts"][3]), 300)
        self.assertEqual(len(s["prompts"]), 30)
        self.assertEqual(s["cwd"], self.cwd("checkout"))

    def test_commit_message_heredoc_and_m_flag(self):
        heredoc = "git commit -m \"$(cat <<'EOF'\nfeat: 환불 API\n\nbody\nEOF\n)\""
        self.assertEqual(commit_message(heredoc), "feat: 환불 API")
        self.assertEqual(commit_message("git commit -m 'fix: 버그'"), "fix: 버그")
        self.assertEqual(commit_message('git add . && git commit -m "chore: 정리"'), "chore: 정리")
        stdin_heredoc = "git add x && git commit -q -F - <<'EOF'\nfeat: 설정 추가\n\n- 상세\nEOF\ngit log -1"
        self.assertEqual(commit_message(stdin_heredoc), "feat: 설정 추가")
        self.assertIsNone(commit_message("git status"))

    def test_commit_message_ignores_heredoc_not_attached_to_commit(self):
        script_then_commit = "python3 - <<'EOF'\nimport glob,re\nEOF\ngit commit -m 'feat: B'"
        self.assertEqual(commit_message(script_then_commit), "feat: B")
        self.assertIsNone(commit_message("cat <<'EOF' > msg.txt\nhello\nEOF\ngit commit -F msg.txt"))

    def test_dedupes_repeated_commit_messages(self):
        bash = lambda i: {"type": "tool_use", "id": f"t{i}", "name": "Bash", "input": {"command": "git commit -m 'feat: A'"}}
        write_session(self.root, "p", "sid-1", [
            user("2026-10-28T01:00:00Z", self.cwd("checkout"), "커밋"),
            assistant("2026-10-28T01:01:00Z", self.cwd("checkout"), [bash(1), bash(2)]),
        ])
        self.assertEqual(self.sessions()[0]["commits"], [{"message": "feat: A"}])

    def test_all_sessions_mode_keeps_exclusions_and_names_repo_by_cwd(self):
        all_cfg = make_settings(Path(self.tmp.name), [])
        write_session(self.root, "p", "sid-1", [
            user("2026-10-28T01:00:00Z", "/tmp/a/repo-x", "일반 작업"),
        ])
        write_session(self.root, "q", "sid-2", [
            user("2026-10-28T01:00:00Z", "/tmp/a/repo-y", "/work-log 2026-10-27"),
        ])
        write_session(self.root, "r", "sid-3", [
            user("2026-10-28T01:00:00Z", "/tmp/a/repo-z", "branch name", entrypoint="sdk-cli"),
        ])
        found = extract(all_cfg, D28, self.root)["sessions"]
        self.assertEqual([(s["sessionId"], s["repo"]) for s in found], [("sid-1", "repo-x")])

    def test_excludes_programmatic_sdk_sessions(self):
        write_session(self.root, "p", "sid-1", [
            user("2026-10-28T01:00:00Z", self.cwd("checkout"), "Generate a short git branch name", entrypoint="sdk-cli"),
        ])
        write_session(self.root, "q", "sid-2", [
            user("2026-10-28T01:00:00Z", self.cwd("checkout"), "대화형 세션", entrypoint="cli"),
        ])
        self.assertEqual([s["sessionId"] for s in self.sessions()], ["sid-2"])

    def test_collects_commits_and_pr_url_from_gh_pr_create_result(self):
        url = "https://github.com/example/repo/pull/1240"
        write_session(self.root, "p", "sid-1", [
            user("2026-10-28T01:00:00Z", self.cwd("checkout"), "PR 올려줘"),
            assistant("2026-10-28T01:01:00Z", self.cwd("checkout"), [
                {"type": "tool_use", "id": "t0", "name": "Bash", "input": {"command": "git commit -m 'feat: A'"}},
                {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "gh pr create --title x"}},
                {"type": "tool_use", "id": "t2", "name": "Bash", "input": {"command": "gh pr view 999"}},
            ]),
            user("2026-10-28T01:02:00Z", self.cwd("checkout"), [
                {"type": "tool_result", "tool_use_id": "t1", "content": f"{url}\n"},
                {"type": "tool_result", "tool_use_id": "t2",
                 "content": [{"type": "text", "text": "https://github.com/example/repo/pull/999"}]},
            ]),
        ])
        s = self.sessions()[0]
        self.assertEqual(s["commits"], [{"message": "feat: A"}])
        self.assertEqual(s["prs"], [{"url": url}])

    def test_skips_broken_lines(self):
        write_session(self.root, "p", "sid-1",
                      [user("2026-10-28T01:00:00Z", self.cwd("checkout"), "정상")],
                      extra_lines=["{not json", '{"type": "user"'])
        result = extract(self.cfg, D28, self.root)
        self.assertEqual(result["skippedLines"], 2)
        self.assertEqual(result["sessions"][0]["prompts"], ["정상"])

    def test_fork_sessions_deduplicated_by_uuid(self):
        copied = [
            user("2026-10-28T01:00:00Z", self.cwd("checkout"), "원본 요청 1", uuid="u1"),
            user("2026-10-28T01:10:00Z", self.cwd("checkout"), "원본 요청 2", uuid="u2"),
        ]
        write_session(self.root, "p", "parent", copied)
        write_session(self.root, "q", "fork", copied + [
            user("2026-10-28T05:00:00Z", self.cwd("checkout"), "갈라진 뒤 요청", uuid="u3"),
        ])
        by_id = {s["sessionId"]: s for s in self.sessions()}
        self.assertEqual(by_id["parent"]["prompts"], ["원본 요청 1", "원본 요청 2"])
        self.assertEqual(by_id["fork"]["prompts"], ["갈라진 뒤 요청"])
        self.assertEqual(by_id["fork"]["start"], "14:00")

    def test_fork_without_new_events_is_dropped(self):
        copied = [user("2026-10-28T01:00:00Z", self.cwd("checkout"), "원본", uuid="u1")]
        write_session(self.root, "p", "parent", copied)
        write_session(self.root, "q", "fork", copied)
        self.assertEqual([s["sessionId"] for s in self.sessions()], ["parent"])

    def test_skips_invalid_timestamp(self):
        write_session(self.root, "p", "sid-1", [
            user("garbage", self.cwd("checkout"), "이상한 시각"),
            user("2026-10-28T01:00:00Z", self.cwd("checkout"), "정상"),
        ])
        result = extract(self.cfg, D28, self.root)
        self.assertEqual(result["skippedLines"], 1)
        self.assertEqual(result["sessions"][0]["prompts"], ["정상"])

    def test_excludes_compact_summary_and_interrupt_prompts(self):
        write_session(self.root, "p", "sid-1", [
            user("2026-10-28T01:00:00Z", self.cwd("checkout"), "This session is being continued...", isCompactSummary=True),
            user("2026-10-28T01:01:00Z", self.cwd("checkout"), "보이기만 함", isVisibleInTranscriptOnly=True),
            user("2026-10-28T01:02:00Z", self.cwd("checkout"), "[Request interrupted by user for tool use]"),
            user("2026-10-28T01:03:00Z", self.cwd("checkout"), "진짜 요청"),
        ])
        self.assertEqual(self.sessions()[0]["prompts"], ["진짜 요청"])

    def test_commit_message_with_dash_c_and_am(self):
        self.assertEqual(commit_message("git -C /repo commit -m 'feat: C'"), "feat: C")
        self.assertEqual(commit_message("git commit -am 'fix: D'"), "fix: D")

    def test_sessions_sorted_by_start(self):
        write_session(self.root, "p", "late", [user("2026-10-28T05:00:00Z", self.cwd("checkout"), "늦게")])
        write_session(self.root, "q", "early", [user("2026-10-28T01:00:00Z", self.cwd("checkout"), "일찍")])
        self.assertEqual([s["sessionId"] for s in self.sessions()], ["early", "late"])


if __name__ == "__main__":
    unittest.main()
