from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_current_user, require_permissions
from app.models import User
from app.schemas import (
    OperationLogResponse,
    OperationLogListResponse,
    AssetLogResponse,
    ImportLogResponse,
)
from app import crud

router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.get("/operations", response_model=OperationLogListResponse)
def list_operation_logs(
    module: str | None = None,
    action: str | None = None,
    operator: str | None = None,
    target_type: str | None = None,
    status: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    keyword: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("log:view")),
):
    items, total = crud.get_operation_logs(
        db, module, action, operator, target_type, status,
        start_date, end_date, keyword, page, page_size
    )
    return OperationLogListResponse(total=total, items=items)


@router.get("/operations/{log_id}", response_model=OperationLogResponse)
def get_operation_log(
    log_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("log:view")),
):
    from app.models import OperationLog
    log = db.query(OperationLog).filter(OperationLog.id == log_id).first()
    if not log:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="操作日志不存在")
    return log


@router.get("/assets", response_model=list[AssetLogResponse])
def list_asset_logs(
    asset_id: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("log:view")),
):
    from app.models import AssetLog
    query = db.query(AssetLog)
    if asset_id:
        query = query.filter(AssetLog.asset_id == asset_id)
    total = query.count()
    items = (
        query.order_by(AssetLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return items


@router.get("/imports", response_model=list[ImportLogResponse])
def list_import_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("log:view")),
):
    from app.models import ImportLog
    total = db.query(ImportLog).count()
    items = (
        db.query(ImportLog)
        .order_by(ImportLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return items
