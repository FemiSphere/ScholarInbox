#!/usr/bin/env bash
set -euo pipefail

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

cd "$PROJECT_ROOT"

CONDA_ENV_PYTHON="/opt/homebrew/Caskroom/miniforge/base/envs/literature-digest-mac/bin/python"

if [[ -x "$PROJECT_ROOT/.venv/bin/python" ]]; then
  PYTHON="$PROJECT_ROOT/.venv/bin/python"
elif [[ -x "$CONDA_ENV_PYTHON" ]]; then
  PYTHON="$CONDA_ENV_PYTHON"
else
  PYTHON="$(command -v python3 || command -v python)"
fi

"$PYTHON" -m literature_digest "$@" 2>&1 | tee "$LOG_FILE"

printf '\nLog saved to: %s\n' "$LOG_FILE"
printf 'Output directory: %s\n' "$PROJECT_ROOT/outputs"
