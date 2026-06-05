---
name: recall
description: Search past work across ALL folders/projects — the full conversation archive ($COMMAND_CENTER/logs) plus curated memory (every project key) — for a topic, person, file, decision, or "did we do this before". Use when asked to "recall X", "find past work on X", "what do I know about X", "이거 전에 했었나", "X 관련 뭐 했었지", "예전에 어떻게 풀었지". Complements the automatic SessionStart cross-folder context (recent-context.py) by letting you search on demand instead of only seeing the most recent sessions.
---

# /recall — 과거 작업 검색 (전 폴더·시점 무관)

토픽/사람/파일/결정을 **전체 대화 아카이브 + 큐레이션 메모리**에서 찾는다.
자동 SessionStart 주입이 "최근"을 보여준다면, 이건 "특정 주제"를 깊게 판다.

## 입력
검색어 = 사용자가 `/recall` 뒤에 적은 것(또는 직전 메시지에서 명확한 주제). 비었으면 무엇을 찾는지 한 번 묻는다.

## 절차
1. 두 소스를 동시에 검색(대소문자 무시·`-a`로 바이너리 회피). **한글과 영문 동의어 둘 다** 시도(예: 엔진·engine, 메모리·memory):
   ```bash
   Q='<검색어>'
   echo "== 큐레이션 메모리(사실) =="
   grep -rails -- "$Q" ~/.claude/projects/*/memory/ 2>/dev/null
   echo "== 대화 아카이브(세션, 최신순) =="
   grep -rails -- "$Q" $COMMAND_CENTER/logs/*.md 2>/dev/null | xargs -r ls -t 2>/dev/null
   ```
   (아카이브가 오래됐을 수 있으면 먼저 `python3 $COMMAND_CENTER/system/export-sessions.py >/dev/null` 한 번.)
2. 결과를 묶어 제시:
   - **메모리 사실** — 매칭된 memory 파일을 Read 해 관련 줄만 인용(출처 파일명 명시).
   - **세션** — 최신순으로 `logs/<파일>.md` 나열 + 각 세션 1줄 설명. 상위 1–2개는 매칭 부분을 Read로 확인해 요약.
3. 결과가 많으면(>10) 최신 위주로 좁히고 "더 볼까요?" 제안.
4. 못 찾으면 동의어/한영을 바꿔 재시도. 그래도 없으면 솔직히 없다고 말한다(지어내지 않는다).

## 규칙
- **읽기 전용.** 아무것도 수정하지 않는다.
- 아카이브/메모리에 실제로 있는 것만 인용. 출처(파일명) 명시. 추측 금지.
- 관련 기억 저장이 필요해 보이면 [[remember]] 스킬을 제안.
