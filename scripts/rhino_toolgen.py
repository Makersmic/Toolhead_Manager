#!/usr/bin/env python3
"""Thin launcher so Klipper's gcode_shell_command can call the rhino package from any directory."""
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from rhino.cli import main  # noqa: E402

sys.exit(main())
