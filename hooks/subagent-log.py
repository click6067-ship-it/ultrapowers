#!/usr/bin/env python3
"""subagent-log.py — SubagentStop 훅 (observability). 서브에이전트 완료를 로그에 기록만(차단 안 함).
stdin: SubagentStop JSON. 실측 payload 키(2026-07-03 확인): agent_id, agent_type, agent_transcript_path,
session_id, cwd, permission_mode, prompt_id, last_assistant_message, transcript_path, hook_event_name,
stop_hook_active, background_tasks, session_crons. (model·tokens·duration은 top-level에 없음 —
agent_transcript_path의 assistant 메시지에서 파생: model, usage 합산, 타임스탬프 duration.)
출력: JSONL 1줄/이벤트 → logs/subagents.jsonl (구 subagents.log tab 포맷은 파서 없음이 확인돼 전환 — 과거 로그는 보존).
"""
import json
import os
import re
import sys
import shutil
import subprocess
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:  # 2026-07-29 감사: 서브에이전트 최종 메시지가 무마스킹으로 jsonl에 남고 있었다.
    from redaction import redact
except Exception:
    def redact(s):
        return s

try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)


def derive_from_transcript(path):
    """agent transcript(JSONL)에서 model·usage 합산·duration·turns 파생 — 실패 시 빈 dict (비차단)."""
    out = {}
    try:
        from datetime import datetime

        model = None
        turns = 0
        usage_by_msg = {}  # message id별 dedupe (한 API 메시지가 여러 라인으로 나뉘어 중복 합산 방지)
        first_ts = last_ts = None
        with open(path) as f:
            for line in f:
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                ts = row.get("timestamp")
                if ts:
                    first_ts = first_ts or ts
                    last_ts = ts
                if row.get("type") != "assistant":
                    continue
                msg = row.get("message") or {}
                model = msg.get("model") or model
                mid = msg.get("id") or f"line{turns}"
                if mid not in usage_by_msg:
                    turns += 1
                    u = msg.get("usage")
                    if isinstance(u, dict):
                        usage_by_msg[mid] = u
        if model:
            out["model"] = model
        if turns:
            out["turns"] = turns
        totals = {}
        for u in usage_by_msg.values():
            for k in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"):
                v = u.get(k)
                if isinstance(v, (int, float)):
                    totals[k] = totals.get(k, 0) + v
        if totals:
            out["usage"] = totals
        if first_ts and last_ts:
            try:
                t0 = datetime.fromisoformat(first_ts.replace("Z", "+00:00"))
                t1 = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
                out["duration_ms"] = int((t1 - t0).total_seconds() * 1000)
            except Exception:
                pass
    except Exception:
        pass
    return out


rec = {"ts": int(time.time())}
# top-level payload에서 존재하는 것만 (없으면 생략)
for key in ("agent_type", "agent_id", "session_id", "cwd", "permission_mode", "prompt_id"):
    v = d.get(key)
    if v:
        rec[key] = v
if not rec.get("agent_type") and d.get("subagent_type"):
    rec["agent_type"] = d["subagent_type"]
lam = d.get("last_assistant_message")
if isinstance(lam, str) and lam:
    rec["last_message"] = redact(lam[:200])
atp = d.get("agent_transcript_path")
if atp:
    rec["agent_transcript_path"] = atp
    rec.update(derive_from_transcript(atp))

try:
    cc = os.environ.get("COMMAND_CENTER") or os.path.join(os.path.expanduser("~"), "main")
    log = os.path.join(cc, "logs", "subagents.jsonl")
    os.makedirs(os.path.dirname(log), exist_ok=True)
    if os.path.exists(log) and os.path.getsize(log) > 512_000:  # 로테이션: 최근 5000줄만 보존
        with open(log) as f:
            tail = f.readlines()[-5000:]
        with open(log, "w") as f:
            f.writelines(tail)
    with open(log, "a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
except Exception:
    pass

# WSL Windows toast — 긴 서브에이전트(>60s) 완료 시 데스크톱 알림(자리 비웠을 때, 2026-07-03 엔지니어 벤치마크).
# best-effort·비차단(detached)·무음 실패. 끄기: CC_TOAST=0.
try:
    dur = rec.get("duration_ms") or 0
    if os.environ.get("CC_TOAST", "1") != "0" and dur > 60_000 and shutil.which("powershell.exe"):
        # PS 문자열에 f-string으로 직접 들어가므로 따옴표·백틱이 든 커스텀 에이전트명은
        # 구문을 깬다 → 화이트리스트 정규화 (2026-07-29 감사).
        at = re.sub(r"[^A-Za-z0-9_.:-]", "_", str(rec.get("agent_type", "agent")))[:40] or "agent"
        secs = int(dur / 1000)
        ps = (
            "Add-Type -AssemblyName System.Windows.Forms;"
            "$b=New-Object System.Windows.Forms.NotifyIcon;"
            "$b.Icon=[System.Drawing.SystemIcons]::Information;$b.Visible=$true;"
            f"$b.ShowBalloonTip(5000,'Claude Code','{at} 완료 ({secs}s)',"
            "[System.Windows.Forms.ToolTipIcon]::Info);Start-Sleep -Seconds 5;$b.Dispose()"
        )
        subprocess.Popen(  # noqa — detached, 대기 안 함
            ["powershell.exe", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
except Exception:
    pass
sys.exit(0)
