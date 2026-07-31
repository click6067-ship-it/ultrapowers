# ⚠️ 반복 함정 — 시그니처와 포인터만

상세 사고 기록은 상시에 싣지 않는다. **증상 시그니처가 맞을 때만** 연결된 runbook을 읽는다. (과거 서사 이력 = `~/main/system/runbooks/rules-history-2026-07-31.md`)

- **공유 계정·클라우드:** 정본 = 헌법 🚫 절. 설정·사고 경계·기존 웹 산출물 삭제 = `~/main/system/runbooks/pitfalls-reference-2026-07-26.md`.
- **파괴·권한:** danger 설정은 이 머신의 의도적 예외지 안전 경계가 아니다. 파괴·외부발행·credential·deploy는 사용자 gate + 실제 target 확인이 먼저 (최악 계열은 guardrail이 기계 차단).
- **Git:** author는 `click6067-ship-it <you@example.com>`. 의도한 경로만 stage (`git add -A`는 guardrail이 차단). `git diff --shortstat`가 대량 삭제만 보이거나 `bad object HEAD`면 즉시 중단하고 runbook의 Git 복구 절차를 읽는다.
- **샌드박스 마스크:** 만든 적 없는 `.bashrc`·`.gitconfig`·`.claude/`·`.mcp.json`은 마운트 스켈레톤일 수 있다. `ls -la`로 유형 확인, 삭제·stage 금지.
- **Codex CLI:** `codex exec`는 **stdin을 닫아서 호출한다 — `< /dev/null` 필수**(안 닫으면 무한 대기).
- **WSL·dev server:** 현재 네트워크 모드를 먼저 실측한다 — 과거 원인을 자동 적maintainer지 않는다. 서버는 `127.0.0.1` 실브라우저 검증, 네트워크 변경 후 `system/netcheck.sh`. WSL 프리즈는 재시작 전 RAM/swap·kernel log부터.
- **Orca — 짜기 전에 공식 문서부터:** `~/main/system/orca-docs.sh guide orca-cli`(+`orchestration`), 정확한 플래그는 `orca-docs.sh cmd "..."`. 가이드는 CLI 번들이라 **md로 복사 금지**(낡은 문서는 없는 것보다 나쁘다). 실행파일 `ORCA_CLI_COMMAND` → 없으면 `orca-ide`. **워크트리는 사용자 요청·실제 체크아웃 충돌 시만.** 완료 감지 = orchestration `task-create`→`dispatch --inject`→`check --wait`, 준비 = `terminal wait --for tui-idle` (마커 폴링 재발명 금지). 조건부 함정(distro·UNC·CODEX_HOME·vsock 등) = `/orca-trio` runbook.
- **문서·도구 특수형:** HWP/HWPX는 `system/doc2txt.sh` · ffmpeg는 `~/.claude/tools/headless` 번들 · 빌트인 슬래시/플러그인 설치는 사용자가 직접 입력.
