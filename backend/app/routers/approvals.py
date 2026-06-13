from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import ApprovalStatus, ApprovalType
from app.schemas import (
    ApprovalCreate,
    ApprovalAction,
    ApprovalResponse,
    ApprovalDetailResponse,
    ApprovalListResponse,
)
from app import crud

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


@router.get("", response_model=ApprovalListResponse)
def list_approvals(
    status: ApprovalStatus | None = None,
    approval_type: ApprovalType | None = None,
    keyword: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    items, total = crud.get_approvals(db, status, approval_type, keyword, page, page_size)
    result = []
    for approval in items:
        asset = crud.get_asset(db, approval.asset_id)
        approval_data = ApprovalDetailResponse.model_validate(approval)
        approval_data.asset_name = asset.name
        approval_data.asset_tag = asset.asset_tag
        result.append(approval_data)
    return ApprovalListResponse(total=total, items=result)


@router.get("/{approval_id}", response_model=ApprovalDetailResponse)
def get_approval(approval_id: int, db: Session = Depends(get_db)):
    approval = crud.get_approval(db, approval_id)
    asset = crud.get_asset(db, approval.asset_id)
    result = ApprovalDetailResponse.model_validate(approval)
    result.asset_name = asset.name
    result.asset_tag = asset.asset_tag
    return result


@router.post("/{approval_id}/approve", response_model=ApprovalResponse)
def approve_approval(approval_id: int, data: ApprovalAction, db: Session = Depends(get_db)):
    return crud.approve_approval(db, approval_id, data)


@router.post("/{approval_id}/reject", response_model=ApprovalResponse)
def reject_approval(approval_id: int, data: ApprovalAction, db: Session = Depends(get_db)):
    return crud.reject_approval(db, approval_id, data)


@router.post("/asset/{asset_id}", response_model=ApprovalResponse)
def create_approval(asset_id: int, data: ApprovalCreate, db: Session = Depends(get_db)):
    return crud.create_approval(db, asset_id, data)
