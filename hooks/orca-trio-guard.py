#!/usr/bin/env python3
"""orca-trio-guard — "orca trio" 문맥에서 Agent 서브에이전트를 결정론 차단.

🤖 왜 (2026-07-25 maintainer 지시): "orca trio"라고 해도 모델이 Orca 분할창 대신 자기 세션
   서브에이전트를 여는 오발동이 실측됨. 스킬 지시문(soft)만으론 샐 수 있어 훅으로 집행:
   - 서브에이전트 = 결과만 반환하고 사라지는 헬퍼. 사용자가 원한 건 눈에 보이는 Orca 창 크루.
   - 차단은 지시가 아니라 하니스 레벨 deny — 모델이 우회 불가.

두 이벤트를 한 스크립트로 (skill-nudge.py와 같은 패턴):
- **UserPromptSubmit**: 발화에서 orca trio/듀오/크루 키워드 감지 → 세션 플래그 arm +
  "/orca-trio 스킬로 처리하라, 이 세션 서브에이전트는 차단됨" 컨텍스트 주입.
  "서브에이전트 허용/풀어/unblock subagents" 감지 → 플래그 해제(escape hatch).
  ⚠️ "/orca-trio onboard ..."(코디네이터 온보딩 주입)도 arm 대상 — 슬래시 프롬프트를 스킵하지 않는다.
- **PreToolUse** (matcher: Agent|Task|Workflow): 플래그 armed면 permissionDecision=deny —
  대안(orca-ide 위임 / '서브에이전트 허용' 요청)을 reason으로 안내.

차단 범위 (2026-07-25 재조정 — 라이브 지휘가 창 워커+보조 서브에이전트를 병행하는 실측과
충돌해서, "영구 차단"에서 "세팅 구간 방어"로): 아래 조건이면 훅이 자동 해제한다.
  ① 크루 실존 — cwd가 속한 레포 계열의 Orca 터미널이 3개 이상 떠 있음 (대체 오발동은
     크루가 없을 때의 실패 모드; 크루가 떴으면 목적 달성이라 보조 사용은 허용).
  ② TTL — arm 후 30분 경과 (오발동은 arm 직후에 일어난다).
  ③ 사용자 "서브에이전트 허용" (즉시).
해제 조건이 전부 Claude 판단 밖(실존 상태·시간·사용자 발화)이라 모델이 논리로 우회 못 함.

플래그: $TMPDIR/orca-trio-armed-<sid8> — 세션 격리라 워커 창(별도 세션)은 영향 없음.
실패는 조용히 exit 0(작업 흐름 절대 안 막음). 단 크루 확인 실패(Orca 미실행 등)는
보수적으로 차단 유지(TTL이 안전판).
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time

TTL_SEC = 30 * 60

ARM_RE = re.compile(
    r"(orca[-\s]?trio|오르카\s*트리오|트리오\s*(ㄱㄱ|세팅|띄워|가자)|orca\s*(duo|crew)|오르카\s*듀오|크루\s*띄워)",
    re.I,
)
DISARM_RE = re.compile(r"(서브\s*에이전트\s*(허용|풀어|해제)|unblock\s*subagents?|allow\s*subagents?)", re.I)


def flag_path(sid: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9-]", "", sid or "") or "nosid"  # 전체 SID (8자 절단 충돌 방지 — Codex 검수 #29)
    return os.path.join(tempfile.gettempdir(), f"orca-trio-armed-{safe}")


def on_prompt(e: dict) -> int:
    prompt = str(e.get("prompt") or "")
    if not prompt or prompt.lstrip().startswith("<"):  # 하니스 주입 리마인더만 제외 (슬래시는 arm 대상)
        return 0
    # arm/disarm은 짧은 명령형 발화만 — 붙여넣은 장문 문서 속 인용 키워드로
    # arm/해제가 오발동하는 것 방지 (Codex 검수 #1 — skill-nudge에서 같은 유형 오탐 실측)
    # 200자 초과는 "붙여넣은 장문 속 인용"으로 보고 스킵했는데, 정작 가장 중요한
    # "orca trio + 상세 brief" 요청이 통째로 우회됐다 (2026-07-29 2백본 감사 MAJOR).
    # 명시적 슬래시 호출·문두 명령은 길이와 무관하게 arm한다.
    _head = prompt.strip()[:120]
    _explicit = _head.startswith("/orca-trio") or bool(ARM_RE.search(_head))
    if len(prompt.strip()) > 200 and not _explicit:
        return 0
    fp = flag_path(e.get("session_id") or "")
    if DISARM_RE.search(prompt):
        try:
            os.remove(fp)
            print("[orca-trio-guard] 서브에이전트 차단 해제됨 (사용자 허용).")
        except OSError:
            pass
        return 0
    if ARM_RE.search(prompt):
        try:
            open(fp, "w").close()
        except OSError:
            return 0
        print(
            "[orca-trio-guard] orca trio 문맥 감지 — 이 요청은 /orca-trio 스킬(실제 Orca 분할창 크루)로 "
            "처리하라. 이 세션의 Agent 툴 서브에이전트는 훅이 차단한다(대체 금지의 결정론 집행). "
            "장수 위임은 반드시 orchestration(task-create → dispatch --inject → check --wait)으로 — "
            "terminal send는 온보딩·단발 메시지 전용이다(ID·deps·worker_done이 안 남는다). "
            "정말 서브에이전트가 필요하면 사용자에게 '서브에이전트 허용'을 요청."
        )
    return 0


def crew_up(cwd: str) -> bool:
    """cwd가 속한 레포 경로 계열의 Orca 터미널이 3개 이상이면 크루 실존으로 판정."""
    try:
        top = subprocess.run(
            ["git", "-C", cwd or ".", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        if not top:
            return False
        repo_root = top.split("/.orca/worktrees/")[0]  # 워크트리 안이면 본 레포 루트로
        unc_root = "\\\\wsl.localhost\\" + os.environ.get("WSL_DISTRO_NAME", "Ubuntu") \
            + repo_root.replace("/", "\\")
        out = subprocess.run(
            [os.environ.get("ORCA_CLI_COMMAND", "orca-ide"), "terminal", "list"],
            capture_output=True, text=True, timeout=8,
        ).stdout
        # 크루 = "같은 워크트리 한 곳"에 터미널 3개+ (레포 전역 합산이면 흩어진 무관
        # 터미널 3개도 크루로 오인 — Codex 검수 #4)
        counts: dict = {}
        for line in out.splitlines():
            parts = line.split()
            if parts and parts[0].startswith("term_") and parts[-1].startswith(unc_root):
                counts[parts[-1]] = counts.get(parts[-1], 0) + 1
        return max(counts.values(), default=0) >= 3
    except Exception:
        return False  # 확인 불가 → 보수적으로 차단 유지 (TTL이 안전판)


def on_pretooluse(e: dict) -> int:
    if e.get("tool_name") not in ("Agent", "Task", "Workflow"):  # Workflow도 서브에이전트 실행 경로 (Codex 검수 #27)
        return 0
    fp = flag_path(e.get("session_id") or "")
    if not os.path.exists(fp):
        return 0
    # 자동 해제: ② TTL 만료 → ① 크루 실존 (순서 = 싼 검사 먼저)
    try:
        expired = (time.time() - os.path.getmtime(fp)) > TTL_SEC
    except OSError:
        return 0
    if expired or crew_up(e.get("cwd") or os.getcwd()):
        try:
            os.remove(fp)
        except OSError:
            pass
        return 0
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                "이 세션은 orca-trio 세팅 문맥 — Agent 서브에이전트로 크루를 대체하지 마라(훅 집행). "
                "/orca-trio 스킬로 실제 Orca 크루를 세팅하라. 크루가 뜨면(같은 레포 터미널 3개+) "
                "이 차단은 자동 해제된다. 위임은 orca orchestration dispatch / terminal send로 "
                "워커 창(Opus·Codex)에게. 그래도 서브에이전트가 필요하면 사용자에게 "
                "'서브에이전트 허용'을 요청하라."
            ),
        }
    }, ensure_ascii=False))
    return 0


def main() -> int:
    try:
        e = json.load(sys.stdin)
    except Exception:
        return 0
    ev = e.get("hook_event_name") or ""
    try:
        if ev == "UserPromptSubmit":
            return on_prompt(e)
        if ev == "PreToolUse":
            return on_pretooluse(e)
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
