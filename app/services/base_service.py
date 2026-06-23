from app.database import get_db

class BaseService:
    @property
    def db(self):
        return get_db()