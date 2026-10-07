#!/bin/sh
# Run every check: static lint, simulated-Klipper macro tests, portal HTTP tests.
cd "$(dirname "$0")" || exit 1
python3 lint_rhino.py && python3 test_macros.py && python3 test_portal.py && python3 test_extras.py && python3 test_maint.py && python3 test_v12.py
