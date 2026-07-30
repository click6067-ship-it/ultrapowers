#!/usr/bin/env bash
# Orca worker provisioner v0 — 2026-07-30 실증 패턴의 실행형.
# 직렬 기동 규칙(생성→tui-idle→다음)과 handle 수집을 코드로 고정한다.
# 사용: orca-provision.sh <model[,model...]> [title-prefix]
#   예: orca-provision.sh haiku,opus,claude-fable-5 crew
# 출력: 워커당 JSON 한 줄 {"index","model","handle","idle"} — idle 실패는 즉시 중단(fail-closed).
# 주의: Claude worker에 orchestration 명령을 시킬 dispatch spec에는
#       "orca-ide는 Bash dangerouslyDisableSandbox true" 지시를 반드시 포함할 것
#       (2026-07-30 소방훈련 A-1: 샌드박스가 orchestration socket을 막는다).
set -euo pipefail

ORCA=${ORCA_CLI_COMMAND:-orca-ide}
MODELS=${1:?usage: orca-provision.sh <model[,model...]> [title-prefix]}
PREFIX=${2:-worker}
IDLE_TIMEOUT_MS=${ORCA_PROVISION_IDLE_TIMEOUT_MS:-90000}

index=0
IFS=',' read -r -a model_list <<<"$MODELS"
for model in "${model_list[@]}"; do
  index=$((index + 1))
  handle=$("$ORCA" terminal create --worktree active --title "${PREFIX}-${index}" \
    --command "claude --model ${model}" --json 2>/dev/null \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["result"]["terminal"]["handle"])')
  if [ -z "$handle" ]; then
    echo "{\"index\":${index},\"model\":\"${model}\",\"error\":\"create failed\"}" >&2
    exit 1
  fi
  idle=$("$ORCA" terminal wait --terminal="$handle" --for=tui-idle \
    --timeout-ms="$IDLE_TIMEOUT_MS" --json 2>/dev/null \
    | python3 -c 'import json,sys; d=json.load(sys.stdin)["result"]["wait"]; print("true" if d.get("satisfied") else "false")')
  echo "{\"index\":${index},\"model\":\"${model}\",\"handle\":\"${handle}\",\"idle\":${idle}}"
  if [ "$idle" != "true" ]; then
    echo "{\"error\":\"worker ${index} (${model}) did not reach tui-idle; stopping fail-closed\"}" >&2
    exit 2
  fi
done
