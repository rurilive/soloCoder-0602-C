from fastapi import APIRouter, Depends, Query, UploadFile, File
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import AssetStatus
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
def create_asset(data: AssetCreate, db: Session = Depends(get_db)):
    return crud.create_asset(db, data)


@router.get("", response_model=AssetListResponse)
def list_assets(
    status: AssetStatus | None = None,
    category: str | None = None,
    keyword: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    items, total = crud.get_assets(db, status, category, keyword, page, page_size)
    return AssetListResponse(total=total, items=items)


@router.get("/tag/{asset_tag}", response_model=AssetResponse)
def get_asset_by_tag(asset_tag: str, db: Session = Depends(get_db)):
    return crud.get_asset_by_tag(db, asset_tag)


@router.post("/import", response_model=ImportResultResponse)
def import_assets(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="仅支持xlsx格式文件")
    file_bytes = file.file.read()
    result = crud.batch_import_assets(db, file_bytes, file.filename or "unknown.xlsx")
    return ImportResultResponse(**result)


@router.get("/{asset_id}", response_model=AssetResponse)
def get_asset(asset_id: int, db: Session = Depends(get_db)):
    return crud.get_asset(db, asset_id)


@router.put("/{asset_id}", response_model=AssetResponse)
def update_asset(asset_id: int, data: AssetUpdate, db: Session = Depends(get_db)):
    return crud.update_asset(db, asset_id, data)


@router.post("/{asset_id}/allocate", response_model=AssetResponse)
def allocate_asset(asset_id: int, data: AssetAllocate, db: Session = Depends(get_db)):
    return crud.allocate_asset(db, asset_id, data)


@router.post("/{asset_id}/return", response_model=AssetResponse)
def return_asset(asset_id: int, data: AssetReturn, db: Session = Depends(get_db)):
    return crud.return_asset(db, asset_id, data)


@router.post("/{asset_id}/scrap", response_model=AssetResponse)
def scrap_asset(asset_id: int, data: AssetScrap, db: Session = Depends(get_db)):
    return crud.scrap_asset(db, asset_id, data)


@router.get("/{asset_id}/logs", response_model=list[AssetLogResponse])
def get_asset_logs(asset_id: int, db: Session = Depends(get_db)):
    return crud.get_asset_logs(db, asset_id)


@router.get("/{asset_id}/qrcode")
def get_asset_qrcode(asset_id: int, db: Session = Depends(get_db)):
    asset = crud.get_asset(db, asset_id)
    base_url = "http://localhost:3332"
    qr_base64 = crud.generate_qr_code_base64(asset.asset_tag, base_url)
    return {"asset_tag": asset.asset_tag, "qr_code_base64": qr_base64}
