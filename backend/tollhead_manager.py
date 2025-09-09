# toolhead_manager.py
# Moonraker extension stub for Toolhead Manager

import logging

class ToolheadManager:
    def __init__(self, config):
        self.config = config
        self.server = config.get_server()
        self.server.register_endpoint(
            "/toolhead_manager/status", ["GET"], self.get_status
        )
        logging.info("Toolhead Manager initialized")

    async def get_status(self, web_request):
        return {"status": "ok"}

def load_component(config):
    return ToolheadManager(config)
