import qrcode
import io
import base64
import logging
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.models import (
    Asset, AssetLog, AssetStatus, AssetCategory, ImportLog,
    Approval, ApprovalType, ApprovalStatus,
    ApprovalChain, ApprovalChainNode, ApprovalNodeRecord,
    ApprovalProxy, OperationLog,
    User, Role, UserRole,
)

logger = logging.getLogger(__name__)
from app.schemas import (
    AssetCreate, AssetUpdate, AssetAllocate, AssetReturn, AssetScrap,
    ImportErrorItem, ApprovalCreate, ApprovalAction,
    ApprovalChainCreate, ApprovalChainUpdate, ChainNodesReorder,
    ApprovalProxyCreate,
)


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

BUILTIN_ROLE_HIERARCHY: dict[str, int] = {
    "super_admin": 100,
    "asset_admin": 90,
    "finance_manager": 80,
    "dept_manager": 70,
    "employee": 10,
}


def _role_is_truly_higher(current_role: str, next_role: str) -> bool:
    if current_role == next_role:
        return False
    current_rank = BUILTIN_ROLE_HIERARCHY.get(current_role)
    next_rank = BUILTIN_ROLE_HIERARCHY.get(next_role)
    if current_rank is None and next_rank is None:
        return False
    if current_rank is None:
        return True
    if next_rank is None:
        return False
    return next_rank > current_rank


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


def create_asset(db: Session, data: AssetCreate, operator: User | None = None) -> Asset:
    existing = db.query(Asset).filter(Asset.serial_number == data.serial_number).first()
    if existing:
        raise HTTPException(status_code=400, detail="序列号已存在")
    asset_tag = generate_asset_tag(db)

    asset_data = data.model_dump()
    if not asset_data.get("purchase_department") and operator and operator.department:
        asset_data["purchase_department"] = operator.department

    asset = Asset(asset_tag=asset_tag, status=AssetStatus.IN_STOCK, **asset_data)
    db.add(asset)

    op_name = operator.real_name or operator.username if operator else "system"
    op_id = operator.id if operator else None

    log = AssetLog(
        asset_id=0,
        action="入库",
        operator=op_name,
        operator_id=op_id,
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
    current_user: User | None = None,
) -> tuple[list[Asset], int]:
    from app.auth import apply_asset_data_scope

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

    if current_user:
        query = apply_asset_data_scope(query, db, current_user.id)

    total = query.count()
    items = (
        query.order_by(Asset.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return items, total


def get_asset(db: Session, asset_id: int, current_user: User | None = None) -> Asset:
    from app.auth import is_admin_user, get_user_display_name, is_dept_manager, get_dept_user_names

    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="资产不存在")

    if current_user and not is_admin_user(db, current_user.id):
        user_name = get_user_display_name(current_user)
        if is_dept_manager(db, current_user.id):
            dept_users = get_dept_user_names(db, current_user.department)
            if asset.assignee is not None:
                if asset.assignee not in dept_users:
                    raise HTTPException(status_code=403, detail="无权查看此资产")
            else:
                if asset.purchase_department != current_user.department:
                    raise HTTPException(status_code=403, detail="无权查看此资产")
        else:
            if asset.assignee != user_name:
                raise HTTPException(status_code=403, detail="无权查看此资产")

    return asset


def get_asset_by_tag(db: Session, asset_tag: str, current_user: User | None = None) -> Asset:
    from app.auth import is_admin_user, get_user_display_name, is_dept_manager, get_dept_user_names

    asset = db.query(Asset).filter(Asset.asset_tag == asset_tag).first()
    if not asset:
        raise HTTPException(status_code=404, detail="资产不存在")

    if current_user and not is_admin_user(db, current_user.id):
        user_name = get_user_display_name(current_user)
        if is_dept_manager(db, current_user.id):
            dept_users = get_dept_user_names(db, current_user.department)
            if asset.assignee is not None:
                if asset.assignee not in dept_users:
                    raise HTTPException(status_code=403, detail="无权查看此资产")
            else:
                if asset.purchase_department != current_user.department:
                    raise HTTPException(status_code=403, detail="无权查看此资产")
        else:
            if asset.assignee != user_name:
                raise HTTPException(status_code=403, detail="无权查看此资产")

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


def allocate_asset(db: Session, asset_id: int, data: AssetAllocate, applicant: User | None = None) -> Asset:
    applicant_name = applicant.real_name or applicant.username if applicant else data.assignee
    approval_data = ApprovalCreate(
        approval_type=ApprovalType.ALLOCATE,
        applicant=applicant_name,
        assignee=data.assignee,
        reason="资产领用申请",
    )
    create_approval(db, asset_id, approval_data, applicant)
    return get_asset(db, asset_id)


def return_asset(db: Session, asset_id: int, data: AssetReturn, operator: User | None = None) -> Asset:
    asset = get_asset(db, asset_id)
    if asset.status != AssetStatus.ALLOCATED:
        raise HTTPException(status_code=400, detail=f"资产当前状态为 {asset.status.value}，无法归还")
    assignee = asset.assignee
    asset.status = AssetStatus.RETURNED
    asset.assignee = None

    op_name = operator.real_name or operator.username if operator else (assignee or "unknown")
    op_id = operator.id if operator else None

    log = AssetLog(
        asset_id=asset.id,
        action="归还",
        operator=op_name,
        operator_id=op_id,
        detail=data.notes or "资产归还",
    )
    db.add(log)
    db.commit()
    db.refresh(asset)
    return asset


def scrap_asset(db: Session, asset_id: int, data: AssetScrap, applicant: User | None = None) -> Asset:
    applicant_name = applicant.real_name or applicant.username if applicant else "admin"
    approval_data = ApprovalCreate(
        approval_type=ApprovalType.SCRAP,
        applicant=applicant_name,
        reason=data.notes or "资产报废申请",
    )
    create_approval(db, asset_id, approval_data, applicant)
    return get_asset(db, asset_id)


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


def batch_import_assets(db: Session, file_bytes: bytes, file_name: str, operator: User | None = None) -> dict:
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
    operator_dept = operator.department if operator and operator.department else None
    for record in data_rows:
        category = CATEGORY_CN_MAP[record["category"]]
        asset_tag = generate_asset_tag(db)
        purchase_dept = record.get("purchase_department")
        if not purchase_dept:
            purchase_dept = operator_dept
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
            purchase_department=purchase_dept,
        )
        db.add(asset)
        created_assets.append(asset)

    op_name = operator.real_name or operator.username if operator else "admin"
    op_id = operator.id if operator else None

    import_log = ImportLog(
        total_rows=len(data_rows),
        success_count=len(data_rows),
        file_name=file_name,
        operator=op_name,
        operator_id=op_id,
        detail=f"批量导入{len(data_rows)}条资产",
    )
    db.add(import_log)

    db.flush()

    for asset in created_assets:
        log = AssetLog(
            asset_id=asset.id,
            action="批量入库",
            operator=op_name,
            operator_id=op_id,
            detail=f"批量导入入库: {asset.asset_tag}",
        )
        db.add(log)

    db.commit()

    for asset in created_assets:
        db.refresh(asset)

    return {
        "success": True,
        "total_rows": len(data_rows),
        "success_count": len(data_rows),
        "errors": [],
    }


def _find_matching_chain(db: Session, approval_type: ApprovalType, price: float | None) -> ApprovalChain | None:
    chains = (
        db.query(ApprovalChain)
        .filter(ApprovalChain.approval_type == approval_type)
        .order_by(ApprovalChain.is_default.asc())
        .all()
    )
    for chain in chains:
        if chain.min_price is not None and price is not None and price < chain.min_price:
            continue
        if chain.max_price is not None and price is not None and price > chain.max_price:
            continue
        return chain
    for chain in chains:
        if chain.is_default:
            return chain
    return chains[0] if chains else None


def _get_user_role_codes(db: Session, user_id: int) -> set[str]:
    urs = db.query(UserRole).filter(UserRole.user_id == user_id).all()
    role_ids = [ur.role_id for ur in urs]
    if not role_ids:
        return set()
    roles = db.query(Role).filter(Role.id.in_(role_ids)).all()
    return {r.code for r in roles}


def _user_is_approver_for_node(db: Session, user_id: int, node_record: ApprovalNodeRecord) -> bool:
    if user_id is None:
        return False
    user_role_codes = _get_user_role_codes(db, user_id)
    if "super_admin" in user_role_codes or "asset_admin" in user_role_codes:
        return True
    return node_record.approver_role in user_role_codes


def create_approval(db: Session, asset_id: int, data: ApprovalCreate, applicant: User | None = None) -> Approval:
    asset = get_asset(db, asset_id)

    if asset.status == AssetStatus.PENDING_APPROVAL:
        raise HTTPException(status_code=400, detail="资产已处于待审批状态，不可重复提交")

    pending_approval = (
        db.query(Approval)
        .filter(
            Approval.asset_id == asset_id,
            Approval.status == ApprovalStatus.PENDING,
        )
        .first()
    )
    if pending_approval:
        raise HTTPException(status_code=400, detail="该资产已有待处理的审批单，不可重复提交")

    if data.approval_type == ApprovalType.ALLOCATE:
        if asset.status != AssetStatus.IN_STOCK and asset.status != AssetStatus.RETURNED:
            raise HTTPException(status_code=400, detail=f"资产当前状态为 {asset.status.value}，无法申请领用")
        if not data.assignee:
            raise HTTPException(status_code=400, detail="领用审批必须指定领用人")
    elif data.approval_type == ApprovalType.SCRAP:
        if asset.status == AssetStatus.SCRAPPED:
            raise HTTPException(status_code=400, detail="资产已报废，不可重复申请")

    previous_status = asset.status
    asset.status = AssetStatus.PENDING_APPROVAL

    chain = _find_matching_chain(db, data.approval_type, asset.purchase_price)
    chain_id = None
    total_levels = 1

    if chain:
        chain_id = chain.id
        nodes = (
            db.query(ApprovalChainNode)
            .filter(ApprovalChainNode.chain_id == chain.id)
            .order_by(ApprovalChainNode.level.asc())
            .all()
        )
        total_levels = len(nodes) if nodes else 1

    approval = Approval(
        asset_id=asset_id,
        approval_type=data.approval_type,
        status=ApprovalStatus.PENDING,
        applicant=data.applicant,
        assignee=data.assignee,
        reason=data.reason,
        previous_status=previous_status,
        current_level=1,
        total_levels=total_levels,
        chain_id=chain_id,
    )
    db.add(approval)
    db.flush()

    if chain and chain_id:
        nodes = (
            db.query(ApprovalChainNode)
            .filter(ApprovalChainNode.chain_id == chain.id)
            .order_by(ApprovalChainNode.level.asc())
            .all()
        )
        now = datetime.now()
        for idx, node in enumerate(nodes):
            timeout_at = None
            if idx == 0 and node.timeout_minutes is not None:
                timeout_at = now + timedelta(minutes=node.timeout_minutes)
            record = ApprovalNodeRecord(
                approval_id=approval.id,
                chain_node_id=node.id,
                level=idx + 1,
                approver_role=node.approver_role,
                approver_name=node.approver_name,
                status=ApprovalStatus.PENDING,
                timeout_at=timeout_at,
            )
            db.add(record)

    action_type = "领用申请" if data.approval_type == ApprovalType.ALLOCATE else "报废申请"
    chain_info = f"（{total_levels}级审批链）" if total_levels > 1 else ""

    op_id = applicant.id if applicant else None
    log = AssetLog(
        asset_id=asset_id,
        action=action_type,
        operator=data.applicant,
        operator_id=op_id,
        detail=data.reason or f"提交{action_type}{chain_info}",
    )
    db.add(log)

    db.commit()
    db.refresh(approval)
    return approval


def get_approvals(
    db: Session,
    status: ApprovalStatus | None = None,
    approval_type: ApprovalType | None = None,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
    current_user: User | None = None,
) -> tuple[list[Approval], int]:
    from app.auth import apply_approval_data_scope

    query = db.query(Approval)
    if status:
        query = query.filter(Approval.status == status)
    if approval_type:
        query = query.filter(Approval.approval_type == approval_type)
    if keyword:
        like = f"%{keyword}%"
        asset_ids = db.query(Asset.id).filter(
            (Asset.name.like(like))
            | (Asset.asset_tag.like(like))
            | (Asset.serial_number.like(like))
        ).all()
        asset_id_list = [aid[0] for aid in asset_ids]
        if asset_id_list:
            query = query.filter(Approval.asset_id.in_(asset_id_list))
        else:
            return [], 0

    if current_user:
        query = apply_approval_data_scope(query, db, current_user.id)

    total = query.count()
    items = (
        query.order_by(Approval.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return items, total


def get_approval(db: Session, approval_id: int, current_user: User | None = None) -> Approval:
    from app.auth import is_admin_user, get_user_display_name, is_dept_manager, get_dept_user_names
    from app.models import ApprovalNodeRecord, ApprovalStatus

    approval = db.query(Approval).filter(Approval.id == approval_id).first()
    if not approval:
        raise HTTPException(status_code=404, detail="审批单不存在")

    if current_user and not is_admin_user(db, current_user.id):
        user_name = get_user_display_name(current_user)
        user_role_codes = set(_get_user_role_codes(db, current_user.id))

        is_applicant = approval.applicant == user_name

        is_pending_approver = False
        if approval.status == ApprovalStatus.PENDING:
            pending_nodes = (
                db.query(ApprovalNodeRecord)
                .filter(
                    ApprovalNodeRecord.approval_id == approval_id,
                    ApprovalNodeRecord.status == ApprovalStatus.PENDING,
                )
                .all()
            )
            for node in pending_nodes:
                if node.approver_role in user_role_codes:
                    is_pending_approver = True
                    break

        in_dept = False
        if is_dept_manager(db, current_user.id):
            dept_users = get_dept_user_names(db, current_user.department)
            if approval.applicant in dept_users:
                in_dept = True

        if not is_applicant and not is_pending_approver and not in_dept:
            raise HTTPException(status_code=403, detail="无权查看此审批单")

    return approval


def _check_circular_proxy(db: Session, principal_user_id: int, proxy_user_id: int, approval_applicant: str) -> bool:
    proxy_user = db.query(User).filter(User.id == proxy_user_id).first()
    if not proxy_user:
        return False
    proxy_display_name = proxy_user.real_name or proxy_user.username
    if proxy_display_name == approval_applicant or proxy_user.username == approval_applicant:
        return True
    return False


def _set_next_level_timeout(db: Session, approval: Approval, context: str = "unknown") -> None:
    next_record = (
        db.query(ApprovalNodeRecord)
        .filter(
            ApprovalNodeRecord.approval_id == approval.id,
            ApprovalNodeRecord.level == approval.current_level,
        )
        .first()
    )
    if not next_record:
        logger.warning(
            "[%s] 审批单#%d 下一级节点(level=%d)不存在，无法设置超时",
            context, approval.id, approval.current_level,
        )
        return
    chain_node = (
        db.query(ApprovalChainNode)
        .filter(ApprovalChainNode.id == next_record.chain_node_id)
        .first()
    )
    if not chain_node or chain_node.timeout_minutes is None:
        return
    new_timeout = datetime.now() + timedelta(minutes=chain_node.timeout_minutes)
    if next_record.timeout_at is not None:
        logger.warning(
            "[%s] 审批单#%d 节点(level=%d, role=%s) timeout_at 已存在，"
            "重新以当前时间计算覆盖: 原值=%s, 新值=%s",
            context, approval.id, next_record.level,
            next_record.approver_role, next_record.timeout_at, new_timeout,
        )
    next_record.timeout_at = new_timeout


def approve_approval(db: Session, approval_id: int, data: ApprovalAction, approver: User | None = None) -> Approval:
    approval = get_approval(db, approval_id)
    if approval.status != ApprovalStatus.PENDING:
        raise HTTPException(status_code=400, detail="审批单已处理，不可重复操作")

    asset = get_asset(db, approval.asset_id)
    if asset.status != AssetStatus.PENDING_APPROVAL:
        raise HTTPException(status_code=400, detail="资产状态异常，不是待审批状态")

    approver_name = approver.real_name or approver.username if approver else "admin"
    approver_id = approver.id if approver else None

    now = datetime.now()

    current_record = (
        db.query(ApprovalNodeRecord)
        .filter(
            ApprovalNodeRecord.approval_id == approval_id,
            ApprovalNodeRecord.level == approval.current_level,
        )
        .first()
    )

    if current_record:
        if current_record.status != ApprovalStatus.PENDING:
            raise HTTPException(status_code=400, detail="当前节点已处理，不可重复操作")

        is_direct_approver = approver and _user_is_approver_for_node(db, approver.id, current_record)

        is_proxy_approver = False
        proxy_principal_name = None

        if approver and not is_direct_approver:
            active_proxies = (
                db.query(ApprovalProxy)
                .filter(
                    ApprovalProxy.proxy_user_id == approver.id,
                    ApprovalProxy.is_active == True,
                    ApprovalProxy.start_time <= now,
                    ApprovalProxy.end_time >= now,
                )
                .all()
            )
            for ap in active_proxies:
                principal = db.query(User).filter(User.id == ap.principal_user_id).first()
                if principal:
                    principal_role_codes = _get_user_role_codes(db, principal.id)
                    if current_record.approver_role in principal_role_codes:
                        if _check_circular_proxy(db, principal.id, approver.id, approval.applicant):
                            raise HTTPException(status_code=400, detail="循环代理检测：代理人同时也是申请人，无法代理审批")
                        is_proxy_approver = True
                        proxy_principal_name = principal.real_name or principal.username
                        break

        if approver and not is_direct_approver and not is_proxy_approver:
            raise HTTPException(
                status_code=403,
                detail=f"您没有权限审批此节点，当前节点需要角色: {current_record.approver_role}",
            )

        current_record.status = ApprovalStatus.APPROVED
        current_record.opinion = data.opinion
        current_record.acted_at = now

        if is_proxy_approver and approver:
            current_record.actual_approver = approver_name
            current_record.proxy_source = proxy_principal_name

        all_records = (
            db.query(ApprovalNodeRecord)
            .filter(ApprovalNodeRecord.approval_id == approval_id)
            .order_by(ApprovalNodeRecord.level.asc())
            .all()
        )
        next_level = approval.current_level + 1

        if next_level <= approval.total_levels:
            approval.current_level = next_level
            _set_next_level_timeout(db, approval, "approve_approval")

            level_desc = f"第{approval.current_level - 1}/{approval.total_levels}级审批通过"
            proxy_info = f"（代理审批，代理人: {approver_name}，代原审批人: {current_record.proxy_source}）" if current_record.proxy_source else ""
            log = AssetLog(
                asset_id=asset.id,
                action="多级审批通过",
                operator=approver_name,
                operator_id=approver_id,
                detail=f"{level_desc}，审批人: {current_record.approver_name}{proxy_info}。{data.opinion or ''}",
            )
            db.add(log)
            db.commit()
            db.refresh(approval)
            return approval

    approval.status = ApprovalStatus.APPROVED
    approval.approver = approver_name
    approval.approval_opinion = data.opinion

    if approval.approval_type == ApprovalType.ALLOCATE:
        asset.status = AssetStatus.ALLOCATED
        asset.assignee = approval.assignee
        action = "领用审批通过"
        detail = f"审批通过，领用人: {approval.assignee}。{data.opinion or ''}"
    elif approval.approval_type == ApprovalType.SCRAP:
        asset.status = AssetStatus.SCRAPPED
        asset.assignee = None
        action = "报废审批通过"
        detail = f"审批通过。{data.opinion or ''}"

    log = AssetLog(
        asset_id=asset.id,
        action=action,
        operator=approver_name,
        operator_id=approver_id,
        detail=detail,
    )
    db.add(log)

    db.commit()
    db.refresh(approval)
    return approval


def reject_approval(db: Session, approval_id: int, data: ApprovalAction, approver: User | None = None) -> Approval:
    approval = get_approval(db, approval_id)
    if approval.status != ApprovalStatus.PENDING:
        raise HTTPException(status_code=400, detail="审批单已处理，不可重复操作")

    asset = get_asset(db, approval.asset_id)
    if asset.status != AssetStatus.PENDING_APPROVAL:
        raise HTTPException(status_code=400, detail="资产状态异常，不是待审批状态")

    approver_name = approver.real_name or approver.username if approver else "admin"
    approver_id = approver.id if approver else None

    now = datetime.now()

    current_record = (
        db.query(ApprovalNodeRecord)
        .filter(
            ApprovalNodeRecord.approval_id == approval_id,
            ApprovalNodeRecord.level == approval.current_level,
        )
        .first()
    )

    if current_record:
        if current_record.status != ApprovalStatus.PENDING:
            raise HTTPException(status_code=400, detail="当前节点已处理，不可重复操作")

        is_direct_approver = approver and _user_is_approver_for_node(db, approver.id, current_record)

        is_proxy_approver = False
        if approver and not is_direct_approver:
            active_proxies = (
                db.query(ApprovalProxy)
                .filter(
                    ApprovalProxy.proxy_user_id == approver.id,
                    ApprovalProxy.is_active == True,
                    ApprovalProxy.start_time <= now,
                    ApprovalProxy.end_time >= now,
                )
                .all()
            )
            for ap in active_proxies:
                principal = db.query(User).filter(User.id == ap.principal_user_id).first()
                if principal:
                    principal_role_codes = _get_user_role_codes(db, principal.id)
                    if current_record.approver_role in principal_role_codes:
                        if _check_circular_proxy(db, principal.id, approver.id, approval.applicant):
                            raise HTTPException(status_code=400, detail="循环代理检测：代理人同时也是申请人，无法代理审批")
                        is_proxy_approver = True
                        current_record.actual_approver = approver_name
                        current_record.proxy_source = principal.real_name or principal.username
                        break

        if approver and not is_direct_approver and not is_proxy_approver:
            raise HTTPException(
                status_code=403,
                detail=f"您没有权限审批此节点，当前节点需要角色: {current_record.approver_role}",
            )

        current_record.status = ApprovalStatus.REJECTED
        current_record.opinion = data.opinion
        current_record.acted_at = now

        remaining_records = (
            db.query(ApprovalNodeRecord)
            .filter(
                ApprovalNodeRecord.approval_id == approval_id,
                ApprovalNodeRecord.level > approval.current_level,
            )
            .all()
        )
        for r in remaining_records:
            r.status = ApprovalStatus.REJECTED

    approval.status = ApprovalStatus.REJECTED
    approval.approver = approver_name
    approval.approval_opinion = data.opinion

    asset.status = approval.previous_status

    action_type = "领用" if approval.approval_type == ApprovalType.ALLOCATE else "报废"
    level_info = f"（第{approval.current_level}/{approval.total_levels}级驳回）" if approval.total_levels > 1 else ""
    proxy_info = ""
    if current_record and current_record.proxy_source:
        proxy_info = f"（代理审批，代理人: {current_record.actual_approver}，代原审批人: {current_record.proxy_source}）"
    action = f"{action_type}审批驳回"
    detail = f"审批驳回{level_info}{proxy_info}。{data.opinion or ''}"

    log = AssetLog(
        asset_id=asset.id,
        action=action,
        operator=approver_name,
        operator_id=approver_id,
        detail=detail,
    )
    db.add(log)

    db.commit()
    db.refresh(approval)
    return approval


def get_my_pending_approvals(
    db: Session,
    current_user: User,
    status: ApprovalStatus | None = None,
    approval_type: ApprovalType | None = None,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Approval], int]:
    user_role_codes = _get_user_role_codes(db, current_user.id)

    query = db.query(Approval)

    if status:
        query = query.filter(Approval.status == status)
    if approval_type:
        query = query.filter(Approval.approval_type == approval_type)

    if "super_admin" not in user_role_codes and "asset_admin" not in user_role_codes:
        pending_node_subquery = (
            db.query(ApprovalNodeRecord.approval_id)
            .filter(
                ApprovalNodeRecord.status == ApprovalStatus.PENDING,
                ApprovalNodeRecord.approver_role.in_(list(user_role_codes)) if user_role_codes else ApprovalNodeRecord.approver_role == "__none__",
            )
            .distinct()
            .subquery()
        )

        now = datetime.now()
        active_proxy_principal_ids = [
            ap.principal_user_id
            for ap in db.query(ApprovalProxy)
            .filter(
                ApprovalProxy.proxy_user_id == current_user.id,
                ApprovalProxy.is_active == True,
                ApprovalProxy.start_time <= now,
                ApprovalProxy.end_time >= now,
            )
            .all()
        ]

        proxy_approval_ids = set()
        for pid in active_proxy_principal_ids:
            principal = db.query(User).filter(User.id == pid).first()
            if principal:
                principal_role_codes = _get_user_role_codes(db, principal.id)
                if principal_role_codes:
                    proxy_ids = (
                        db.query(ApprovalNodeRecord.approval_id)
                        .filter(
                            ApprovalNodeRecord.status == ApprovalStatus.PENDING,
                            ApprovalNodeRecord.approver_role.in_(list(principal_role_codes)),
                        )
                        .distinct()
                        .subquery()
                    )
                    for aid in db.query(Approval.id).filter(Approval.id.in_(proxy_ids)).all():
                        approval_obj = db.query(Approval).filter(Approval.id == aid[0]).first()
                        if approval_obj and approval_obj.applicant != (current_user.real_name or current_user.username) and approval_obj.applicant != current_user.username:
                            proxy_approval_ids.add(aid[0])

        from sqlalchemy import or_
        if proxy_approval_ids:
            query = query.filter(
                or_(
                    Approval.id.in_(pending_node_subquery),
                    Approval.id.in_(list(proxy_approval_ids)),
                )
            )
        else:
            query = query.filter(Approval.id.in_(pending_node_subquery))

    if keyword:
        like = f"%{keyword}%"
        asset_ids = db.query(Asset.id).filter(
            (Asset.name.like(like))
            | (Asset.asset_tag.like(like))
            | (Asset.serial_number.like(like))
        ).all()
        asset_id_list = [aid[0] for aid in asset_ids]
        if asset_id_list:
            query = query.filter(Approval.asset_id.in_(asset_id_list))
        else:
            return [], 0

    total = query.count()
    items = (
        query.order_by(Approval.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return items, total


def get_my_submitted_approvals(
    db: Session,
    current_user: User,
    status: ApprovalStatus | None = None,
    approval_type: ApprovalType | None = None,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Approval], int]:
    user_name = current_user.real_name or current_user.username

    query = db.query(Approval).filter(Approval.applicant == user_name)

    if status:
        query = query.filter(Approval.status == status)
    if approval_type:
        query = query.filter(Approval.approval_type == approval_type)

    if keyword:
        like = f"%{keyword}%"
        asset_ids = db.query(Asset.id).filter(
            (Asset.name.like(like))
            | (Asset.asset_tag.like(like))
            | (Asset.serial_number.like(like))
        ).all()
        asset_id_list = [aid[0] for aid in asset_ids]
        if asset_id_list:
            query = query.filter(Approval.asset_id.in_(asset_id_list))
        else:
            return [], 0

    total = query.count()
    items = (
        query.order_by(Approval.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return items, total


def get_approval_node_records(db: Session, approval_id: int) -> list[ApprovalNodeRecord]:
    return (
        db.query(ApprovalNodeRecord)
        .filter(ApprovalNodeRecord.approval_id == approval_id)
        .order_by(ApprovalNodeRecord.level.asc())
        .all()
    )


def create_approval_chain(db: Session, data: ApprovalChainCreate) -> ApprovalChain:
    chain = ApprovalChain(
        name=data.name,
        approval_type=data.approval_type,
        min_price=data.min_price,
        max_price=data.max_price,
        is_default=data.is_default,
    )
    db.add(chain)
    db.flush()

    for idx, node_data in enumerate(data.nodes):
        node = ApprovalChainNode(
            chain_id=chain.id,
            level=idx + 1,
            approver_role=node_data.approver_role,
            approver_name=node_data.approver_name,
            timeout_minutes=node_data.timeout_minutes,
        )
        db.add(node)

    db.commit()
    db.refresh(chain)
    return chain


def get_approval_chains(
    db: Session,
    approval_type: ApprovalType | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[ApprovalChain], int]:
    query = db.query(ApprovalChain)
    if approval_type:
        query = query.filter(ApprovalChain.approval_type == approval_type)
    total = query.count()
    items = (
        query.order_by(ApprovalChain.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return items, total


def get_approval_chain(db: Session, chain_id: int) -> ApprovalChain:
    chain = db.query(ApprovalChain).filter(ApprovalChain.id == chain_id).first()
    if not chain:
        raise HTTPException(status_code=404, detail="审批链不存在")
    return chain


def get_chain_nodes(db: Session, chain_id: int) -> list[ApprovalChainNode]:
    return (
        db.query(ApprovalChainNode)
        .filter(ApprovalChainNode.chain_id == chain_id)
        .order_by(ApprovalChainNode.level.asc())
        .all()
    )


def update_approval_chain(db: Session, chain_id: int, data: ApprovalChainUpdate) -> ApprovalChain:
    chain = get_approval_chain(db, chain_id)

    if data.name is not None:
        chain.name = data.name
    if data.min_price is not None:
        chain.min_price = data.min_price
    if data.max_price is not None:
        chain.max_price = data.max_price
    if data.is_default is not None:
        chain.is_default = data.is_default

    if data.nodes is not None:
        db.query(ApprovalChainNode).filter(ApprovalChainNode.chain_id == chain_id).delete()
        for idx, node_data in enumerate(data.nodes):
            node = ApprovalChainNode(
                chain_id=chain_id,
                level=idx + 1,
                approver_role=node_data.approver_role,
                approver_name=node_data.approver_name,
                timeout_minutes=node_data.timeout_minutes,
            )
            db.add(node)

    db.commit()
    db.refresh(chain)
    return chain


def delete_approval_chain(db: Session, chain_id: int) -> None:
    chain = get_approval_chain(db, chain_id)
    pending_approvals = (
        db.query(Approval)
        .filter(Approval.chain_id == chain_id, Approval.status == ApprovalStatus.PENDING)
        .count()
    )
    if pending_approvals > 0:
        raise HTTPException(status_code=400, detail="该审批链下有待处理的审批单，不可删除")
    db.query(ApprovalChainNode).filter(ApprovalChainNode.chain_id == chain_id).delete()
    db.delete(chain)
    db.commit()


def reorder_chain_nodes(db: Session, chain_id: int, data: ChainNodesReorder) -> ApprovalChain:
    chain = get_approval_chain(db, chain_id)

    existing_nodes = get_chain_nodes(db, chain_id)
    existing_ids = {n.id for n in existing_nodes}

    if set(data.node_ids) != existing_ids:
        raise HTTPException(status_code=400, detail="节点ID与当前审批链节点不匹配")

    for new_level, node_id in enumerate(data.node_ids, start=1):
        node = next((n for n in existing_nodes if n.id == node_id), None)
        if node:
            node.level = new_level

    db.commit()
    db.refresh(chain)
    return chain


def create_operation_log(
    db: Session,
    module: str,
    action: str,
    operator: str,
    operator_id: int | None = None,
    target_type: str | None = None,
    target_id: int | None = None,
    detail: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    status: str = "success",
    error_message: str | None = None,
) -> OperationLog:
    from app.models import OperationLog

    log = OperationLog(
        module=module,
        action=action,
        operator=operator,
        operator_id=operator_id,
        target_type=target_type,
        target_id=target_id,
        detail=detail,
        ip_address=ip_address,
        user_agent=user_agent,
        status=status,
        error_message=error_message,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def get_operation_logs(
    db: Session,
    module: str | None = None,
    action: str | None = None,
    operator: str | None = None,
    target_type: str | None = None,
    status: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[OperationLog], int]:
    from app.models import OperationLog
    from datetime import datetime

    query = db.query(OperationLog)

    if module:
        query = query.filter(OperationLog.module == module)
    if action:
        query = query.filter(OperationLog.action == action)
    if operator:
        query = query.filter(OperationLog.operator.like(f"%{operator}%"))
    if target_type:
        query = query.filter(OperationLog.target_type == target_type)
    if status:
        query = query.filter(OperationLog.status == status)
    if start_date:
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            query = query.filter(OperationLog.created_at >= start_dt)
        except ValueError:
            pass
    if end_date:
        try:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            from datetime import timedelta
            end_dt = end_dt + timedelta(days=1)
            query = query.filter(OperationLog.created_at < end_dt)
        except ValueError:
            pass
    if keyword:
        like = f"%{keyword}%"
        query = query.filter(
            (OperationLog.detail.like(like))
            | (OperationLog.operator.like(like))
            | (OperationLog.action.like(like))
        )

    total = query.count()
    items = (
        query.order_by(OperationLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return items, total


def check_and_process_timeouts(db: Session) -> list[dict]:
    now = datetime.now()
    timed_out_records = (
        db.query(ApprovalNodeRecord)
        .filter(
            ApprovalNodeRecord.status == ApprovalStatus.PENDING,
            ApprovalNodeRecord.timeout_at.isnot(None),
            ApprovalNodeRecord.timeout_at < now,
        )
        .all()
    )

    processed = []
    for record in timed_out_records:
        approval = db.query(Approval).filter(Approval.id == record.approval_id).first()
        if not approval or approval.status != ApprovalStatus.PENDING:
            continue

        asset = db.query(Asset).filter(Asset.id == approval.asset_id).first()
        if not asset:
            continue

        record.status = ApprovalStatus.ESCALATED
        record.is_escalated = True
        record.acted_at = now
        record.opinion = "审批超时，自动升级"

        should_reject = False
        reason_for_reject = ""

        if record.level < approval.total_levels:
            next_record = (
                db.query(ApprovalNodeRecord)
                .filter(
                    ApprovalNodeRecord.approval_id == approval.id,
                    ApprovalNodeRecord.level == record.level + 1,
                )
                .first()
            )
            if next_record and not _role_is_truly_higher(record.approver_role, next_record.approver_role):
                should_reject = True
                reason_for_reject = f"下一级角色（{next_record.approver_role}）权限不高于当前级（{record.approver_role}），避免升级死循环，自动驳回"

        if not should_reject and record.level < approval.total_levels:
            approval.current_level = record.level + 1
            _set_next_level_timeout(db, approval, "check_and_process_timeouts")

            log = AssetLog(
                asset_id=asset.id,
                action="审批超时升级",
                operator="系统",
                operator_id=None,
                detail=f"第{record.level}/{approval.total_levels}级审批超时，自动升级到第{record.level + 1}级",
            )
            db.add(log)

            op_log = OperationLog(
                module="approval",
                action="timeout_escalate",
                operator="系统",
                detail=f"审批单#{approval.id}第{record.level}级超时，升级到第{record.level + 1}级",
            )
            db.add(op_log)

            processed.append({
                "approval_id": approval.id,
                "level": record.level,
                "action": "escalated",
                "new_level": record.level + 1,
            })
        else:
            if should_reject:
                final_reason = reason_for_reject
            else:
                final_reason = "最高级审批超时，自动驳回"
            approval.status = ApprovalStatus.REJECTED
            approval.approver = "系统"
            approval.approval_opinion = final_reason

            asset.status = approval.previous_status

            remaining_records = (
                db.query(ApprovalNodeRecord)
                .filter(
                    ApprovalNodeRecord.approval_id == approval.id,
                    ApprovalNodeRecord.level > record.level,
                    ApprovalNodeRecord.status == ApprovalStatus.PENDING,
                )
                .all()
            )
            for r in remaining_records:
                r.status = ApprovalStatus.REJECTED

            log_detail = (
                f"（第{record.level}/{approval.total_levels}级）{final_reason}，资产状态恢复为{approval.previous_status.value}"
            )
            log = AssetLog(
                asset_id=asset.id,
                action="审批超时驳回",
                operator="系统",
                operator_id=None,
                detail=log_detail,
            )
            db.add(log)

            op_log = OperationLog(
                module="approval",
                action="timeout_reject",
                operator="系统",
                detail=f"审批单#{approval.id}{final_reason}",
            )
            db.add(op_log)

            processed.append({
                "approval_id": approval.id,
                "level": record.level,
                "action": "rejected",
                "reason": final_reason,
            })

    if processed:
        db.commit()

    return processed


def expire_outdated_proxies(db: Session) -> int:
    now = datetime.now()
    expired = (
        db.query(ApprovalProxy)
        .filter(
            ApprovalProxy.is_active == True,
            ApprovalProxy.end_time < now,
        )
        .all()
    )
    count = len(expired)
    for proxy in expired:
        proxy.is_active = False
    if count > 0:
        db.commit()
    return count


def create_approval_proxy(db: Session, data: ApprovalProxyCreate, current_user: User) -> ApprovalProxy:
    if data.proxy_user_id == current_user.id:
        raise HTTPException(status_code=400, detail="不能将自己设置为代理人")

    if data.start_time >= data.end_time:
        raise HTTPException(status_code=400, detail="开始时间必须早于结束时间")

    if data.end_time <= datetime.now():
        raise HTTPException(status_code=400, detail="结束时间必须晚于当前时间")

    proxy_user = db.query(User).filter(User.id == data.proxy_user_id).first()
    if not proxy_user:
        raise HTTPException(status_code=404, detail="代理人用户不存在")
    if not proxy_user.is_active:
        raise HTTPException(status_code=400, detail="代理人用户已被禁用")

    existing = (
        db.query(ApprovalProxy)
        .filter(
            ApprovalProxy.principal_user_id == current_user.id,
            ApprovalProxy.is_active == True,
            ApprovalProxy.end_time > datetime.now(),
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="您已有生效中的代理设置，请先取消后再设置新代理")

    existing_proxy_as_principal = (
        db.query(ApprovalProxy)
        .filter(
            ApprovalProxy.principal_user_id == data.proxy_user_id,
            ApprovalProxy.proxy_user_id == current_user.id,
            ApprovalProxy.is_active == True,
            ApprovalProxy.end_time > datetime.now(),
        )
        .first()
    )
    if existing_proxy_as_principal:
        raise HTTPException(status_code=400, detail="检测到循环代理：对方已将您设为代理人，不能再将其设为您的代理人")

    proxy = ApprovalProxy(
        principal_user_id=current_user.id,
        proxy_user_id=data.proxy_user_id,
        start_time=data.start_time,
        end_time=data.end_time,
        reason=data.reason,
        is_active=True,
    )
    db.add(proxy)
    db.commit()
    db.refresh(proxy)
    return proxy


def get_approval_proxies(
    db: Session,
    current_user: User | None = None,
    is_active: bool | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[ApprovalProxy], int]:
    query = db.query(ApprovalProxy)

    if current_user:
        query = query.filter(
            (ApprovalProxy.principal_user_id == current_user.id)
            | (ApprovalProxy.proxy_user_id == current_user.id)
        )

    if is_active is not None:
        query = query.filter(ApprovalProxy.is_active == is_active)

    total = query.count()
    items = (
        query.order_by(ApprovalProxy.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return items, total


def cancel_approval_proxy(db: Session, proxy_id: int, current_user: User) -> ApprovalProxy:
    proxy = db.query(ApprovalProxy).filter(ApprovalProxy.id == proxy_id).first()
    if not proxy:
        raise HTTPException(status_code=404, detail="代理设置不存在")

    if proxy.principal_user_id != current_user.id:
        from app.auth import is_admin_user
        if not is_admin_user(db, current_user.id):
            raise HTTPException(status_code=403, detail="只有代理设置人或管理员可以取消代理")

    proxy.is_active = False
    db.commit()
    db.refresh(proxy)
    return proxy
