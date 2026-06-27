#!/usr/bin/env python3
"""statusline.py — Claude Code 상태줄 (observability).
stdin JSON(model·context_window·workspace·cost)을 받아 한 줄 출력.
무채색(daltonized 배려) — 색 대신 텍스트·기호·구분자만. python3 전용(jq 불필요).
"""
import json
import os
import subprocess
import sys

try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)

model = (d.get("model") or {}).get("display_name", "?")
cw = d.get("context_window") or {}
used = cw.get("used_percentage")
ws = d.get("workspace") or {}
cwd = ws.get("current_dir") or d.get("cwd") or os.getcwd()
base = os.path.basename(cwd.rstrip("/")) or cwd
cost = (d.get("cost") or {}).get("total_cost_usd")

branch = ""
try:
    r = subprocess.run(["git", "-C", cwd, "rev-parse", "--abbrev-ref", "HEAD"],
                       capture_output=True, text=True, timeout=2)
    if r.returncode == 0:
        branch = r.stdout.strip()
except Exception:
    pass

parts = [model]
if used is not None:
    try:
        parts.append(f"{int(float(used))}% ctx")
    except (TypeError, ValueError):
        pass
parts.append(f"📁 {base}")
if branch:
    parts.append(f"⎇ {branch}")
if cost is not None:
    try:
        parts.append(f"${float(cost):.2f}")
    except (TypeError, ValueError):
        pass

print(" | ".join(parts))
