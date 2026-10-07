"""Everything that touches the file system resolves its location here."""
import os
from dataclasses import dataclass

DEFAULT_CONFIG_DIR = "~/printer_data/config"


@dataclass(frozen=True)
class Paths:
    cfg: str  # the Klipper config directory

    @property
    def printer_cfg(self): return os.path.join(self.cfg, "printer.cfg")
    @property
    def variables_cfg(self): return os.path.join(self.cfg, "variables.cfg")
    @property
    def registry_json(self): return os.path.join(self.cfg, "myrhino", "custom_tools.json")
    @property
    def registry_cfg(self): return os.path.join(self.cfg, "myrhino", "custom_tools.cfg")
    @property
    def umbilical_json(self): return os.path.join(self.cfg, "myrhino", "umbilical.json")
    @property
    def lists_json(self): return os.path.join(self.cfg, "myrhino", "portal_lists.json")
    @property
    def state_dir(self):
        """Portal-only data (photos, restart flag). Kept NEXT TO the config dir, not inside it,
        so Klipper backups / git never fill up with pictures."""
        return os.path.join(os.path.dirname(self.cfg), "rhino_data")
    @property
    def images_dir(self): return os.path.join(self.state_dir, "images")
    @property
    def restart_flag(self): return os.path.join(self.state_dir, "restart_pending")


def resolve(config_dir=None) -> Paths:
    """Explicit argument wins, then $RHINO_CONFIG_DIR, then ~/printer_data/config."""
    d = config_dir or os.environ.get("RHINO_CONFIG_DIR") or DEFAULT_CONFIG_DIR
    return Paths(os.path.abspath(os.path.expanduser(d)))
