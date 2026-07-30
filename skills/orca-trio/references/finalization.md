# Deterministic finalization

사용자 merge/ship 승인 뒤에만 실행한다.

1. base와 candidate의 정확한 SHA를 확인한다.
2. fetch 후 divergence를 판정한다. 자동 pull/merge/rebase 금지.
3. 지정 test/lint/build를 실행하고 증거를 저장한다.
4. scoped diff와 commit identity를 확인한다.
5. 승인된 정책으로 integration·push·PR을 수행한다.
6. remote/base에 결과 SHA가 포함됐는지 확인한다.
7. 작업트리 clean과 untracked 산출물 0을 확인한다.
8. terminal을 중단하고 run을 archive한다.
9. 승인된 candidate 외 worktree/HOME/session을 제거한다.
10. terminal/worktree/task/untracked orphan 0을 다시 조회한다.

중간 실패는 `FAILED_RECOVERABLE`로 남기고 완료된 단계와 재개 위치를 기록한다. 처음부터 재실행해 외부 변경을 중복시키지 않는다.
