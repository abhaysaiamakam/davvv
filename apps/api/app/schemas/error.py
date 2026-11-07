from pydantic import BaseModel, Field


class ApiErrorResponse(BaseModel):
    detail: str = Field(..., description="Human-readable error explanation")
    status_code: int = Field(..., description="HTTP status code")
    error_code: str = Field(..., description="Machine-readable error identifier")
    timestamp: str = Field(..., description="ISO 8601 UTC timestamp")

