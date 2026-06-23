# app/services/auth_service.py
from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader
from app.database import get_db

# This tells FastAPI to look for the 'X-API-KEY' header
api_key_header = APIKeyHeader(name="X-API-KEY", auto_error=False)

class AuthService:
    @staticmethod
    async def verify_api_key(api_key: str = Security(api_key_header)):
        """
        Base validator: Checks if the API key exists and is active.
        """
        if not api_key:
            raise HTTPException(status_code=401, detail="Missing X-API-KEY header")
        
        db = get_db()
        if not db:
            raise HTTPException(status_code=503, detail="Database unavailable")
            
        # Search for the key in the database
        key_data = await db.apikeys.find_one({"key": api_key, "isActive": True})
        
        if not key_data:
            raise HTTPException(status_code=401, detail="Invalid or inactive API Key")
        
        return key_data

class RequireScope:
    """
    Advanced Validator: Checks if the valid API key has the required permissions.
    """
    def __init__(self, required_scope: str):
        self.required_scope = required_scope

    async def __call__(self, key_data: dict = Security(AuthService.verify_api_key)):
        scopes = key_data.get("scopes", [])
        
        # 'admin' scope acts as a master key. Otherwise, check for the specific scope.
        if "admin" in scopes or self.required_scope in scopes:
            return key_data
            
        raise HTTPException(
            status_code=403, 
            detail=f"Permission denied. API Key requires scope: '{self.required_scope}'"
        )