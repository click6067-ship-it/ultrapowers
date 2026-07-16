---
name: serve
description: Use when the user says 서버 띄워/로컬 실행/dev 서버 켜줘/로컬로 열어줘/localhost 안 열려/로컬호스트 또 안 열리네/포트 안 열림/serve, or a dev server must be started and reachable from the user's browser. Starts the dev server OUTSIDE the sandbox (netns trap), verifies reachability on 127.0.0.1, and on failure auto-runs the 4-family localhost diagnosis (sandbox netns · ::1 blackhole · portproxy shadowing · vmIdleTimeout) instead of guessing. Completion = user's browser confirms.
---

# serve — dev 서버 기동 + localhost 자동 진단

**목적.** "로컬호스트 또 안 열리네"를 끝낸다. 로그 실측 16세션에서 localhost 문제 반복 — 근본원인 4계열은 이미 규명돼 있다(`rules/pitfalls.md`, 2026-07-06/07 실증). 이 스킬은 그 지식을 **기동 시점에 자동 적용**한다.

## 절차

### 1. 기동 (함정 1 차단이 여기서 결정된다)
- **⚠️ 샌드박스 Bash로 서버를 띄우지 않는다** — 샌드박스는 호출마다 ephemeral netns라 브라우저·호스트·다음 Bash 어디서도 도달 불가("안에서 curl 200 = 떠 있다" 착각이 만성 원흉 1호). **반드시 `dangerouslyDisableSandbox: true` + `run_in_background: true`**로 기동하거나, 사용자에게 `! <명령>` 실행을 요청.
- 기동 전 포트 선점 확인: `ss -ltn | grep :<port>` + stale 데몬/락(Next 등) 정리.
- ready 감지는 로그 폴링(`until grep -q "Ready\|Local:" <log>; do sleep 0.5; done`) — 추측 금지.

### 2. 도달성 검증 (함정 2: ::1 블랙홀)
```bash
curl -sS -o /dev/null -w "%{http_code} %{time_total}s" http://127.0.0.1:<port>/
```
- **항상 `127.0.0.1`** — WSL mirrored 모드에서 `localhost`(::1)는 SYN 블랙홀(5초+ 행, RST 없음) 가능. 사용자에게 주는 URL도 `http://127.0.0.1:<port>` 형태로.

### 3. 실패 시 — 4계열 자동 진단 (추측으로 재시작 반복 금지)
순서대로 실행하고 결과를 함께 보고:
```bash
netsh.exe interface portproxy show all   # ① 포트 섀도잉 1순위 (NAT 잔재 규칙이 점유 — :3000 실증)
bash $COMMAND_CENTER/system/netcheck.sh           # ② 네트워크 회귀 매트릭스 (~3초, 실제 netns)
ss -ltn                                  # ③ 실제 바인딩 확인 (WSL쪽)
```
- ①에서 172.20.x 타깃 규칙 발견 = iphlpsvc 점유 → elevated `netsh interface portproxy delete`로 해결(사용자 안내).
- "어제 띄운 게 오늘 안 열림" = ④ vmIdleTimeout VM 회수 의심 — 서버 재기동이 정답(현재 3600000ms 완화 적용됨).
- **"전에 해결했던" 기억이 나면 `/recall localhost`** — 과거 해결 로그 자동 탐색.

### 4. 완료 기준
**사용자 브라우저에서 열리는 것**이 완료다(2026-07-03 교훈) — curl 200은 중간 증거일 뿐. URL을 주고 열리는지 확인 요청. 안 열리면 §3으로 돌아간다.

## 안 하는 것
- 샌드박스 안 기동 (증상 재생산의 근원).
- 진단 없이 "재시작 한 번 더" 반복.
- `localhost` 문자열 URL 안내 (127.0.0.1로).
