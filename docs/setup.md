# Toolhead Manager Setup

## Installation

1. Copy `/backend/toolhead_manager.py` into Moonraker's `components/` folder.
2. Add `[toolhead_manager]` to `moonraker.conf`.
3. Restart Moonraker.

To test:
```bash
curl http://localhost:7125/toolhead_manager/status
