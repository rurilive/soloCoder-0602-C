from fastapi import APIRouter, Depends, Query, UploadFile, File, Request
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth import get_current_user, require_permissions, log_operation
from app.models import AssetStatus, User
from app.schemas import (
    AssetCreate,
    AssetUpdate,
    AssetAllocate,
    AssetReturn,
    AssetScrap,
    AssetResponse,
    AssetListResponse,
    AssetLogResponse,
    ImportResultResponse,
)
from app import crud

router = APIRouter(prefix="/api/assets", tags=["assets"])


@router.post("", response_model=AssetResponse, status_code=201)
def create_asset(
    request: Request,
    data: AssetCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("asset:create")),
):
    asset = crud.create_asset(db, data, current_user)
    log_operation(
        db,
        module="asset",
        action="create",
        user=current_user,
        target_type="asset",
        target_id=asset.id,
        detail=f"创建资产: {asset.asset_tag} - {asset.name}",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return asset


@router.get("", response_model=AssetListResponse)
def list_assets(
    status: AssetStatus | None = None,
    category: str | None = None,
    keyword: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("asset:view")),
):
    items, total = crud.get_assets(db, status, category, keyword, page, page_size, current_user)
    return AssetListResponse(total=total, items=items)


@router.get("/tag/{asset_tag}", response_model=AssetResponse)
def get_asset_by_tag(
    asset_tag: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("asset:view")),
):
    return crud.get_asset_by_tag(db, asset_tag, current_user)


@router.post("/import", response_model=ImportResultResponse)
def import_assets(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("asset:import")),
):
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="仅支持xlsx格式文件")
    file_bytes = file.file.read()
    result = crud.batch_import_assets(db, file_bytes, file.filename or "unknown.xlsx", current_user)
    log_operation(
        db,
        module="asset",
        action="import",
        user=current_user,
        target_type="asset",
        detail=f"批量导入资产: {file.filename}, 成功 {result['success_count']} 条",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        status="success" if result["success"] else "failed",
        error_message=None if result["success"] else f"导入失败，共 {len(result['errors'])} 个错误",
    )
    return ImportResultResponse(**result)


@router.get("/{asset_id}", response_model=AssetResponse)
def get_asset(
    asset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("asset:view")),
):
    return crud.get_asset(db, asset_id, current_user)


@router.put("/{asset_id}", response_model=AssetResponse)
def update_asset(
    request: Request,
    asset_id: int,
    data: AssetUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("asset:edit")),
):
    crud.get_asset(db, asset_id, current_user)
    asset = crud.update_asset(db, asset_id, data)
    log_operation(
        db,
        module="asset",
        action="update",
        user=current_user,
        target_type="asset",
        target_id=asset.id,
        detail=f"更新资产: {asset.asset_tag} - {asset.name}",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return asset


@router.post("/{asset_id}/allocate", response_model=AssetResponse)
def allocate_asset(
    request: Request,
    asset_id: int,
    data: AssetAllocate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("asset:allocate")),
):
    asset = crud.allocate_asset(db, asset_id, data, current_user)
    log_operation(
        db,
        module="asset",
        action="allocate",
        user=current_user,
        target_type="asset",
        target_id=asset_id,
        detail=f"申请领用资产, 领用人: {data.assignee}",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return asset


@router.post("/{asset_id}/return", response_model=AssetResponse)
def return_asset(
    request: Request,
    asset_id: int,
    data: AssetReturn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("asset:return")),
):
    crud.get_asset(db, asset_id, current_user)
    asset = crud.return_asset(db, asset_id, data, current_user)
    log_operation(
        db,
        module="asset",
        action="return",
        user=current_user,
        target_type="asset",
        target_id=asset.id,
        detail=f"归还资产: {asset.asset_tag} - {asset.name}",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return asset


@router.post("/{asset_id}/scrap", response_model=AssetResponse)
def scrap_asset(
    request: Request,
    asset_id: int,
    data: AssetScrap,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("asset:scrap")),
):
    crud.get_asset(db, asset_id, current_user)
    asset = crud.scrap_asset(db, asset_id, data, current_user)
    log_operation(
        db,
        module="asset",
        action="scrap",
        user=current_user,
        target_type="asset",
        target_id=asset_id,
        detail=f"申请报废资产",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return asset


@router.get("/{asset_id}/logs", response_model=list[AssetLogResponse])
def get_asset_logs(
    asset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("asset:view")),
):
    crud.get_asset(db, asset_id, current_user)
    return crud.get_asset_logs(db, asset_id)


@router.get("/{asset_id}/qrcode")
def get_asset_qrcode(
    asset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("asset:view")),
):
    asset = crud.get_asset(db, asset_id, current_user)
    base_url = "http://localhost:3332"
    qr_base64 = crud.generate_qr_code_base64(asset.asset_tag, base_url)
    return {"asset_tag": asset.asset_tag, "qr_code_base64": qr_base64}
