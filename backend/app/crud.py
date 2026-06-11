import qrcode
import io
import base64
from datetime import datetime
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.models import Asset, AssetLog, AssetStatus, AssetCategory, ImportLog
from app.schemas import AssetCreate, AssetUpdate, AssetAllocate, AssetReturn, AssetScrap, ImportErrorItem


CATEGORY_CN_MAP: dict[str, AssetCategory] = {
    "电脑": AssetCategory.COMPUTER,
    "计算机": AssetCategory.COMPUTER,
    "显示器": AssetCategory.MONITOR,
    "打印机": AssetCategory.PRINTER,
    "网络设备": AssetCategory.NETWORK_DEVICE,
    "外设": AssetCategory.PERIPHERAL,
    "外围设备": AssetCategory.PERIPHERAL,
    "其他": AssetCategory.OTHER,
    "computer": AssetCategory.COMPUTER,
    "monitor": AssetCategory.MONITOR,
    "printer": AssetCategory.PRINTER,
    "network_device": AssetCategory.NETWORK_DEVICE,
    "peripheral": AssetCategory.PERIPHERAL,
    "other": AssetCategory.OTHER,
}

REQUIRED_FIELDS = ["name", "category", "brand", "model", "serial_number"]

HEADER_MAP = {
    "名称": "name",
    "名称/name": "name",
    "类别": "category",
    "类别/category": "category",
    "品牌": "brand",
    "品牌/brand": "brand",
    "型号": "model",
    "型号/model": "model",
    "序列号": "serial_number",
    "序列号/serial_number": "serial_number",
    "使用人": "assignee",
    "使用人/assignee": "assignee",
    "位置": "location",
    "位置/location": "location",
    "备注": "notes",
    "备注/notes": "notes",
    "购买日期": "purchase_date",
    "购买日期/purchase_date": "purchase_date",
    "购买价格": "purchase_price",
    "购买价格/purchase_price": "purchase_price",
}


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


def batch_import_assets(db: Session, file_bytes: bytes, file_name: str) -> dict:
    import openpyxl

    try:
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    except Exception:
        raise HTTPException(status_code=400, detail="无法解析Excel文件，请确认文件格式为xlsx")

    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()

    if len(rows) < 2:
        raise HTTPException(status_code=400, detail="Excel文件至少需要包含表头和一行数据")

    raw_headers = [str(h).strip() if h else "" for h in rows[0]]
    col_map: dict[int, str] = {}
    for idx, h in enumerate(raw_headers):
        field = HEADER_MAP.get(h)
        if field:
            col_map[idx] = field

    data_rows: list[dict] = []
    for row in rows[1:]:
        record: dict = {}
        for col_idx, field_name in col_map.items():
            val = row[col_idx] if col_idx < len(row) else None
            if val is not None:
                val = str(val).strip()
                if val == "":
                    val = None
            record[field_name] = val
        data_rows.append(record)

    errors: list[ImportErrorItem] = []
    serial_numbers_in_file: dict[str, int] = {}

    for i, record in enumerate(data_rows):
        row_num = i + 2
        for field in REQUIRED_FIELDS:
            if not record.get(field):
                errors.append(ImportErrorItem(row=row_num, reason=f"必填字段'{field}'缺失"))
                break

        sn = record.get("serial_number", "")
        if sn:
            if sn in serial_numbers_in_file:
                errors.append(ImportErrorItem(row=row_num, reason=f"序列号'{sn}'在文件内重复（首次出现在第{serial_numbers_in_file[sn]}行）"))
            else:
                serial_numbers_in_file[sn] = row_num

        cat_raw = record.get("category", "")
        if cat_raw and cat_raw not in CATEGORY_CN_MAP:
            errors.append(ImportErrorItem(row=row_num, reason=f"类别'{cat_raw}'无法转换为有效枚举值"))

    if errors:
        return {
            "success": False,
            "total_rows": len(data_rows),
            "success_count": 0,
            "errors": errors,
        }

    for sn in serial_numbers_in_file:
        existing = db.query(Asset).filter(Asset.serial_number == sn).first()
        if existing:
            row_num = serial_numbers_in_file[sn]
            errors.append(ImportErrorItem(row=row_num, reason=f"序列号'{sn}'在数据库中已存在"))

    if errors:
        return {
            "success": False,
            "total_rows": len(data_rows),
            "success_count": 0,
            "errors": errors,
        }

    created_assets: list[Asset] = []
    for record in data_rows:
        category = CATEGORY_CN_MAP[record["category"]]
        asset_tag = generate_asset_tag(db)
        asset = Asset(
            asset_tag=asset_tag,
            name=record["name"],
            category=category,
            brand=record["brand"],
            model=record["model"],
            serial_number=record["serial_number"],
            status=AssetStatus.IN_STOCK,
            assignee=record.get("assignee"),
            location=record.get("location"),
            notes=record.get("notes"),
            purchase_date=record.get("purchase_date"),
            purchase_price=float(record["purchase_price"]) if record.get("purchase_price") else None,
        )
        db.add(asset)
        created_assets.append(asset)

    import_log = ImportLog(
        total_rows=len(data_rows),
        success_count=len(data_rows),
        file_name=file_name,
        operator="admin",
        detail=f"批量导入{len(data_rows)}条资产",
    )
    db.add(import_log)

    db.commit()

    for asset in created_assets:
        log = AssetLog(
            asset_id=asset.id,
            action="批量入库",
            operator="admin",
            detail=f"批量导入入库: {asset.asset_tag}",
        )
        db.add(log)

    db.commit()

    return {
        "success": True,
        "total_rows": len(data_rows),
        "success_count": len(data_rows),
        "errors": [],
    }
