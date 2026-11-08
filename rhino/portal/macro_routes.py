"""Your macros (1.9.13): stored here, built and run in Rhino Studio. See rhino/user_macros.py and
docs/phase-macro-builder.md. The Portal never runs a macro and never writes Klipper config for one."""
from flask import Blueprint

from .store_routes import add_store_routes

bp = Blueprint("macros", __name__)
add_store_routes(bp, "user-macros", "MACROS", "macro", "rhino-macros")
