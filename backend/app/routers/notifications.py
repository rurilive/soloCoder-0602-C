from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth import get_current_user
from app.models import User
from app.schemas import (
    NotificationResponse,
    NotificationListResponse,
)
from app import crud

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("", response_model=NotificationListResponse)
def list_notifications(
    is_read: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items, total, unread_count = crud.get_user_notifications(
        db, current_user.id, is_read, page, page_size
    )
    return NotificationListResponse(total=total, items=items, unread_count=unread_count)


@router.get("/unread-count")
def get_unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _, _, unread_count = crud.get_user_notifications(db, current_user.id, is_read=False, page=1, page_size=1)
    return {"unread_count": unread_count}


@router.get("/{notification_id}", response_model=NotificationResponse)
def get_notification(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return crud.get_notification(db, notification_id, current_user.id)


@router.post("/{notification_id}/read", response_model=NotificationResponse)
def mark_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return crud.mark_notification_read(db, notification_id, current_user.id)


@router.post("/read-all")
def mark_all_notifications_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    count = crud.mark_all_notifications_read(db, current_user.id)
    return {"marked_count": count}
