# Orca worker contract

모든 task spec에 다음을 넣는다.

1. 입력 파일·허용 도구·읽기/쓰기 범위·산출 경로
2. 제품 writer인지 read-only worker인지 명시
3. 전제가 깨지면 추측하지 말고 `ask` 또는 `escalation`
4. 장기 작업은 heartbeat/status
5. 성공·부분·실패 모두 `worker_done` 정확히 한 번
6. payload에 task ID, dispatch ID, 산출 경로, 상태, 검증 명령 포함
7. 자식 생성은 controller 승인과 depth/count/budget 범위 안에서만
8. **writer 브리프에 타겟 테스트 목록** (2026-07-30): 구현 task는 "통과시켜야 할 테스트"(파일::테스트명 — writing-plans의 Target Tests에서)를 브리프에 명시한다. "TDD 하라" 지시가 아니라 목표 테스트를 주는 방식이 실증적으로 작동한다(TDAD).
   - **착수 전제 (하드):** Target Tests 목록이 없는 구현 브리프를 받은 writer는 착수 전에 최소 1개의 실패 테스트를 먼저 만들거나 `ask`로 반려한다 — 목록 없는 구현 착수 금지. specpack을 안 거친 직행 경로에도 이 전제가 걸린다(테스트 목록 한 줄만 요구하므로 스테이크 비례와 충돌하지 않음).
   - **RED 증거 캡처:** coordinator는 dispatch 전에 타겟 테스트를 실제로 돌려 **실패 출력을 run 디렉토리에 저장**한다(비쌀 것 없음 — 실패가 정상인 실행 1회). 완료 시 같은 테스트의 통과 출력과 쌍을 이뤄야 "테스트 선행"이 산출물로 증명된다 — writer에게 지시가 아니라 하네스가 검사한다.

## 테스트 소유권 (2026-07-30)

- 계획의 Target Tests와 기존 테스트는 **계약**이다. writer가 테스트를 삭제·단언 완화·SKIP 전환하면 reviewer는 사유 불문 **자동 REVISE** — 정당한 변경이면 writer가 사유를 적어 escalation으로 올리고 coordinator/사용자가 승인한 뒤에만 반영한다.
- reviewer 체크 1줄: diff에 비가역 결정(마이그레이션·스키마·API 계약·신규 의존성)이 있는데 ADR이 없으면 minor REVISE.

## 리뷰 수용 프로토콜 (2026-07-30 — 판단 기준을 톤에서 증거로)

- **reviewer 의무:** 지적마다 재현 수단(실패하는 커맨드·테스트·구체 시나리오 + 파일:줄)을 붙인다. 재현 수단이 없으면 그 지적은 "의견"으로 강등되어 REVISE 사유가 못 된다. 프롬프트는 적대 강요가 아니라 **증거 요구형** — 결함 수 할당·무조건 REVISE 압박 금지(오탐 강요는 약한-리뷰어-후퇴 경로).
- **writer 의무:** 각 지적의 재현을 실제로 돌린다 → 재현되면 수용 / 재현 안 되면 반증 첨부 기각 / 판단 불가면 사용자 escalation. **리뷰어의 확신 톤은 수용 근거가 아니다.**
- **사용자 가시성:** 라운드 종료 보고에 전 지적의 처리표(수용·기각·보류 + 각 근거 1줄)를 포함한다 — 기각한 지적도 전부 보이게.

Coordinator 인정 조건:

- task ID와 dispatch ID가 현재 배포 장부와 일치
- sender/assignee가 일치
- 중복 `worker_done`이면 첫 유효 결과만 인정하고 이후는 duplicate로 기록
- 산출 파일·commit·test가 실제 존재
- 고정 commit reviewer는 리뷰 중 target commit이 바뀌면 실패 처리
- 구현 task는 브리프의 타겟 테스트가 실제 통과했는지 확인 (verify.sh TEST_GAP 경고 시 사유 확인)
