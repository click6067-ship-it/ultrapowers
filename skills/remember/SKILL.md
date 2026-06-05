---
name: remember
description: Save one durable fact to cross-session curated memory. Use when asked to "remember X", "기억해", "이거 기억해둬", "save this to memory", "메모리에 저장", or when a non-obvious fact worth keeping surfaces (user preference, project constraint, working-style feedback, external reference). Writes a memory file (one file = one fact) + updates the MEMORY.md index + mirrors to the git snapshot. Automatic conversation logging is separate (Stop hook) — this is for curated facts you want recalled later.
---

# /remember — 사실 하나를 메모리에 저장

세션을 넘어 남길 **사실 하나**를 큐레이션 메모리에 저장한다(파일 1개 = 사실 1개).
자동 대화 로그(Stop 훅)와 별개 — 이건 *나중에 recall될 큐레이션된 사실*.

## 입력
저장할 내용 = 사용자가 `/remember` 뒤에 적은 것(또는 직전 대화에서 명확한 사실). 비었으면 무엇을 기억할지 한 번 묻는다.

## 절차
1. **타입 판정** (`metadata.type`): `user`(사용자 정체성·선호) / `feedback`(작업 방식 지침 — 교정·확인된 접근) / `project`(진행 작업·목표·제약) / `reference`(외부 리소스 포인터). 애매하면 묻는다.
2. **대상 키 결정** (경로 키잉: 작업경로의 `/`·`.`를 `-`로):
   - 현재 작업 폴더에 한정된 사실 → 현재 cwd 키 `~/.claude/projects/<키>/memory/`
   - 전역·메타·사용자·작업방식 사실 → **두뇌 키**(= `$COMMAND_CENTER`을 경로 키잉한 값: `/`·`.`→`-`). 이 머신=`-home-USER-main` → `~/.claude/projects/-home-USER-main/memory/`. (다른 머신은 `$HOME` 따라 달라짐 — 확인: `ls ~/.claude/projects/ | grep -- -main`.)
   - 확신 없으면 둘 중 어디인지 사용자에 확인.
3. **중복 확인 먼저**: 같은 사실의 기존 파일이 있으면 새로 만들지 말고 **그 파일을 갱신**(`grep -ril <키워드> <memory dir>`).
4. **파일 작성** (kebab-case 슬러그):
   ```markdown
   ---
   name: <slug>
   description: <한 줄 요약 — recall/SessionStart이 이걸로 관련성 판단. 정확히.>
   metadata:
     type: user | feedback | project | reference
   ---

   <사실. feedback/project면 **Why:** 와 **How to apply:** 줄 추가. 관련 메모리는 [[slug]]로 링크.>
   ```
5. **인덱스 갱신**: 같은 memory 디렉토리의 `MEMORY.md`에 한 줄 추가(`- [제목](파일.md) — 후크`). 없으면 생성.
6. **git 미러 + 커밋**:
   ```bash
   bash $COMMAND_CENTER/system/dotclaude/sync.sh >/dev/null
   git -C $COMMAND_CENTER log -3 --format=%ae        # ← author 이메일 확인(반복 함정)
   git -C $COMMAND_CENTER add -A && git -C $COMMAND_CENTER -c user.email="<확인된 이메일>" commit -m "mem: <요약>"
   ```

## 규칙 (FitLLM 정확도·메모리 규율)
- **코드·구조·git이 이미 기록하는 건 저장 안 함** — 비자명한 것만. 시킨 게 그런 거면 "무엇이 비자명했는지"를 물어 그걸 저장.
- **출처 없는 하드웨어/성능 숫자 저장 금지** (프로젝트 정확도 규율 — 출처 URL 동반).
- 틀린 것으로 판명된 메모리는 갱신하지 말고 **삭제**.
- "결정·규칙"이 매 세션 지켜져야 하면 메모리(recall 기반)보다 **CLAUDE.md(항상 로드)** 가 맞다 — 그 경우 사용자에 제안.
