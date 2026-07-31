# 🧠 세션 간 기억 (전 폴더 · 자동) — 계층 정본

| 겹 | 위치 | 성격 | 훅 |
|---|---|---|---|
| 원시 | `~/.claude/projects/*/*.jsonl` | 하니스 전체 기록 | 자동 |
| 아카이브 | `~/main/logs/<키>__<날짜>__<sid>.md` | 전체 대화 md (gitignore) | Stop `export-sessions.py` |
| 요약 | `~/main/worklog/` | 세션당 1개 (gitignore) | SessionEnd |
| 주입 | 세션 시작 시 | 최근 세션 **메타 포인터만** | SessionStart `recent-context.py` |
| devlog | 각 `~/ghq` repo의 `DEVLOG.md` | LLM 정제 프로젝트 일지 | SessionEnd (`DEVLOG_DISABLE=1`로 끔) |

- 주입은 파일명·시각·크기뿐, 본문 미주입(인젝션·누수 차단) — "직전 작업 자동 인지"가 아니라 **어디를 읽으면 되는지의 자동 인지**다. 내용은 로그 Read 또는 `/recall`. 폴더가 바뀌어 끊긴 듯 보여도 데이터는 안전.
- devlog 항목 마커(`devlog:entry <sid>`)는 지우지 말 것(중복 방지 키).
- **큐레이션 메모리**: 폴더 키별 `memory/` + git 미러 `~/main/system/memory-snapshot/<키>/` (SessionEnd sync 자동 커밋).
- **메모리에 크리덴셜(암호·토큰·키) 절대 저장 금지** — 미러를 타고 원격 git에 실린다. 포인터("X는 .env 참조")만.
