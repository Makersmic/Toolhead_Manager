#!/bin/sh
# Run every check: static lint, simulated-Klipper macro and motion tests, portal HTTP tests, real Klipper reading the config
# (SKIPs without a Klipper checkout and arm-none-eabi-gcc), installer test, browser smoke test.
# The browser test needs Playwright (pip install playwright && python3 -m playwright install chromium); without it, it says SKIP.
cd "$(dirname "$0")" || exit 1
python3 lint_rhino.py && python3 test_macros.py && python3 test_mesh.py && python3 test_motion.py && python3 test_portal.py && python3 test_backup.py && python3 test_slice_profiles.py && python3 test_hw_catalog.py && python3 test_hw_boards.py && python3 test_hw_devices.py && python3 test_job_hooks.py && python3 test_net.py && python3 test_prusa.py && python3 test_extras.py && python3 test_updater.py && python3 test_labels.py && python3 test_access.py && python3 test_trust.py && python3 test_snapshot.py \
  && python3 test_maint.py && python3 test_v12.py && python3 test_real_klipper.py && python3 test_install.py && python3 test_studio_site.py && python3 test_browser.py
