---
name: techreport
description: 기술보고서를 작성해 docx로 변환하고 GitHub 레포에 업로드하는 워크플로. 트러블슈팅 내역·변경로그·발전과정을 상세 타임스탬프(인간 기록용)로 정리. "기술보고서 만들어", "techreport", "이 작업 보고서로", "트러블슈팅 문서화", "보고서 docx로 깃허브에" 요청 시. 산출물 = report.md + report.docx + (선택) 새 private GitHub 레포 + 업로드.
---

# /techreport — 기술보고서 → docx → GitHub

작업·시스템·트러블슈팅 이력을 **사람이 읽는 상세 기술보고서**로 만들고, docx로 변환해, GitHub 레포에 올린다.
핵심: **날짜·시간을 세부적으로**(인간 기록용 — "언제 무엇이 왜 바뀌었나"가 추적되게).

## 언제 / 조건
- 큰 작업·시스템 변경·디버깅 세션을 정식 문서로 남길 때.
- 출력 대상 = 👤 사람(미래의 나 포함). Claude용 운영 정본(SYSTEM.md류)과는 별개 — 이건 *서사·이력*.

## 단계

### 0. 환경 확인
```bash
command -v pandoc || echo "NO_PANDOC — 설치: 'brew install pandoc' 또는 배포판 패키지"
command -v gh && gh auth status 2>&1 | grep -m1 "Logged in" || echo "NO_GH — 'gh auth login' 필요(업로드 단계 한정)"
git log -3 --format=%ae   # 커밋 이메일 트랩: 정상 배포 이메일 확인 후 사용
```

### 1. 사료 수집 (타임스탬프가 생명)
- **변경로그**: `git -C <repo> log --format="%ci | %h | %s"` (커밋 시각 그대로 — ISO).
- **트러블슈팅 내역**: 무엇이 깨졌나 → 증상 → 원인(근본) → 해결 → 배운점. 가능하면 발견·수정 시각.
- **발전과정**: 시간순 마일스톤 (init → 기능 → 리팩터 → 결정 번복 등).
- **결정 로그**: `decisions/log.md` 같은 데서 "왜 그렇게 정했나".
- 세션 로그(`$COMMAND_CENTER/logs/`)·메모리에서 맥락 보강.

### 2. 보고서 markdown 작성 (`<name>-report.md`)
표준 헤더(`👤 사람용 · 의도 · 언제 · 기준일시`) + 아래 골격. **모든 이벤트에 날짜/시간**:
```
1. 요약 (한 문단 + 한눈 표)
2. 시스템/대상 구조 (무엇으로 이루어졌나)
3. 작동 원리 (어떻게 도나)
4. 트러블슈팅 내역 (시간순 표: 시각 · 증상 · 원인 · 해결)
5. 변경로그 (git 시각 그대로, 최신→과거)
6. 발전과정 (마일스톤 타임라인)
7. 발견된 이슈 / 개선점 (severity + 조치/플래그)
8. 부록 (검증 로그·출처·링크)
```
- 기준일시 명시: `> 작성: YYYY-MM-DD HH:MM (TZ)`.
- 숫자·경로·버전은 **실측**으로(추측 금지). 출처 있으면 인용.

### 3. docx 변환 (pandoc)
```bash
pandoc <name>-report.md -o <name>-report.docx \
  --toc --toc-depth=3 -V lang=ko \
  --metadata title="<제목>" --metadata date="$(date +%Y-%m-%d)"
# 스타일 레퍼런스 있으면: --reference-doc=<ref.docx>
```
변환 후 `ls -la <name>-report.docx`로 생성 확인.

### 4. 산출물 배치 + GitHub push

**`$COMMAND_CENTER/reports/` + (opt-in) SessionEnd hook 자동 push** — *techreport-autopush.py가 `settings.json` SessionEnd에 활성화돼 있으면, 프로젝트 끝에 보고서가 사용자 개입 0으로 GitHub에 올라감. (공개 템플릿 기본은 비활성 — 직접 opt-in.)*
```bash
DIR=$COMMAND_CENTER/reports/<proj>-$(date +%F); mkdir -p "$DIR"
# 보안: 보고서에 토큰·키 값이 들어갔으면 push 전 검토(변수명·건수는 OK, 실제 값은 마스킹).
cp <name>-report.md <name>-report.docx "$DIR/"
touch $COMMAND_CENTER/reports/.push-pending      # ← SessionEnd hook(techreport-autopush.py)이 감지
```
세션 종료 시 `techreport-autopush.py`가 `.push-pending` 마커를 보고 `$COMMAND_CENTER`을 자동 commit+push(reports/만, 정상 이메일 고정, 실패는 조용히). **skill = 보고서 작성(LLM) / hook = GitHub push(셸)** 분담 — hook은 셸이라 LLM 보고서를 못 쓰므로 이 구조가 정석.

**(옵션) 별도 private 레포** — 보고서를 독립 레포로 원할 때(민감내용 → `--private`, 공개는 명시 확인 시만):
```bash
WORK=$(mktemp -d) && chmod 700 "$WORK"
cp <name>-report.md <name>-report.docx "$WORK/"
cd "$WORK" && git init -q && git add -A
git -c user.email="<배포정상이메일>" -c user.name="<git 사용자명>" commit -qm "docs: <제목> (YYYY-MM-DD)"
gh repo create <owner>/<repo> --private --source=. --remote=origin --push
cd / && rm -rf "$WORK"
```
- 끝나면 위치(또는 레포 URL)를 사용자에게 보고.

### 5. 마무리
- 보고서 md는 소스 레포(예: `$COMMAND_CENTER/system/`)에도 두면 버전관리됨.
- 커스텀 스킬/시스템 변경을 동반했으면 `dotclaude/sync.sh`로 미러 갱신.

## 함정
- **pandoc 없으면** docx 단계 막힘 — 설치 안내 후 md까지만 산출.
- **커밋 이메일**: Vercel 연동 레포는 미스매치 이메일 차단(`git log -3 --format=%ae` 확인). 일반 레포도 계정 일관성 위해 noreply 이메일 권장.
- **보안**: 보고서에 토큰·키·민감경로 들어가면 push 전 검토. 기본 private.
- **타임스탬프 누락 금지**: "최근에"·"얼마전" 금지, 실제 시각 박을 것(인간 기록용).
