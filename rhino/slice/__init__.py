"""Slicing inside the portal (PROTOTYPE - off unless myrhino/slicer.json says "enabled": true).

    profiles.py   turns the tools the portal already knows (variables.cfg, the registry) into
                  Kiri:Moto machine profiles, so a sliced job already calls the right macros

The Kiri:Moto side (the pinned copy, its Rhino mod and the one-line patch) lives in kiri/ at the
top of the repo. Only laser tools (LightSaber) are covered in this prototype.
"""
