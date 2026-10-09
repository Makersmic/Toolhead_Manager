"""The simulated Klipper (klippersim) behind a fake Moonraker's console endpoints, for trying and testing the
portal's question window against the real Rhino macros (PROTOTYPE).

    b = SimBackend(config_dir, tool=3)
    b.script("LASER_JOB_SETUP FILE=x.gcode")   -> None, or Klipper's error text
    b.store(count)                              -> Moonraker's /server/gcode_store list
    b.status()                                  -> print_state, current_tool, filename

Used by dev/demo_server.py --sim and dev/test_slice.py.
"""
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from klippersim import KlipperError, Sim  # noqa: E402


class SimBackend:
    def __init__(self, config_dir, tool=3, bed_z=150.0):
        s = Sim(config_dir).load()
        s.macro_vars["SWAP_TOOL"]["current_tool"] = tool
        names = {1: "BlockOne", 2: "SwitchFly", 3: "LightSaber", 4: "HotJoe", 5: "DragKnife"}
        s.save_vars.update(current_tool=tool, set_material_toolhead=names.get(tool, ""), set_material_material="PLYWOOD")
        s.objects["toolhead"]["position"]["z"] = bed_z
        s.objects["gcode_move"]["gcode_position"]["z"] = bed_z
        s.objects["toolhead"]["homed_axes"] = "xyz"

        def skp(p, rest):          # SET_KINEMATIC_POSITION: the bed is where Set Z zero says it is
            s.objects["toolhead"]["position"]["z"] = float(p.get("Z", s.objects["toolhead"]["position"]["z"]))

        def start_file(p, rest):   # SDCARD_PRINT_FILE: the job is running now
            s.objects["print_stats"]["state"] = "printing"
            s.objects["print_stats"]["filename"] = str(p.get("FILENAME", "")).strip('"')

        s.extra_cmds = {"SET_KINEMATIC_POSITION": skp, "SDCARD_PRINT_FILE": start_file}
        s.responses = []
        self.sim, self.lock, self._store = s, threading.Lock(), []

    def _log(self, message, typ):
        self._store.append({"message": message, "time": time.time(), "type": typ})

    def script(self, text):
        """Run a console command like Moonraker's /printer/gcode/script. -> None, or Klipper's error."""
        with self.lock:
            self._log(text, "command")
            s = self.sim
            s.responses = []
            err = None
            try:
                s.run_script(text)
            except KlipperError as e:
                err = str(e)
            for line in s.responses:
                self._log(line, "response")
            if err:
                self._log("!! " + err, "response")
            return err

    def store(self, count=200):
        with self.lock:
            return list(self._store[-int(count):])

    def status(self):
        with self.lock:
            ps = self.sim.objects["print_stats"]
            return {"print_state": ps.get("state", "standby"), "filename": ps.get("filename", ""),
                    "current_tool": int(self.sim.macro_vars["SWAP_TOOL"]["current_tool"])}

    NAMES = {1: "BlockOne", 2: "SwitchFly", 3: "LightSaber", 4: "HotJoe", 5: "DragKnife"}

    def set_tool(self, slot):
        """As if the swap wizard had been answered: the mounted tool and the job's tool both change."""
        with self.lock:
            self.sim.macro_vars["SWAP_TOOL"]["current_tool"] = int(slot)
            self.sim.save_vars.update(current_tool=int(slot), set_material_toolhead=self.NAMES.get(int(slot), ""))

    def set_state(self, state):
        with self.lock:
            self.sim.objects["print_stats"]["state"] = state
