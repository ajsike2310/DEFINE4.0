"""One error type for the whole backend. Rendered by main.py as {"error": {code, message, details}}."""
from fastapi import HTTPException


class ApiError(HTTPException):
    def __init__(self, status: int, code: str, message: str, details=None, headers: dict | None = None):
        super().__init__(status_code=status, detail={"code": code, "message": message, "details": details}, headers=headers)
