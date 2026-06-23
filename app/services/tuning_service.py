from .base_service import BaseService

class TuningService(BaseService):
    def get_tuning_config(self, device_id: str):
        return self.db.tuning.find_one({"deviceId": device_id}) or {}