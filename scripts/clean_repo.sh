#!/usr/bin/env bash
# Safe repo cleanup: remove build artifacts, logs, caches and generated results
# Defaults to dry-run (no deletion). Use --force to actually delete.
# Optional flags:
#   --include-build   also remove ./build (out-of-tree build dir)
#   --include-venv    also remove ./.venv (Python virtualenv)
#   --aggressive      broaden patterns (remove extra reports like *.json/*.csv)
#   --quiet           concise output
#   --root DIR        repository root (default: script/..)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${REPO_ROOT:-${SCRIPT_DIR}/..}"
cd "${REPO_ROOT}"

# Flags
FORCE=0
INCLUDE_BUILD=0
INCLUDE_VENV=0
AGGRESSIVE=0
QUIET=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --force) FORCE=1; shift ;;
    --include-build) INCLUDE_BUILD=1; shift ;;
    --include-venv) INCLUDE_VENV=1; shift ;;
    --aggressive) AGGRESSIVE=1; shift ;;
    --quiet) QUIET=1; shift ;;
    --root) REPO_ROOT="$2"; shift 2 ;;
    *) echo "[WARN] unknown arg: $1"; shift ;;
  esac
done

# Collect targets
declare -a FILE_PATTERNS=(
  "*.o" "*.lo" "*.a" "*.so" "*.d"
  "*.tmp" "*.temp" "*~"
  "*.log"
)

# Reports and generated data that are safe to remove. Controlled by --aggressive
if [[ ${AGGRESSIVE} -eq 1 ]]; then
  FILE_PATTERNS+=( "*.csv" "*.json" )
fi

# Directories to remove (always)
declare -a DIR_TARGETS=(
  "_include_server" "+distcheck" "_testtmp"
  "logs" "results" "test_results" "real_test_results" "docker_test_results" "test_results_archive"
  "distcc_external_scheduler/logs" "distcc_external_scheduler/benchmarks/logs" "distcc_external_scheduler/benchmarks/results"
  "__pycache__" ".pytest_cache"
)

# Optionally remove build dir and venv
if [[ ${INCLUDE_BUILD} -eq 1 ]]; then
  DIR_TARGETS+=( "build" )
fi
if [[ ${INCLUDE_VENV} -eq 1 ]]; then
  DIR_TARGETS+=( ".venv" )
fi

# Exclusions to keep the repo safe
# - never touch .git
# - do not touch distcc_external_scheduler/config
EXCLUDE_PATHS=( ".git" "distcc_external_scheduler/config" )

would_delete_files=()
would_delete_dirs=()

not_expr=()
for p in "${EXCLUDE_PATHS[@]}"; do
  not_expr+=( -not -path "./${p}/*" )
  not_expr+=( -not -path "./${p}" )
done

# Exclude build and venv unless explicitly included
if [[ ${INCLUDE_BUILD} -eq 0 ]]; then
  not_expr+=( -not -path "./build/*" )
  not_expr+=( -not -path "./build" )
fi
if [[ ${INCLUDE_VENV} -eq 0 ]]; then
  not_expr+=( -not -path "./.venv/*" )
  not_expr+=( -not -path "./.venv" )
fi

# Scan files by patterns
for pat in "${FILE_PATTERNS[@]}"; do
  while IFS= read -r -d '' f; do
    would_delete_files+=("${f#./}")
  done < <(find . -type f -name "${pat}" "${not_expr[@]}" -print0)
done

# Scan directories
for d in "${DIR_TARGETS[@]}"; do
  while IFS= read -r -d '' dd; do
    would_delete_dirs+=("${dd#./}")
  done < <(find . -type d -name "$(basename "${d}")" "${not_expr[@]}" -print0)
done

# De-duplicate preserving order
unique() { awk '!seen[$0]++'; }
FILE_LIST=$(printf '%s\n' "${would_delete_files[@]:-}" | unique)
DIR_LIST=$(printf '%s\n' "${would_delete_dirs[@]:-}" | unique)

# Summary
count_files=$(printf '%s\n' "${FILE_LIST}" | sed '/^$/d' | wc -l || true)
count_dirs=$(printf '%s\n' "${DIR_LIST}" | sed '/^$/d' | wc -l || true)

if [[ ${QUIET} -ne 1 ]]; then
  echo "[CLEANUP] Repo: ${REPO_ROOT}"
  echo "[CLEANUP] Files matched: ${count_files}"
  echo "[CLEANUP] Dirs matched:  ${count_dirs}"
fi

if [[ ${FORCE} -eq 0 ]]; then
  [[ ${QUIET} -ne 1 ]] && echo "[DRY-RUN] Use --force to actually delete."
  # Print a short peek unless --quiet
  if [[ ${QUIET} -ne 1 ]]; then
    echo "--- Files (first 50) ---"
    printf '%s\n' ${FILE_LIST} | sed -n '1,50p'
    echo "--- Dirs (first 50) ---"
    printf '%s\n' ${DIR_LIST} | sed -n '1,50p'
  fi
  exit 0
fi

# Perform deletion
# Delete files first
if [[ -n "${FILE_LIST}" ]]; then
  # handle spaces safely
  printf '%s\0' ${FILE_LIST} | xargs -0 -r rm -f
fi
# Delete directories (deep)
if [[ -n "${DIR_LIST}" ]]; then
  printf '%s\0' ${DIR_LIST} | xargs -0 -r rm -rf
fi

if [[ ${QUIET} -ne 1 ]]; then
  echo "[DONE] Cleanup completed."
fi
