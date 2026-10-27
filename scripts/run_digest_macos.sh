#!/bin/bash
set -euo pipefail

# Keep the launcher usable even when a terminal profile overwrites PATH.
export PATH="/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

export PYTHONIOENCODING=utf-8
export PYTHONUTF8=1
export PYTHONDONTWRITEBYTECODE=1

if [[ -n "${SCHOLAR_INBOX_PROXY_URL:-}" ]]; then
  export http_proxy="$SCHOLAR_INBOX_PROXY_URL"
  export https_proxy="$SCHOLAR_INBOX_PROXY_URL"
  export HTTP_PROXY="$SCHOLAR_INBOX_PROXY_URL"
  export HTTPS_PROXY="$SCHOLAR_INBOX_PROXY_URL"
elif [[ -n "${CODEX_PROXY_URL:-}" && -z "${https_proxy:-}${HTTPS_PROXY:-}" ]]; then
  export http_proxy="$CODEX_PROXY_URL"
  export https_proxy="$CODEX_PROXY_URL"
  export HTTP_PROXY="$CODEX_PROXY_URL"
  export HTTPS_PROXY="$CODEX_PROXY_URL"
fi

if [[ -n "${CODEX_ALL_PROXY_URL:-}" && -z "${all_proxy:-}${ALL_PROXY:-}" ]]; then
  export all_proxy="$CODEX_ALL_PROXY_URL"
  export ALL_PROXY="$CODEX_ALL_PROXY_URL"
fi

if [[ -n "${SCHOLAR_INBOX_PROXY_URL:-}" ]]; then
  SCHOLAR_INBOX_EFFECTIVE_NO_PROXY="${SCHOLAR_INBOX_NO_PROXY:-localhost,127.0.0.1,::1}"
  export no_proxy="$SCHOLAR_INBOX_EFFECTIVE_NO_PROXY"
  export NO_PROXY="$SCHOLAR_INBOX_EFFECTIVE_NO_PROXY"
  unset SCHOLAR_INBOX_EFFECTIVE_NO_PROXY
elif [[ -n "${CODEX_NO_PROXY:-}" && -z "${no_proxy:-}${NO_PROXY:-}" ]]; then
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

CONDA_COMMAND=""
if [[ -n "${CONDA_EXE:-}" && -x "$CONDA_EXE" ]]; then
  CONDA_COMMAND="$CONDA_EXE"
elif command -v conda >/dev/null 2>&1; then
  CONDA_COMMAND="$(command -v conda)"
elif [[ -x "/opt/homebrew/bin/conda" ]]; then
  CONDA_COMMAND="/opt/homebrew/bin/conda"
elif [[ -x "/usr/local/bin/conda" ]]; then
  CONDA_COMMAND="/usr/local/bin/conda"
fi

CONDA_BASE=""
if [[ -n "$CONDA_COMMAND" ]]; then
  CONDA_BASE="$("$CONDA_COMMAND" info --base 2>/dev/null || true)"
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
  PYTHON="$(command -v python3 || command -v python || true)"
fi

if [[ -z "$PYTHON" ]]; then
  printf 'Error: ScholarInbox requires Python 3.12 or newer, but no Python interpreter was found.\n' \
    | tee -a "$LOG_FILE" >&2
  exit 2
fi

if ! "$PYTHON" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)'; then
  PYTHON_VERSION="$("$PYTHON" --version 2>&1 || true)"
  printf 'Error: ScholarInbox requires Python 3.12 or newer; detected %s at %s.\n' \
    "$PYTHON_VERSION" "$PYTHON" | tee -a "$LOG_FILE" >&2
  exit 2
fi

printf 'Python interpreter: %s\n' "$PYTHON" >> "$LOG_FILE"
"$PYTHON" --version >> "$LOG_FILE" 2>&1

set +e
"$PYTHON" -m literature_digest "$@" 2> >(tee -a "$LOG_FILE" >&2)
EXIT_STATUS=$?
set -e

printf 'Exit status: %s\n' "$EXIT_STATUS" >> "$LOG_FILE"
exit "$EXIT_STATUS"
