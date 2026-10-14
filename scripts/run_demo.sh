#!/usr/bin/env sh
# SPDX-License-Identifier: MPL-2.0
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
export PYTHONUTF8=1
if [ "${1:-}" = "--skip-install" ]; then
    python3 -m cst.demo
else
    if [ ! -x .venv/bin/python ]; then python3 -m venv .venv; fi
    .venv/bin/python -m pip install -e ".[dxf]"
    .venv/bin/python -m cst.demo
fi
