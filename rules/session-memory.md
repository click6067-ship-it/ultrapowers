# 🧠 세션 간 기억 (cross-folder, 시점 기반 — 자동)

- **세션 시작 시** `SessionStart` 훅(`~/main/system/recent-context.py`)이 전 폴더 세션을 *시점순*으로 훑어 최근 작업 맥락을 자동 주입한다. → 어느 폴더에서 열든, vscode를 껐다 켜든, 직전 작업을 자동 인지. 폴더가 바뀌어 "끊긴 것처럼" 보여도 데이터는 안전.
- **세션 종료 시** `Stop` 훅이 `export-sessions.py`로 전체 대화를 `~/main/logs/<키>__<날짜>__<sid>.md` 에 갱신. 상세 맥락이 필요하면 그 파일을 Read.
- **원본**은 항상 `~/.claude/projects/*/*.jsonl`(하니스 자동). **큐레이션 메모리**는 키별 `memory/` + git 미러 `~/main/system/memory-snapshot/<키>/`(SessionEnd sync가 scoped 자동 커밋).
- **메모리에 크리덴셜(암호·토큰·키) 절대 저장 금지** — 미러를 타고 원격 git에 실린다. 포인터("X는 .env 참조")만.
