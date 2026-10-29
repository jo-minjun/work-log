import unittest
from datetime import date

from helpers import SCRIPTS  # noqa: F401  (puts scripts/ on sys.path)

from logformat import FORMATS

D = date(2026, 10, 29)


class LogFormatTest(unittest.TestCase):
    def test_en_strings(self):
        fmt = FORMATS["en"]
        self.assertEqual(fmt.month_file_name(D), "2026-10 Work Log.md")
        self.assertEqual(fmt.month_title(D), "2026-10 Work Log")
        self.assertEqual(fmt.day_heading(D), "## 2026-10-29 (Thu)")
        self.assertEqual(fmt.other_project, "Other")
        self.assertEqual(fmt.project_list_name, "Active Projects.md")
        self.assertEqual(fmt.tags, ("work-log", "career"))
        self.assertEqual(list(fmt.source_headings.values()),
                         ["Claude Sessions", "Slack", "Decisions", "Needs Confirmation"])

    def test_ko_strings(self):
        fmt = FORMATS["ko"]
        self.assertEqual(fmt.month_file_name(D), "2026년 10월 업무 로그.md")
        self.assertEqual(fmt.day_heading(D), "## 2026-10-29 (목)")
        self.assertEqual(fmt.other_project, "기타")
        self.assertEqual(fmt.project_list_name, "진행 중인 프로젝트.md")
        self.assertEqual(list(fmt.source_headings), ["claude_session", "slack", "decision", "needs_confirmation"])
        self.assertEqual(fmt.source_headings["needs_confirmation"], "확인 필요")

    def test_descriptions_are_single_line(self):
        for fmt in FORMATS.values():
            self.assertNotIn("\n", fmt.description(D))


if __name__ == "__main__":
    unittest.main()
