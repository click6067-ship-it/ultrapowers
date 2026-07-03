# ⚠️ 반복 함정

- **커밋 author 이메일**: Vercel git연동이 미스매치 이메일을 차단. 새 작업 전 `git log -3 --format=%ae`로 정상 배포된 이메일 확인 후 사용. (`you@example.com`은 차단 이력 — 개인 git 기본 이메일 주의.)
- **빌트인 슬래시·플러그인 설치**(`/plugin`, `/codex:*` 등)는 사용자가 직접 입력해야 함 (Claude가 대신 실행 못 함).
- **WSL chromium**: libs는 settings.json env(`LD_LIBRARY_PATH`)로 해결됨.
- **codex exec**: stdin 안 닫으면 무한 대기(`< /dev/null` 필수) · 글로벌 플래그(-s/-c)는 `resume` *앞에* · 백그라운드 실행 함정은 CPX 메모리 codex-exec-background-traps 참조.
- **ffmpeg**: 시스템 미설치 — `~/.claude/tools/headless/node_modules/ffmpeg-static` 바이너리 사용.
