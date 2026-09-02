#!/bin/bash
set -euo pipefail

# Keep the launcher usable even when a terminal profile overwrites PATH.
export PATH="/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

export PYTHONIOENCODING=utf-8
export PYTHONUTF8=1
export PYTHONDONTWRITEBYTECODE=1

if [[ -n "${CODEX_PROXY_URL:-}" && -z "${https_proxy:-}${HTTPS_PROXY:-}" ]]; then
  export http_proxy="$CODEX_PROXY_URL"
  export https_proxy="$CODEX_PROXY_URL"
  export HTTP_PROXY="$CODEX_PROXY_URL"
  export HTTPS_PROXY="$CODEX_PROXY_URL"
fi

if [[ -n "${CODEX_ALL_PROXY_URL:-}" && -z "${all_proxy:-}${ALL_PROXY:-}" ]]; then
  export all_proxy="$CODEX_ALL_PROXY_URL"
  export ALL_PROXY="$CODEX_ALL_PROXY_URL"
fi

if [[ -n "${CODEX_NO_PROXY:-}" && -z "${no_proxy:-}${NO_PROXY:-}" ]]; then
  export no_proxy="$CODEX_NO_PROXY"
  export NO_PROXY="$CODEX_NO_PROXY"
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$PROJECT_ROOT/logs"
mkdir -p "$LOG_DIR"

TIMESTAMP="$(date +"%Y%m%d-%H%M%S")"
LOG_FILE="$LOG_DIR/digest-$TIMESTAMP.log"
export LITERATURE_DIGEST_RUN_LOG="$LOG_FILE"

cd "$PROJECT_ROOT"

CONDA_BASE=""
if command -v conda >/dev/null 2>&1; then
  CONDA_BASE="$(conda info --base 2>/dev/null || true)"
fi
CONDA_ENV_PYTHON="${CONDA_BASE:+$CONDA_BASE/envs/scholar-inbox-mac/bin/python}"
LEGACY_CONDA_ENV_PYTHON="${CONDA_BASE:+$CONDA_BASE/envs/literature-digest-mac/bin/python}"

if [[ -x "$PROJECT_ROOT/.venv/bin/python" ]]; then
  PYTHON="$PROJECT_ROOT/.venv/bin/python"
elif [[ -x "$CONDA_ENV_PYTHON" ]]; then
  PYTHON="$CONDA_ENV_PYTHON"
elif [[ -x "$LEGACY_CONDA_ENV_PYTHON" ]]; then
  PYTHON="$LEGACY_CONDA_ENV_PYTHON"
else
  PYTHON="$(command -v python3 || command -v python)"
fi

set +e
"$PYTHON" -m literature_digest "$@" 2> >(tee -a "$LOG_FILE" >&2)
EXIT_STATUS=$?
set -e

printf '\nLog saved to: %s\n' "$LOG_FILE" | tee -a "$LOG_FILE"
printf 'Output directory: %s\n' "$PROJECT_ROOT/outputs" | tee -a "$LOG_FILE"
exit "$EXIT_STATUS"
