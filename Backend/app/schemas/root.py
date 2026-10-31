from pydantic import BaseModel


class RootResponse(BaseModel):
    application: str
    version: str
    docs: str
    health: str