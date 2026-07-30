#!/usr/bin/env python3
"""project_brief (온보딩 ②) hermetic 테스트 — 포인터 전용 계약 검증."""
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("recent-context.py")
SPEC = importlib.util.spec_from_file_location("recent_context", SCRIPT)
assert SPEC and SPEC.loader
RC = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RC)


class ProjectBriefTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.ghq = base / "ghq"
        self.main = base / "main"
        (self.main / "projects").mkdir(parents=True)
        self.repo = self.ghq / "github.com" / "me" / "demoproj"
        (self.repo / ".git").mkdir(parents=True)
        self.addCleanup(self._tmp.cleanup)

    def _brief(self, cwd=None):
        return RC.project_brief(
            str(cwd or self.repo), ghq_root=self.ghq, main_root=self.main
        )

    def test_non_ghq_cwd_returns_nothing(self):
        self.assertEqual(
            RC.project_brief(str(self.main), ghq_root=self.ghq, main_root=self.main),
            [],
        )

    def test_missing_claude_md_recommends_newproject(self):
        out = "\n".join(self._brief())
        self.assertIn("demoproj", out)
        self.assertIn("/newproject", out)
        self.assertIn("project-status.sh", out)

    def test_devlog_headers_are_capped_and_normalized(self):
        (self.repo / "CLAUDE.md").write_text("x", encoding="utf-8")
        entries = "\n".join(
            f"## 2026-07-{10+i} 항목{i}\n본문 자유텍스트 {i}\n" for i in range(5)
        )
        (self.repo / "DEVLOG.md").write_text(entries, encoding="utf-8")
        out = "\n".join(self._brief())
        self.assertIn("항목0", out)
        self.assertIn("항목2", out)
        self.assertNotIn("항목3", out, "헤더는 3개 캡")
        self.assertNotIn("본문 자유텍스트", out, "본문(자유텍스트) 미주입 계약")

    def test_registered_project_frontmatter_and_deadline_warning(self):
        from datetime import datetime, timedelta

        soon = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")
        (self.main / "projects" / "demoproj-plan.md").write_text(
            f"---\ndecide_by: {soon}\nstatus: pending\n---\n비밀 본문은 실리면 안 됨\n",
            encoding="utf-8",
        )
        out = "\n".join(self._brief())
        self.assertIn("demoproj-plan.md", out)
        self.assertIn("pending", out)
        self.assertIn("⚠️ D-", out, "7일 내 pending decide_by는 경고")
        self.assertNotIn("비밀 본문", out, "frontmatter 키 2개 외 미주입")

    def test_subdirectory_resolves_to_repo_root(self):
        sub = self.repo / "src" / "deep"
        sub.mkdir(parents=True)
        out = "\n".join(self._brief(cwd=sub))
        self.assertIn("demoproj", out)


if __name__ == "__main__":
    unittest.main()
