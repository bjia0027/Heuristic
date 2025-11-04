#!/usr/bin/env bash
# Out-of-tree build helper for distcc
# Creates a separate build directory and runs configure/make there so that
# all .o/.d and other artifacts stay out of the source tree.
#
# Usage examples:
#   scripts/out_of_tree_build.sh                 # uses ./build, auto -j$(nproc)
#   BUILD_DIR=out scripts/out_of_tree_build.sh   # custom build dir
#   JOBS=24 PREFIX=/usr/local scripts/out_of_tree_build.sh  # custom flags
#
# Env vars:
#   BUILD_DIR:   build directory path (default: build)
#   JOBS:        parallel jobs for make (default: $(nproc))
#   PREFIX:      installation prefix for configure (default: /usr/local)
#   CONFIGURE_EXTRA: extra flags passed to configure (e.g., --disable-Werror)
#
# Exit on any error and treat unset vars as errors
set -euo pipefail

# Resolve repo root (directory containing this script)/..
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

BUILD_DIR="${BUILD_DIR:-build}"
JOBS="${JOBS:-$(nproc || echo 4)}"
PREFIX="${PREFIX:-/usr/local}"
CONFIGURE_EXTRA="${CONFIGURE_EXTRA:-}"

# Create build directory absolute path
if [[ "${BUILD_DIR}" = /* ]]; then
  BUILD_ABS="${BUILD_DIR}"
else
  BUILD_ABS="${REPO_ROOT}/${BUILD_DIR}"
fi

mkdir -p "${BUILD_ABS}"

# Autoconf configure lives at repo root as ./configure
if [[ ! -x "${REPO_ROOT}/configure" ]]; then
  echo "[ERROR] configure script not found at ${REPO_ROOT}/configure" >&2
  echo "Run 'autoreconf -fi' or ensure you are at the repo root." >&2
  exit 1
fi

# Show a concise plan
cat <<EOF
[distcc OOT Build]
- Source:   ${REPO_ROOT}
- Build dir:${BUILD_ABS}
- Prefix:   ${PREFIX}
- Jobs:     ${JOBS}
- Extra:    ${CONFIGURE_EXTRA}
EOF

# Run configure in build dir, pointing src to repo root (../configure)
pushd "${BUILD_ABS}" >/dev/null

# If config.status exists and matches current prefix/args, we can skip reconfigure
if [[ ! -f config.status ]]; then
  "${REPO_ROOT}/configure" --prefix="${PREFIX}" ${CONFIGURE_EXTRA}
fi

# Ensure expected object output directories exist for Makefile patterns like src/*.o, popt/*.o, lzo/*.o
mkdir -p src popt lzo || true

# Build
make -j"${JOBS}"

# Optional target from env: TARGET=install or check
if [[ "${TARGET:-}" != "" ]]; then
  make -j"${JOBS}" "${TARGET}"
fi

popd >/dev/null

echo "[OK] Build finished in ${BUILD_ABS}. Artifacts remain out-of-tree."
