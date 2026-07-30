#!/usr/bin/env bash
set -euo pipefail
# Orca managed WSL CLI launcher; repaired by sync-orca-codex-home.py.
# ORCA_WIN_LAUNCHER_B64=__ORCA_WIN_LAUNCHER_B64__
ORCA_WIN_LAUNCHER_B64='__ORCA_WIN_LAUNCHER_B64__'
ORCA_BRIDGE_PS1="${HOME}/.local/share/orca/orca-wsl-bridge.ps1"

if command -v powershell.exe >/dev/null 2>&1; then
  ORCA_POWERSHELL=powershell.exe
elif [ -x /mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe ]; then
  ORCA_POWERSHELL=/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe
else
  echo "Orca WSL CLI requires Windows interop and could not find powershell.exe." >&2
  exit 1
fi

ORCA_WIN_LAUNCHER=$(printf '%s' "$ORCA_WIN_LAUNCHER_B64" | base64 -d)
# A shell can outlive a deleted worktree. Repair cwd before WSL interop resolves it.
ORCA_WSL_CWD=$(pwd -P 2>/dev/null) || {
  ORCA_WSL_CWD=/
  cd /
}
ORCA_BRIDGE_PS1_WIN=$(wslpath -w "$ORCA_BRIDGE_PS1")
ORCA_WSL_CWD_WIN=$(wslpath -w "$ORCA_WSL_CWD")
# PowerShell -File can bind GNU flags as its own parameters. Transport the exact
# argv vector as one JSON/Base64 value so spaces, quotes, and --flags survive.
ORCA_FORWARD_ARGS_B64=$(
  python3 -c 'import base64,json,sys; print(base64.b64encode(json.dumps(sys.argv[1:],ensure_ascii=False).encode()).decode())' "$@"
)

exec "$ORCA_POWERSHELL" -NoProfile -ExecutionPolicy Bypass \
  -File "$ORCA_BRIDGE_PS1_WIN" \
  -OrcaLauncher "$ORCA_WIN_LAUNCHER" \
  -WslCwd "$ORCA_WSL_CWD_WIN" \
  -ForwardArgsB64 "$ORCA_FORWARD_ARGS_B64"
