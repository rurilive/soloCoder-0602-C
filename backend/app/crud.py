import qrcode
import io
import base64
from datetime import datetime
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.models import Asset, AssetLog, AssetStatus
from app.schemas import AssetCreate, AssetUpdate, AssetAllocate, AssetReturn, AssetScrap


def generate_asset_tag(db: Session) -> str:
    today = datetime.now().strftime("%Y%m%d")
    prefix = f"AST{today}"
    last = (
        db.query(Asset)
        .filter(Asset.asset_tag.like(f"{prefix}%"))
        .order_by(Asset.id.desc())
        .first()
    )
    seq = 1
    if last and last.asset_tag.startswith(prefix):
        try:
            seq = int(last.asset_tag[len(prefix):]) + 1
        except ValueError:
            seq = 1
    return f"{prefix}{seq:04d}"


def create_asset(db: Session, data: AssetCreate) -> Asset:
    existing = db.query(Asset).filter(Asset.serial_number == data.serial_number).first()
    if existing:
        raise HTTPException(status_code=400, detail="序列号已存在")
    asset_tag = generate_asset_tag(db)
    asset = Asset(asset_tag=asset_tag, status=AssetStatus.IN_STOCK, **data.model_dump())
    db.add(asset)
    log = AssetLog(
        asset_id=0,
        action="入库",
        operator="system",
        detail=f"新资产入库: {asset_tag}",
    )
    db.add(log)
    db.commit()
    db.refresh(asset)
    log.asset_id = asset.id
    db.commit()
    return asset


def get_assets(
    db: Session,
    status: AssetStatus | None = None,
    category: str | None = None,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Asset], int]:
    query = db.query(Asset)
    if status:
        query = query.filter(Asset.status == status)
    if category:
        query = query.filter(Asset.category == category)
    if keyword:
        like = f"%{keyword}%"
        query = query.filter(
            (Asset.name.like(like))
            | (Asset.asset_tag.like(like))
            | (Asset.brand.like(like))
            | (Asset.serial_number.like(like))
            | (Asset.assignee.like(like))
        )
    total = query.count()
    items = (
        query.order_by(Asset.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return items, total


def get_asset(db: Session, asset_id: int) -> Asset:
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="资产不存在")
    return asset


def get_asset_by_tag(db: Session, asset_tag: str) -> Asset:
    asset = db.query(Asset).filter(Asset.asset_tag == asset_tag).first()
    if not asset:
        raise HTTPException(status_code=404, detail="资产不存在")
    return asset


def update_asset(db: Session, asset_id: int, data: AssetUpdate) -> Asset:
    asset = get_asset(db, asset_id)
    update_data = data.model_dump(exclude_unset=True)
    if "serial_number" in update_data:
        existing = (
            db.query(Asset)
            .filter(Asset.serial_number == update_data["serial_number"], Asset.id != asset_id)
            .first()
        )
        if existing:
            raise HTTPException(status_code=400, detail="序列号已存在")
    for key, value in update_data.items():
        setattr(asset, key, value)
    db.commit()
    db.refresh(asset)
    return asset


def allocate_asset(db: Session, asset_id: int, data: AssetAllocate) -> Asset:
    asset = get_asset(db, asset_id)
    if asset.status != AssetStatus.IN_STOCK and asset.status != AssetStatus.RETURNED:
        raise HTTPException(status_code=400, detail=f"资产当前状态为 {asset.status.value}，无法领用")
    asset.status = AssetStatus.ALLOCATED
    asset.assignee = data.assignee
    log = AssetLog(
        asset_id=asset.id,
        action="领用",
        operator=data.assignee,
        detail=f"领用人: {data.assignee}",
    )
    db.add(log)
    db.commit()
    db.refresh(asset)
    return asset


def return_asset(db: Session, asset_id: int, data: AssetReturn) -> Asset:
    asset = get_asset(db, asset_id)
    if asset.status != AssetStatus.ALLOCATED:
        raise HTTPException(status_code=400, detail=f"资产当前状态为 {asset.status.value}，无法归还")
    assignee = asset.assignee
    asset.status = AssetStatus.RETURNED
    asset.assignee = None
    log = AssetLog(
        asset_id=asset.id,
        action="归还",
        operator=assignee or "unknown",
        detail=data.notes or "资产归还",
    )
    db.add(log)
    db.commit()
    db.refresh(asset)
    return asset


def scrap_asset(db: Session, asset_id: int, data: AssetScrap) -> Asset:
    asset = get_asset(db, asset_id)
    if asset.status == AssetStatus.SCRAPPED:
        raise HTTPException(status_code=400, detail="资产已报废")
    asset.status = AssetStatus.SCRAPPED
    asset.assignee = None
    log = AssetLog(
        asset_id=asset.id,
        action="报废",
        operator="admin",
        detail=data.notes or "资产报废",
    )
    db.add(log)
    db.commit()
    db.refresh(asset)
    return asset


def get_asset_logs(db: Session, asset_id: int) -> list[AssetLog]:
    return (
        db.query(AssetLog)
        .filter(AssetLog.asset_id == asset_id)
        .order_by(AssetLog.created_at.desc())
        .all()
    )


def generate_qr_code_base64(asset_tag: str, base_url: str) -> str:
    url = f"{base_url}/assets/tag/{asset_tag}"
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")
