from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = Field(..., examples=["ok"])
    app: str
    version: str
    database: str = Field(..., description="connected | disconnected")
