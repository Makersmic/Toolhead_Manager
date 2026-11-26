"""Process chains (Studio 0.40): stored here, built and run in Rhino Studio. See rhino/chains.py. The Portal never runs a
chain, starts a job or writes Klipper config for one."""
from flask import Blueprint

from .store_routes import add_store_routes

bp = Blueprint("chains", __name__)
add_store_routes(bp, "chains", "CHAINS", "chain", "rhino-chains")
