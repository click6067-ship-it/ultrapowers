#!/usr/bin/env python3
"""SessionEnd hook — techreport 자동 GitHub push.

🤖/👤 무엇: techreport 스킬이 `$COMMAND_CENTER/reports/`에 보고서를 두고 `.push-pending` 마커를 남기면,
세션 종료 시 이 훅이 `$COMMAND_CENTER`을 자동 commit+push → 보고서가 GitHub(private command-center)에 올라감.
의도: "프로젝트 끝나면 자동으로 보고서가 GitHub에" — skill(LLM 보고서 작성) + hook(셸 push) 분담.
언제: SessionEnd 훅 자동. 마커 없으면 즉시 종료(노이즈 0).

설계:
- 마커 게이트: `.push-pending` 있을 때만 동작 → 매 세션 노이즈 방지(worklog 교훈).
- reports/ 만 add → 다른 미커밋 변경 안 건드림(안전).
- 커밋 이메일 트랩 회피: 정상 배포 이메일 고정.
- 실패 시 마커 보존 + hooks.log 기록 → 다음 SessionEnd가 자동 재시도(push는 마커 존재 시 무조건 시도 —
  "커밋됐지만 미푸시" 상태도 커버). 성공했을 때만 마커 삭제. 훅은 세션 종료를 막지 않음.
"""
import datetime, sys, subprocess, pathlib, os

HOME = pathlib.Path.home()
MAIN = pathlib.Path(os.environ.get("COMMAND_CENTER") or (HOME / "main"))
MARKER = MAIN / "reports" / ".push-pending"
LOG = MAIN / "logs" / "hooks.log"
# 커밋 이메일 트랩(Vercel 차단 이력) 회피 — main repo 정상 배포 이메일 고정.
EMAIL = "YOUR_GH_ID@users.noreply.github.com"


def hlog(msg):
    """훅 공통 관측 로그 — 조용한 실패 금지(2026-07-03 감사). 로그 실패 자체는 세션 종료를 막지 않음."""
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        if LOG.exists() and LOG.stat().st_size > 512_000:  # 로테이션: 캡 초과 시 최근 2000줄만 보존
            LOG.write_text("\n".join(LOG.read_text().splitlines()[-2000:]) + "\n")
        with LOG.open("a") as f:
            f.write(f"{datetime.datetime.now().isoformat(timespec='seconds')} [techreport-autopush] {msg}\n")
    except Exception:
        pass


def git(*args):
    return subprocess.run(["git", *args], cwd=str(MAIN), capture_output=True, text=True)


def main():
    if not MARKER.exists():
        return 0  # 보고서 push 대기 없음 → 조용히 종료(노이즈 0)
    try:
        name = (git("log", "-1", "--format=%an").stdout.strip() or "click6067-ship-it")
        git("add", "reports")
        git("reset", "-q", "--", "reports/.push-pending")  # 마커는 커밋 제외(커밋·삭제 시 repo dirty 방지)
        # reports/에 실제 staged 변경이 있을 때만 커밋(빈 커밋 방지).
        if git("diff", "--cached", "--quiet", "--", "reports").returncode != 0:
            # pathspec 한정 커밋 — 훅 실행 전 이미 staged된 무관 파일을 휩쓸지 않음(2026-07-03 Codex 리뷰 A1).
            c = git("-c", f"user.email={EMAIL}", "-c", f"user.name={name}",
                    "commit", "-m", "docs(report): auto techreport push (SessionEnd)", "--", "reports")
            if c.returncode != 0:
                hlog(f"ERROR commit 실패 — 마커 보존, 다음 세션 재시도: {' '.join(c.stderr.split())[:200]}")
                return 0
        # push는 마커 존재 시 무조건 시도 — 이전 세션에 커밋만 되고 push 실패한 경우 회수.
        p = git("push")
        if p.returncode != 0:
            hlog(f"ERROR push 실패 — 마커 보존, 다음 세션 재시도: {' '.join(p.stderr.split())[:200]}")
            return 0
        MARKER.unlink(missing_ok=True)
        hlog("OK 보고서 push 완료 — 마커 삭제")
    except Exception as e:
        hlog(f"ERROR 예외 — 마커 보존: {e}")
        sys.stderr.write(f"[techreport-autopush] {e}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
