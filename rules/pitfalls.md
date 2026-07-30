# ⚠️ 반복 함정 — 상시 경고만

상세 사고 기록은 매 세션에 싣지 않는다. 아래 **증상 시그니처가 맞을 때만** 연결된 runbook을 읽는다.

- **공유 계정·클라우드 노출:** 일반 모델 추론은 허용하지만 비밀 원문을 모델 컨텍스트에 넣지 않는다. Ultraplan·ultrareview·Remote Control/원격 에이전트·Artifact 발행·세션 URL 트레일러는 금지한다. “업로드 0”이라 과장하지 말고, 정확히는 **일반 추론 외 웹 게시·원격 실행·계정 공유형 지속 저장 금지**다. 설정·사고 경계·기존 웹 산출물 삭제는 `~/main/system/runbooks/pitfalls-reference-2026-07-26.md`를 본다.
- **파괴·권한:** `danger-full-access + approval=never`는 이 머신의 의도적 예외일 뿐 안전 경계가 아니다. 파괴·외부발행·credential·deploy는 사용자 gate와 실제 target 확인이 먼저다.
- **Git:** author는 `click6067-ship-it <click6067@gmail.com>`. `git add -A` 금지, 의도한 경로만 stage. `git diff --shortstat`가 대량 삭제만 보이거나 `bad object HEAD`면 즉시 중단하고 상세 기록의 Git 복구 절차를 읽는다.
- **샌드박스 마스크:** 만든 적 없는 `.bashrc`·`.gitconfig`·`.claude/`·`.mcp.json`은 마운트 스켈레톤일 수 있다. `ls -la`로 유형을 확인하고 삭제·stage하지 않는다.
- **Codex CLI:** `codex exec`는 **stdin을 닫아서 호출한다 — `< /dev/null` 필수**(안 닫으면 무한 대기). 업그레이드 뒤 plugin thread만 400이면 장수 broker/app-server의 구 바이너리를 의심한다.
- **WSL·dev server:** 현재 네트워크 모드를 먼저 실측한다. localhost 문제에 과거 mirrored/netns 원인을 자동 적용하지 않는다. 서버는 `127.0.0.1`로 실제 브라우저에서 검증하고, 네트워크 변경 후 `system/netcheck.sh`를 실행한다. WSL 프리즈는 재시작 전 RAM/swap·kernel log부터 본다.
- **Orca — 짜기 전에 공식 문서부터:** `~/main/system/orca-docs.sh guide orca-cli`(+`orchestration`), 정확한 플래그는 `orca-docs.sh cmd "worktree create"`. 가이드는 CLI에 번들돼 버전이 항상 맞으니 **md로 복사하지 말 것**(낡은 문서는 없는 것보다 나쁘다). 실행파일은 `ORCA_CLI_COMMAND` → 없으면 `orca-ide`(리눅스 bare `orca`는 GNOME 스크린리더). **워크트리는 사용자가 요청했거나 실제 체크아웃 충돌이 있을 때만** 만든다 — 병렬·독립·편의는 격리 사유가 아니며 fresh worker = 새 에이전트 터미널이지 새 워크트리가 아니다. 완료 감지는 마커 폴링이 아니라 orchestration `task-create`→`dispatch --inject`→`check --wait`, 준비 확인은 `terminal wait --for tui-idle`. *(2026-07-29: 이 줄에 이미 "orchestration이 정본"이라 적혀 있었는데 안 읽고 마커·nonce·폴링 감독을 재발명했다. 규칙을 읽는 것과 실행법을 아는 것은 다르다 → 그래서 도구 경로를 앞에 뒀다.)* WSL distro·UNC·worktree full ID·`CODEX_HOME` 복사본·vsock·등호형 flag 함정은 `/orca-trio`의 조건부 runbook에서 확인한다.
- **문서·도구 특수형:** HWP/HWPX는 `system/doc2txt.sh`; ffmpeg는 `~/.claude/tools/headless/node_modules/ffmpeg-static`; 빌트인 slash/plugin 설치는 사용자가 직접 입력한다.
