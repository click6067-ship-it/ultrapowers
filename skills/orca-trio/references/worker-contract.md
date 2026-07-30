# Orca worker contract

모든 task spec에 다음을 넣는다.

1. 입력 파일·허용 도구·읽기/쓰기 범위·산출 경로
2. 제품 writer인지 read-only worker인지 명시
3. 전제가 깨지면 추측하지 말고 `ask` 또는 `escalation`
4. 장기 작업은 heartbeat/status
5. 성공·부분·실패 모두 `worker_done` 정확히 한 번
6. payload에 task ID, dispatch ID, 산출 경로, 상태, 검증 명령 포함
7. 자식 생성은 controller 승인과 depth/count/budget 범위 안에서만

Coordinator 인정 조건:

- task ID와 dispatch ID가 현재 배포 장부와 일치
- sender/assignee가 일치
- 중복 `worker_done`이면 첫 유효 결과만 인정하고 이후는 duplicate로 기록
- 산출 파일·commit·test가 실제 존재
- 고정 commit reviewer는 리뷰 중 target commit이 바뀌면 실패 처리
