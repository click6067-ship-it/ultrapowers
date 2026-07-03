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

def git(*args):
    try:
        r = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, timeout=2)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


branch = git("rev-parse", "--abbrev-ref", "HEAD")
# worktree 표시 (연결된 worktree면 git-dir != common-dir) — 2026-07-03 엔지니어 벤치마크 채택
is_worktree = bool(branch) and git("rev-parse", "--git-dir") != git("rev-parse", "--git-common-dir")
# 미커밋 변경 규모(blast-radius·비용의식) — +ins/-del
changed = ""
if branch:
    ss = git("diff", "--shortstat")  # 예: " 3 files changed, 42 insertions(+), 10 deletions(-)"
    import re as _re
    ins = _re.search(r"(\d+) insertion", ss)
    dele = _re.search(r"(\d+) deletion", ss)
    if ins or dele:
        changed = f"±{(ins.group(1) if ins else '0')}/{(dele.group(1) if dele else '0')}"

parts = [model]
if used is not None:
    try:
        parts.append(f"{int(float(used))}% ctx")
    except (TypeError, ValueError):
        pass
parts.append(f"📁 {base}")
if branch:
    parts.append(f"⎇ {'⌥' if is_worktree else ''}{branch}")
if changed:
    parts.append(changed)
if cost is not None:
    try:
        parts.append(f"${float(cost):.2f}")
    except (TypeError, ValueError):
        pass

print(" | ".join(parts))
