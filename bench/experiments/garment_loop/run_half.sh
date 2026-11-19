#!/usr/bin/env bash
# Run every arm on one half, in order (DESIGN.md section 4). Each step carries on where it stopped when run again;
# a step that hits the Claude plan's usage limit stops the whole run (exit 3).
# usage: bash run_half.sh tuning|held-out [D-small]
set -u
HALF=${1:-tuning}
cd "$(dirname "$0")"
step() { echo "== $* $(date -u +%H:%M:%S)"; python run.py "$@" --half "$HALF"; rc=$?; [ $rc -eq 3 ] && { echo "== stopped: usage limit"; exit 3; }; return 0; }
step arm-a
step describe B --runs 1,2,3
step describe C-sonnet --runs 1,2,3
step describe C-opus --runs 1,2,3
step loop D --chains 1,2,3
if [ "${2:-}" = "D-small" ]; then step loop D-small --chains 1,2,3; fi
echo "== done $(date -u +%H:%M:%S)"
