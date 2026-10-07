#!/usr/bin/env python3
"""Start the Rhino tool portal:  python3 scripts/rhino_portal.py [--port 5000]"""
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from rhino.portal.__main__ import main  # noqa: E402

main()
