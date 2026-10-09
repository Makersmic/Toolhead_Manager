#!/bin/sh
# Run every check: static lint, simulated-Klipper macro and motion tests, portal HTTP tests, installer test, browser smoke test.
# The browser test needs Playwright (pip install playwright && python3 -m playwright install chromium); without it, it says SKIP.
cd "$(dirname "$0")" || exit 1
python3 lint_rhino.py && python3 test_macros.py && python3 test_motion.py && python3 test_portal.py && python3 test_extras.py \
  && python3 test_maint.py && python3 test_v12.py && python3 test_slice.py && python3 test_kiri_install.py && python3 test_install.py && python3 test_browser.py
