from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import PageParams, get_current_user, require_staff
from app.db.session import get_db
from app.models import User
from app.schemas.common import Page
from app.schemas.notification import NotificationResponse
from app.services import notification_service as service

router = APIRouter()


@router.get("", response_model=Page[NotificationResponse])
def list_notifications(
    unread_only: bool = Query(False),
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items, total = service.list_notifications(db, current_user, params.offset, params.page_size, unread_only)
    return Page(items=items, total=total, page=params.page, page_size=params.page_size)


@router.get("/unread-count")
def unread_count(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return {"unread": service.unread_count(db, current_user)}


@router.post("/read-all")
def read_all(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return {"updated": service.mark_all_read(db, current_user)}


@router.post("/send-overdue-reminders")
def send_overdue_reminders(db: Session = Depends(get_db), _: User = Depends(require_staff)):
    return {"created": service.send_overdue_reminders(db)}


@router.post("/{notification_id}/read", response_model=NotificationResponse)
def read_one(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return service.mark_read(db, current_user, notification_id)