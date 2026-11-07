from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = Field(default="ok", description="API health status ('ok', 'degraded', 'error')")
    app_name: str = Field(default="CropLens API", description="Application name")
    version: str = Field(default="0.1.0", description="API version")
    environment: str = Field(default="development", description="Runtime environment")
    timestamp: str = Field(..., description="ISO 8601 UTC timestamp")

