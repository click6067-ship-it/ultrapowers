#!/usr/bin/env python3
"""skill-nudge — 상황→스킬 선제 제안의 결정론 훅화 (rules/routing.md 결정표의 집행 레이어).

🤖 왜 (2026-07-17 용하 지시): 규칙 기반 선제 제안은 모델이 놓칠 수 있다 → 훅으로 승격.
   단 **완전 자동 아님** — 훅은 "제안하라"는 지시만 주입하고, 실행 여부는 사용자가 1번 답해 결정.
   같은 세션에서 같은 제안은 1회만(마커 dedupe — 강매 금지).

두 이벤트를 한 스크립트로:
- **UserPromptSubmit**: 사용자 발화 키워드 감지(ship/serve/specpack/kickoff/recall) →
  stdout(컨텍스트 주입)으로 "해당 스킬을 1줄 제안하라, 자동 실행 금지" 지시. exit 0.
- **Stop**: transcript 꼬리에서 "에러 신호 ≥3회 + 마지막 응답에 해결 선언" = 트러블슈팅 종결 →
  exit 2(stderr)로 "종료 전 /techreport 1줄 제안" 강제. 세션당 1회, stop_hook_active면 무발동(루프 방지).

성능: Stop은 transcript 마지막 ~200KB만 읽음. 실패는 조용히 exit 0(작업 흐름 절대 안 막음).
"""
import json
import os
import re
import sys
import tempfile

# ── 발화 키워드 → 제안할 스킬 (tight하게 — 오탐이 잔소리를 만든다) ──
PROMPT_RULES = [
    ("ship", r"(배포\s*해|배포까지|배포하고|푸시하고|푸시해|커밋하고|커밋해\s*줘?|마무리\s*하자|끝내\s*[자줘]|릴리즈|\bship\b)",
     "/ship (verify→커밋→푸시→배포→vcheck 표준 마무리 체인)"),
    ("serve", r"(서버\s*(좀\s*)?(띄|켜|실행|올려)|로컬\s*호스트|localhost|로컬로\s*(열|띄)|포트가?\s*안\s*열)",
     "/serve (샌드박스 밖 기동 + 127.0.0.1 검증 + localhost 4계열 진단)"),
    ("specpack", r"(\bPRD\b|\bERD\b|기획서\s*(써|작성)|스펙\s*(작성|정식화|문서화)|요구사항\s*정리)",
     "/specpack (경량 PRD·ERD·design·ADR 규격 문서팩)"),
    ("kickoff", r"(만들고\s*싶|새\s*프로젝트\s*시작|기획\s*회의|킥오프|\bkickoff\b)",
     "/kickoff (다중백본 Plan Council — blind 발산 → 봉인 → HARDEN, Phase 0)"),
    ("recall", r"(전에\s*(했|어떻게\s*했)|예전에\s*(했|어떻게)|이거\s*전에)",
     "/recall (전 폴더 과거 작업·해결 로그 검색)"),
]

# ── 트러블슈팅 종결 신호 (Stop) ──
_ERR_RE = re.compile(r"(Traceback|Error:|ERROR|FAILED|exit code [1-9]|Exception|에러|실패)", re.I)
_RESOLVED_RE = re.compile(r"(근본\s*원인|root\s*cause|해결(했|됐|되었)|고쳤|수정\s*(완료|됐)|복구(했|됐|되었)|정상화|fixed)", re.I)


def marker(sid: str, key: str):
    return os.path.join(tempfile.gettempdir(), f"skill-nudge-{sid[:8]}-{key}")


def on_prompt(e: dict) -> int:
    prompt = str(e.get("prompt") or "")
    if not prompt or prompt.lstrip().startswith(("<", "/")):  # 하니스 주입·슬래시 직접 호출은 제외
        return 0
    # orca trio 문맥은 orca-trio-guard.py가 전담 — 같은 발화에 kickoff 등 넛지가 겹치면
    # 지시가 비결정적으로 병합됨 (2026-07-26 Codex 검수 #28)
    if re.search(r"(orca[-\s]?(trio|duo|crew)|오르카\s*(트리오|듀오)|트리오\s*(ㄱㄱ|세팅|띄워)|크루\s*띄워)", prompt, re.I):
        return 0
    sid = e.get("session_id") or "nosid"
    for key, pat, desc in PROMPT_RULES:
        if re.search(pat, prompt):
            m = marker(sid, key)
            if os.path.exists(m):
                continue  # 이 세션에서 이미 제안됨 — 재제안 금지
            try:
                open(m, "w").close()
            except OSError:
                pass
            print(f"[skill-nudge] 사용자 발화에서 '{key}' 상황 감지 — {desc}. "
                  f"**사용자가 직접 명령한 것이면(‘배포해’·‘서버 띄워’ 같은 명령형) 되묻지 말고 바로 그 스킬을 쓴다** — "
                  f"스킬 자체의 trigger 계약이 그렇게 돼 있고, 재승인 질문은 실행만 멈춘다(2026-07-29 감사). "
                  f"암묵적 상황 감지일 뿐이면 **1줄로 제안**하고 사용자 선택을 따른다. "
                  f"이미 해당 스킬 흐름 중이거나 사용자가 명시적으로 그 스킬을 불렀다면 이 알림은 무시하라.")
            return 0  # 첫 매치 1건만 — 제안 폭탄 금지
    return 0


def last_assistant_text(entries) -> str:
    for o in reversed(entries):
        if o.get("type") == "assistant":
            c = o.get("message", {}).get("content")
            if isinstance(c, list):
                texts = [b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text"]
                if texts:
                    return texts[-1]
    return ""


def on_stop(e: dict) -> int:
    if e.get("stop_hook_active"):  # 다른 stop 훅이 이미 계속시킨 턴 — 루프 방지
        return 0
    sid = e.get("session_id") or "nosid"
    m = marker(sid, "techreport")
    if os.path.exists(m):
        return 0
    tp = e.get("transcript_path") or ""
    if not os.path.isfile(tp):
        return 0
    # 꼬리 ~200KB만
    size = os.path.getsize(tp)
    with open(tp, "rb") as f:
        if size > 200_000:
            f.seek(size - 200_000)
            f.readline()  # 잘린 첫 줄 버림
        raw = f.read().decode("utf-8", "replace")
    entries = []
    for ln in raw.splitlines():
        try:
            entries.append(json.loads(ln))
        except Exception:
            continue
    errs = len(_ERR_RE.findall(raw))
    final = last_assistant_text(entries)
    if errs >= 3 and final and _RESOLVED_RE.search(final):
        try:
            open(m, "w").close()  # exit 2 전에 마커 — 다음 Stop은 무조건 통과
        except OSError:
            pass
        sys.stderr.write(
            "[skill-nudge] 트러블슈팅 종결 신호 감지(에러 신호 반복 후 해결 선언). 종료하기 전에 사용자에게 "
            "\"이 트러블슈팅 /techreport로 기술보고서 남길까요?\" 를 **한 번만** 물어라. "
            "강요 금지 — 사용자가 답하면(또는 무시하면) 그대로 종료. 다른 작업 추가 금지.\n")
        return 2
    return 0


def main() -> int:
    try:
        e = json.load(sys.stdin)
    except Exception:
        return 0
    ev = e.get("hook_event_name") or ""
    if ev == "UserPromptSubmit":
        return on_prompt(e)
    if ev == "Stop":
        return on_stop(e)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
