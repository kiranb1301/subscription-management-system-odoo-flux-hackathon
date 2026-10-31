from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.models.enums import NotificationStatus


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    message: str
    status: NotificationStatus
    related_type: Optional[str] = None
    related_id: Optional[int] = None
    created_at: datetime
    read_at: Optional[datetime] = None