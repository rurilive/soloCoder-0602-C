import qrcode
import io
import base64
import logging
from datetime import datetime, timedelta
from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException
from app.models import (
    Asset, AssetLog, AssetStatus, AssetCategory, ImportLog,
    Approval, ApprovalType, ApprovalStatus, ApprovalMode,
    ApprovalChain, ApprovalChainNode, ApprovalChainNodeApprover, ApprovalNodeRecord,
    ApprovalChainCondition, ApprovalChainConditionRule,
    ApprovalProxy, ApprovalReminder, ApprovalNodeAction,
    ApprovalNodeActionType, ApprovalRecordType, TransferStatus,
    TimeoutEscalationStrategy, ChainNodeType,
    OperationLog, TaskLock,
    User, Role, UserRole,
    Notification, NotificationType,
)
from app.condition_engine import (
    ConditionEvaluationContext,
    resolve_next_level,
    detect_cycle,
)
from app.parallel_engine import (
    parse_parallel_groups,
    detect_parallel_deadlock,
    get_parallel_path_levels,
    check_branch_all_rejected,
    check_branch_complete,
    check_parallel_group_ready_to_merge,
    check_any_branch_rejected,
    generate_branch_id,
    generate_parallel_group_id,
)
from app.schemas import (
    ApprovalTimelineEvent,
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


def _user_is_approver_for_node(db: Session, user_id: int, node_record: ApprovalNodeRecord) -> tuple[bool, bool]:
    """
    返回 (是否是审批人, 是否是精确匹配（按名字匹配优先于按角色匹配）
    """
    if user_id is None:
        return False, False
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return False, False
    user_name = user.real_name or user.username
    if node_record.approver_name == user_name:
        return True, True
    user_role_codes = _get_user_role_codes(db, user_id)
    if "super_admin" in user_role_codes or "asset_admin" in user_role_codes:
        return True, False
    if node_record.approver_role in user_role_codes:
        return True, False
    return False, False


def _get_applicant_department(db: Session, applicant_name: str) -> str | None:
    user = (
        db.query(User)
        .filter((User.real_name == applicant_name) | (User.username == applicant_name))
        .first()
    )
    return user.department if user else None


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

    chain_nodes_by_level: dict[int, ApprovalChainNode] = {}
    path_items: list[dict] = []

    if chain:
        chain_id = chain.id
        all_nodes = (
            db.query(ApprovalChainNode)
            .options(
                joinedload(ApprovalChainNode.approvers),
                joinedload(ApprovalChainNode.conditions).joinedload(ApprovalChainCondition.rules),
            )
            .filter(ApprovalChainNode.chain_id == chain.id)
            .order_by(ApprovalChainNode.level.asc())
            .all()
        )
        for n in all_nodes:
            chain_nodes_by_level[n.level] = n

        applicant_department = _get_applicant_department(db, data.applicant)
        ctx = ConditionEvaluationContext(
            price=asset.purchase_price,
            category=asset.category,
            applicant_department=applicant_department,
        )

        has_parallel = any(n.node_type != ChainNodeType.APPROVAL for n in all_nodes)

        if has_parallel:
            path_items = get_parallel_path_levels(all_nodes, ctx) or []
            approval_count = 0
            for item in path_items:
                if item["type"] == "approval":
                    approval_count += 1
                elif item["type"] == "branch":
                    approval_count += len(item.get("nodes", []))
            total_levels = approval_count if approval_count > 0 else 1
        else:
            all_levels = set(chain_nodes_by_level.keys())
            visited: set[int] = set()
            current_level = 1
            max_iterations = len(all_levels) * 2 + 10
            iterations = 0
            resolved_path_levels: list[int] = []
            while current_level is not None and current_level in all_levels and iterations < max_iterations:
                iterations += 1
                if current_level in visited:
                    logger.warning(
                        "审批单创建时检测到路径环路，中断路径生成: chain_id=%s, level=%s",
                        chain.id, current_level,
                    )
                    break
                visited.add(current_level)
                resolved_path_levels.append(current_level)
                node = chain_nodes_by_level[current_level]
                current_level = resolve_next_level(node, ctx, all_levels)

            for lv in resolved_path_levels:
                path_items.append({
                    "type": "approval",
                    "level": lv,
                    "node": chain_nodes_by_level.get(lv),
                })
            total_levels = len(resolved_path_levels) if resolved_path_levels else 1

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

    if chain and chain_id and path_items:
        now = datetime.now()
        record_level_counter = 0
        first_level_nodes: list[int] = []

        def process_approval_item(item: dict, is_parallel_branch: bool = False) -> None:
            nonlocal record_level_counter
            node = item.get("node")
            if not node:
                return
            if node.node_type in (ChainNodeType.PARALLEL_START, ChainNodeType.PARALLEL_END):
                return
            if not node.approvers:
                raise HTTPException(
                    status_code=500,
                    detail=f"审批链节点（level={node.level}）缺少审批人配置",
                )
            record_level_counter += 1
            record_level = record_level_counter
            timeout_at = None
            if not is_parallel_branch and record_level == 1 and node.timeout_minutes is not None:
                timeout_at = now + timedelta(minutes=node.timeout_minutes)
            if is_parallel_branch and node.timeout_minutes is not None:
                timeout_at = now + timedelta(minutes=node.timeout_minutes)

            group_id = item.get("group_id")
            branch_id = item.get("branch_id")
            branch_index = item.get("branch_index")

            for approver in node.approvers:
                record = ApprovalNodeRecord(
                    approval_id=approval.id,
                    chain_node_id=node.id,
                    chain_node_approver_id=approver.id,
                    level=record_level,
                    chain_node_level=node.level,
                    parallel_group_id=group_id,
                    branch_id=branch_id,
                    branch_index=branch_index,
                    approver_role=approver.approver_role,
                    approver_name=approver.approver_name,
                    status=ApprovalStatus.PENDING,
                    timeout_at=timeout_at,
                )
                db.add(record)
            if record_level == 1 or is_parallel_branch:
                first_level_nodes.append(record_level)

        for item in path_items:
            if item["type"] == "approval":
                process_approval_item(item, is_parallel_branch=False)
            elif item["type"] == "branch":
                for branch_node in item.get("nodes", []):
                    process_approval_item(branch_node, is_parallel_branch=True)

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
                    _not_transferred_sql(),
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


def _is_active_record(record: ApprovalNodeRecord) -> bool:
    if record.transfer_status and record.transfer_status == TransferStatus.TRANSFERRED:
        return False
    return True


def _filter_active_records(records: list[ApprovalNodeRecord]) -> list[ApprovalNodeRecord]:
    return [r for r in records if _is_active_record(r)]


def _not_transferred_sql():
    from sqlalchemy import or_
    return or_(
        ApprovalNodeRecord.transfer_status.is_(None),
        ApprovalNodeRecord.transfer_status != TransferStatus.TRANSFERRED,
    )


def _get_node_mode(db: Session, chain_node_id: int) -> ApprovalMode:
    chain_node = db.query(ApprovalChainNode).filter(ApprovalChainNode.id == chain_node_id).first()
    if not chain_node:
        return ApprovalMode.SINGLE
    return chain_node.mode


def _get_node_escalation_config(db: Session, chain_node_id: int) -> tuple[TimeoutEscalationStrategy, int | None]:
    chain_node = db.query(ApprovalChainNode).filter(ApprovalChainNode.id == chain_node_id).first()
    if not chain_node:
        return TimeoutEscalationStrategy.ESCALATE_TO_LEVEL, None
    strategy = chain_node.escalation_strategy or TimeoutEscalationStrategy.ESCALATE_TO_LEVEL
    target = chain_node.escalation_target_level
    return strategy, target


def _get_chain_node_map(db: Session, chain_id: int) -> dict[int, ApprovalChainNode]:
    nodes = (
        db.query(ApprovalChainNode)
        .options(joinedload(ApprovalChainNode.approvers))
        .filter(ApprovalChainNode.chain_id == chain_id)
        .all()
    )
    return {node.level: node for node in nodes}


def _chain_node_level_to_record_level(
    db: Session, approval_id: int, chain_node_level: int
) -> int | None:
    record = (
        db.query(ApprovalNodeRecord)
        .filter(
            ApprovalNodeRecord.approval_id == approval_id,
            ApprovalNodeRecord.chain_node_level == chain_node_level,
        )
        .first()
    )
    return record.level if record else None


def _ensure_record_level_for_chain_node(
    db: Session, approval: Approval, target_chain_node_level: int
) -> int | None:
    """确保指定链节点级别存在对应的审批记录。
    如果不存在，则按 chain_node_level 顺序插入新级别，
    重新编号所有 record_level 使其与链节点逻辑顺序一致，
    并生成该级别的所有审批人记录。
    新记录的 timeout_at 根据链节点的 timeout_minutes 计算。

    _get_next_record_level 通过排序去重取下一个值，虽不要求
    level连续，但要求level的排序顺序与链节点逻辑顺序一致，
    否则升级后无法正确流转到下一级。

    Returns:
        新创建（或已存在）的记录级别，失败时返回None
    """
    existing_record_level = _chain_node_level_to_record_level(db, approval.id, target_chain_node_level)
    if existing_record_level is not None:
        return existing_record_level

    if not approval.chain_id:
        return None

    chain_nodes = _get_chain_node_map(db, approval.chain_id)
    if target_chain_node_level not in chain_nodes:
        return None

    target_node = chain_nodes[target_chain_node_level]
    if not target_node.approvers:
        return None

    all_records = (
        db.query(ApprovalNodeRecord)
        .filter(ApprovalNodeRecord.approval_id == approval.id)
        .all()
    )

    existing_chain_levels = sorted(set(r.chain_node_level for r in all_records))
    new_chain_levels = sorted(existing_chain_levels + [target_chain_node_level])
    new_level_map = {chain_lv: i + 1 for i, chain_lv in enumerate(new_chain_levels)}

    old_current_chain_level = None
    for r in all_records:
        if r.level == approval.current_level:
            old_current_chain_level = r.chain_node_level
            break

    for record in all_records:
        new_lv = new_level_map[record.chain_node_level]
        if new_lv != record.level:
            record.level = new_lv

    new_record_level = new_level_map[target_chain_node_level]

    now = datetime.now()
    if target_node.timeout_minutes is not None:
        timeout_at = now + timedelta(minutes=target_node.timeout_minutes)
    else:
        timeout_at = None

    for approver in target_node.approvers:
        record = ApprovalNodeRecord(
            approval_id=approval.id,
            chain_node_id=target_node.id,
            chain_node_approver_id=approver.id,
            level=new_record_level,
            chain_node_level=target_node.level,
            approver_role=approver.approver_role,
            approver_name=approver.approver_name,
            status=ApprovalStatus.PENDING,
            timeout_at=timeout_at,
        )
        db.add(record)

    if old_current_chain_level is not None:
        approval.current_level = new_level_map[old_current_chain_level]

    approval.total_levels = len(new_chain_levels)

    db.flush()
    return new_record_level


def _detect_escalation_cycle(
    db: Session,
    chain_id: int,
    current_chain_level: int,
    target_chain_level: int,
) -> bool:
    chain_nodes = _get_chain_node_map(db, chain_id)
    if target_chain_level not in chain_nodes:
        return False

    visited: set[int] = set()
    visited.add(current_chain_level)

    current = target_chain_level
    max_iterations = len(chain_nodes) * 2 + 10
    iterations = 0

    while current is not None and current in chain_nodes and iterations < max_iterations:
        iterations += 1
        if current in visited:
            return True
        visited.add(current)

        node = chain_nodes.get(current)
        if not node:
            break

        strategy = node.escalation_strategy or TimeoutEscalationStrategy.ESCALATE_TO_LEVEL
        if strategy == TimeoutEscalationStrategy.ESCALATE_TO_LEVEL and node.escalation_target_level is not None:
            current = node.escalation_target_level
        else:
            break

    return False


def _escalation_resolve_target_level(
    db: Session,
    approval: Approval,
    current_chain_node_level: int,
    strategy: TimeoutEscalationStrategy,
    configured_target: int | None,
) -> tuple[int | None, str]:
    if strategy == TimeoutEscalationStrategy.ESCALATE_TO_LEVEL:
        if configured_target is not None:
            if not approval.chain_id:
                return None, "审批单无关联审批链，自动驳回"

            chain_nodes = _get_chain_node_map(db, approval.chain_id)
            if configured_target not in chain_nodes:
                return None, f"配置的升级目标级别L{configured_target}不在审批链定义中，自动驳回"

            if _detect_escalation_cycle(db, approval.chain_id, current_chain_node_level, configured_target):
                return None, f"升级到L{configured_target}会形成环路，自动驳回"

            record_level = _ensure_record_level_for_chain_node(db, approval, configured_target)
            if record_level is None:
                return None, f"升级目标级别L{configured_target}不在当前审批路径中，自动驳回"

            return record_level, ""

        return _get_next_record_level(db, approval.id, approval.current_level), ""
    if strategy == TimeoutEscalationStrategy.AUTO_REJECT:
        return None, "超时策略配置为自动驳回"
    if strategy == TimeoutEscalationStrategy.SKIP_NODE:
        next_level = _get_next_record_level(db, approval.id, approval.current_level)
        return next_level, ""
    return _get_next_record_level(db, approval.id, approval.current_level), ""


def _set_next_level_timeout(db: Session, approval: Approval, context: str = "unknown") -> None:
    next_records = (
        db.query(ApprovalNodeRecord)
        .filter(
            ApprovalNodeRecord.approval_id == approval.id,
            ApprovalNodeRecord.level == approval.current_level,
            ApprovalNodeRecord.status == ApprovalStatus.PENDING,
            _not_transferred_sql(),
        )
        .all()
    )
    if not next_records:
        logger.warning(
            "[%s] 审批单#%d 下一级节点(level=%d)不存在待处理记录，无法设置超时",
            context, approval.id, approval.current_level,
        )
        return
    chain_node = (
        db.query(ApprovalChainNode)
        .filter(ApprovalChainNode.id == next_records[0].chain_node_id)
        .first()
    )
    if not chain_node or chain_node.timeout_minutes is None:
        return
    new_timeout = datetime.now() + timedelta(minutes=chain_node.timeout_minutes)
    for record in next_records:
        if record.timeout_at is not None:
            logger.warning(
                "[%s] 审批单#%d 节点(level=%d, approver=%s) timeout_at 已存在，"
                "重新以当前时间计算覆盖: 原值=%s, 新值=%s",
                context, approval.id, record.level,
                record.approver_name, record.timeout_at, new_timeout,
            )
        record.timeout_at = new_timeout


def _get_next_record_level(db: Session, approval_id: int, current_level: int) -> int | None:
    all_levels = [
        r[0] for r in db.query(ApprovalNodeRecord.level)
        .filter(ApprovalNodeRecord.approval_id == approval_id)
        .distinct()
        .order_by(ApprovalNodeRecord.level.asc())
        .all()
    ]
    idx = all_levels.index(current_level) if current_level in all_levels else -1
    if idx < 0 or idx >= len(all_levels) - 1:
        return None
    return all_levels[idx + 1]


def _get_next_record_level_by_level(db: Session, approval_id: int, chain_end_level: int) -> int | None:
    all_records = (
        db.query(ApprovalNodeRecord)
        .filter(ApprovalNodeRecord.approval_id == approval_id)
        .order_by(ApprovalNodeRecord.level.asc(), ApprovalNodeRecord.chain_node_level.asc())
        .all()
    )
    found_parallel_end = False
    for rec in all_records:
        if found_parallel_end and rec.level is not None and rec.status == ApprovalStatus.PENDING:
            return rec.level
        if rec.chain_node_level == chain_end_level:
            found_parallel_end = True
    return None


def _get_next_record_level_in_branch(db: Session, approval_id: int, current_level: int, branch_id: str) -> int | None:
    branch_records = (
        db.query(ApprovalNodeRecord)
        .filter(
            ApprovalNodeRecord.approval_id == approval_id,
            ApprovalNodeRecord.branch_id == branch_id,
        )
        .order_by(ApprovalNodeRecord.level.asc())
        .all()
    )
    levels = sorted(list({r.level for r in branch_records}))
    idx = levels.index(current_level) if current_level in levels else -1
    if idx < 0 or idx >= len(levels) - 1:
        return None
    return levels[idx + 1]


def _set_branch_level_timeout(db: Session, approval_id: int, level: int, branch_id: str, context: str = "unknown") -> None:
    next_records = (
        db.query(ApprovalNodeRecord)
        .filter(
            ApprovalNodeRecord.approval_id == approval_id,
            ApprovalNodeRecord.level == level,
            ApprovalNodeRecord.branch_id == branch_id,
            ApprovalNodeRecord.status == ApprovalStatus.PENDING,
            _not_transferred_sql(),
        )
        .all()
    )
    if not next_records:
        return
    chain_node = (
        db.query(ApprovalChainNode)
        .filter(ApprovalChainNode.id == next_records[0].chain_node_id)
        .first()
    )
    if not chain_node or chain_node.timeout_minutes is None:
        return
    new_timeout = datetime.now() + timedelta(minutes=chain_node.timeout_minutes)
    for record in next_records:
        if record.timeout_at is not None:
            logger.warning(
                "[%s] 审批单#%d 分支节点(branch=%s, level=%d, approver=%s) timeout_at 已存在，重新覆盖",
                context, approval_id, branch_id, level, record.approver_name,
            )
        record.timeout_at = new_timeout


def _finish_approval_as_approved(
    db: Session,
    approval: Approval,
    asset: Asset,
    approver_name: str,
    approver_id: int | None,
    opinion: str | None,
) -> Approval:
    approval.status = ApprovalStatus.APPROVED
    approval.approver = approver_name
    approval.approval_opinion = opinion

    if approval.approval_type == ApprovalType.ALLOCATE:
        asset.status = AssetStatus.ALLOCATED
        asset.assignee = approval.assignee
        action = "领用审批通过"
        detail = f"审批通过，领用人: {approval.assignee}。{opinion or ''}"
    elif approval.approval_type == ApprovalType.SCRAP:
        asset.status = AssetStatus.SCRAPPED
        asset.assignee = None
        action = "报废审批通过"
        detail = f"审批通过。{opinion or ''}"
    else:
        action = "审批通过"
        detail = opinion or ""

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


def _finish_approval_as_rejected(
    db: Session,
    approval: Approval,
    asset: Asset,
    approver_name: str,
    approver_id: int | None,
    opinion: str | None,
) -> Approval:
    approval.status = ApprovalStatus.REJECTED
    approval.approver = approver_name
    approval.approval_opinion = opinion
    asset.status = approval.previous_status

    if approval.approval_type == ApprovalType.ALLOCATE:
        action = "领用审批驳回"
    elif approval.approval_type == ApprovalType.SCRAP:
        action = "报废审批驳回"
    else:
        action = "审批驳回"

    log = AssetLog(
        asset_id=asset.id,
        action=action,
        operator=approver_name,
        operator_id=approver_id,
        detail=opinion or "审批驳回",
    )
    db.add(log)
    db.commit()
    db.refresh(approval)
    return approval


def _check_proxy_conflict_for_countersign(
    db: Session,
    approver: User,
    approval_id: int,
    level: int,
) -> None:
    approver_name = approver.real_name or approver.username
    same_level_records = (
        db.query(ApprovalNodeRecord)
        .filter(
            ApprovalNodeRecord.approval_id == approval_id,
            ApprovalNodeRecord.level == level,
        )
        .all()
    )
    for record in same_level_records:
        if record.approver_name == approver_name or record.approver_role in _get_user_role_codes(db, approver.id):
            raise HTTPException(
                status_code=400,
                detail="代理审批冲突：您作为直接审批人出现在同一级会签节点中，不能代理审批该节点",
            )


def approve_approval(db: Session, approval_id: int, data: ApprovalAction, approver: User | None = None) -> Approval:
    approval = (
        db.query(Approval)
        .filter(Approval.id == approval_id)
        .with_for_update()
        .first()
    )
    if not approval:
        raise HTTPException(status_code=404, detail="审批单不存在")

    db.refresh(approval)
    if approval.status != ApprovalStatus.PENDING:
        raise HTTPException(
            status_code=409,
            detail="并发冲突：该审批单已被其他审批人处理，请刷新后重试",
        )

    asset = get_asset(db, approval.asset_id)
    if asset.status != AssetStatus.PENDING_APPROVAL:
        raise HTTPException(status_code=400, detail="资产状态异常，不是待审批状态")

    approver_name = approver.real_name or approver.username if approver else "admin"
    approver_id = approver.id if approver else None

    now = datetime.now()

    all_pending_records = (
        db.query(ApprovalNodeRecord)
        .filter(
            ApprovalNodeRecord.approval_id == approval_id,
            ApprovalNodeRecord.status == ApprovalStatus.PENDING,
        )
        .with_for_update()
        .all()
    )

    if not all_pending_records:
        raise HTTPException(status_code=400, detail="当前没有待处理的审批节点")

    approval.updated_at = datetime.now()
    db.flush()

    pending_record = None
    is_direct_approver = False
    is_proxy_approver = False
    proxy_principal_name = None
    fuzzy_match_candidate = None
    node_mode = ApprovalMode.SINGLE

    for record in all_pending_records:
        if record.transfer_status and record.transfer_status == TransferStatus.TRANSFERRED:
            continue

        if approver:
            is_approver, is_exact = _user_is_approver_for_node(db, approver.id, record)
            if is_approver and is_exact:
                pending_record = record
                is_direct_approver = True
                node_mode = _get_node_mode(db, record.chain_node_id)
                break
            elif is_approver and not is_exact and fuzzy_match_candidate is None:
                fuzzy_match_candidate = record

    if not pending_record and fuzzy_match_candidate:
        pending_record = fuzzy_match_candidate
        is_direct_approver = True
        node_mode = _get_node_mode(db, pending_record.chain_node_id)

    if not pending_record and approver:
        for record in all_pending_records:
            if record.transfer_status and record.transfer_status == TransferStatus.TRANSFERRED:
                continue

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
                    if record.approver_role in principal_role_codes:
                        if _check_circular_proxy(db, principal.id, approver.id, approval.applicant):
                            raise HTTPException(status_code=400, detail="循环代理检测：代理人同时也是申请人，无法代理审批")

                        rec_mode = _get_node_mode(db, record.chain_node_id)
                        if rec_mode in (ApprovalMode.ALL_SIGN, ApprovalMode.OR_SIGN):
                            _check_proxy_conflict_for_countersign(db, approver, approval_id, record.level)

                        pending_record = record
                        is_proxy_approver = True
                        proxy_principal_name = principal.real_name or principal.username
                        node_mode = rec_mode
                        break
            if pending_record:
                break

    if not pending_record:
        raise HTTPException(status_code=400, detail="当前没有您需要审批的待处理节点，或节点已处理")

    if approver and not is_direct_approver and not is_proxy_approver:
        raise HTTPException(
            status_code=403,
            detail=f"您没有权限审批此节点",
        )

    db.refresh(pending_record)
    if pending_record.status != ApprovalStatus.PENDING:
        raise HTTPException(
            status_code=409,
            detail="并发冲突：该节点已被其他审批人处理，请刷新后重试",
        )

    pending_record.status = ApprovalStatus.APPROVED
    pending_record.opinion = data.opinion
    pending_record.acted_at = now

    if is_proxy_approver and approver:
        pending_record.actual_approver = approver_name
        pending_record.proxy_source = proxy_principal_name

    same_level_records = (
        db.query(ApprovalNodeRecord)
        .filter(
            ApprovalNodeRecord.approval_id == approval_id,
            ApprovalNodeRecord.level == pending_record.level,
        )
        .with_for_update()
        .all()
    )

    level_complete = False
    active_records = _filter_active_records(same_level_records)
    if node_mode == ApprovalMode.SINGLE:
        level_complete = True
    elif node_mode == ApprovalMode.ALL_SIGN:
        all_approved = all(
            r.status == ApprovalStatus.APPROVED for r in active_records
        )
        level_complete = all_approved
    elif node_mode == ApprovalMode.OR_SIGN:
        db.flush()
        for r in active_records:
            if r is not pending_record:
                db.refresh(r)
        any_approved = any(
            r.status == ApprovalStatus.APPROVED for r in active_records
        )
        any_pending = any(
            r.status == ApprovalStatus.PENDING for r in active_records
        )
        if any_approved and not any_pending:
            raise HTTPException(
                status_code=409,
                detail="并发冲突：该或签节点已被其他审批人处理，请刷新后重试",
            )
        if any_approved:
            for r in active_records:
                if r.status == ApprovalStatus.PENDING:
                    r.status = ApprovalStatus.APPROVED
                    r.opinion = "或签模式自动通过"
                    r.acted_at = now
            level_complete = True

    if not level_complete:
        db.commit()
        db.refresh(approval)
        return approval

    approval.updated_at = datetime.now()
    db.flush()

    is_parallel_branch = pending_record.parallel_group_id is not None and pending_record.branch_id is not None
    chain = None
    all_chain_nodes: list[ApprovalChainNode] = []

    if approval.chain_id:
        chain = db.query(ApprovalChain).filter(ApprovalChain.id == approval.chain_id).first()
        if chain:
            all_chain_nodes = (
                db.query(ApprovalChainNode)
                .options(joinedload(ApprovalChainNode.approvers))
                .filter(ApprovalChainNode.chain_id == chain.id)
                .order_by(ApprovalChainNode.level.asc())
                .all()
            )

    all_records = (
        db.query(ApprovalNodeRecord)
        .filter(ApprovalNodeRecord.approval_id == approval_id)
        .all()
    )

    if is_parallel_branch:
        group_id = pending_record.parallel_group_id
        branch_id = pending_record.branch_id

        branch_all_records = [r for r in all_records if r.branch_id == branch_id]
        branch_chain_nodes = [n for n in all_chain_nodes if n.branch_id == branch_id]

        branch_finished = check_branch_complete(branch_all_records, branch_id, branch_chain_nodes)
        if branch_finished:
            for r in branch_all_records:
                r.branch_complete = True

            if check_branch_all_rejected(all_records, branch_id):
                return _finish_approval_as_rejected(
                    db, approval, asset, approver_name, approver_id, data.opinion or "并行分支全部驳回"
                )

            group_ready = check_parallel_group_ready_to_merge(all_records, group_id, all_chain_nodes)
            if group_ready:
                if check_any_branch_rejected(all_records, group_id):
                    return _finish_approval_as_rejected(
                        db, approval, asset, approver_name, approver_id, data.opinion or "并行存在驳回分支"
                    )

                end_node = next((n for n in all_chain_nodes if n.parallel_group_id == group_id and n.node_type == ChainNodeType.PARALLEL_END), None)
                if end_node:
                    next_after_parallel = _get_next_record_level_by_level(db, approval_id, end_node.level)
                    if next_after_parallel is not None:
                        approval.current_level = next_after_parallel
                        _set_next_level_timeout(db, approval, "approve_approval_parallel_merge")
                    else:
                        return _finish_approval_as_approved(
                            db, approval, asset, approver_name, approver_id, data.opinion
                        )
                else:
                    next_level = _get_next_record_level(db, approval_id, pending_record.level)
                    if next_level is not None:
                        approval.current_level = next_level
                        _set_next_level_timeout(db, approval, "approve_approval")
                    else:
                        return _finish_approval_as_approved(
                            db, approval, asset, approver_name, approver_id, data.opinion
                        )
            else:
                pass
        else:
            next_in_branch = _get_next_record_level_in_branch(
                db, approval_id, pending_record.level, branch_id
            )
            if next_in_branch is not None:
                _set_branch_level_timeout(db, approval_id, next_in_branch, branch_id, "approve_approval_branch")

        mode_desc = {
            ApprovalMode.SINGLE: "单人审批",
            ApprovalMode.ALL_SIGN: "会签",
            ApprovalMode.OR_SIGN: "或签",
        }.get(node_mode, "审批")

        branch_info = f"，分支{pending_record.branch_index + 1}" if pending_record.branch_index is not None else ""
        level_desc = f"第{pending_record.level}/{approval.total_levels}级{mode_desc}{branch_info}通过"
        proxy_info = f"（代理审批，代理人: {approver_name}，代原审批人: {pending_record.proxy_source}）" if pending_record.proxy_source else ""
        log = AssetLog(
            asset_id=asset.id,
            action="多级审批通过",
            operator=approver_name,
            operator_id=approver_id,
            detail=f"{level_desc}，审批人: {pending_record.approver_name}{proxy_info}。{data.opinion or ''}",
        )
        db.add(log)
        db.commit()
        db.refresh(approval)
        return approval

    next_level = _get_next_record_level(db, approval_id, pending_record.level)

    if next_level is not None:
        approval.current_level = next_level
        _set_next_level_timeout(db, approval, "approve_approval")

        mode_desc = {
            ApprovalMode.SINGLE: "单人审批",
            ApprovalMode.ALL_SIGN: "会签",
            ApprovalMode.OR_SIGN: "或签",
        }.get(node_mode, "审批")

        level_desc = f"第{pending_record.level}/{approval.total_levels}级{mode_desc}通过"
        proxy_info = f"（代理审批，代理人: {approver_name}，代原审批人: {pending_record.proxy_source}）" if pending_record.proxy_source else ""
        log = AssetLog(
            asset_id=asset.id,
            action="多级审批通过",
            operator=approver_name,
            operator_id=approver_id,
            detail=f"{level_desc}，审批人: {pending_record.approver_name}{proxy_info}。{data.opinion or ''}",
        )
        db.add(log)
        db.commit()
        db.refresh(approval)
        return approval

    return _finish_approval_as_approved(db, approval, asset, approver_name, approver_id, data.opinion)


def reject_approval(db: Session, approval_id: int, data: ApprovalAction, approver: User | None = None) -> Approval:
    approval = (
        db.query(Approval)
        .filter(Approval.id == approval_id)
        .with_for_update()
        .first()
    )
    if not approval:
        raise HTTPException(status_code=404, detail="审批单不存在")

    db.refresh(approval)
    if approval.status != ApprovalStatus.PENDING:
        raise HTTPException(
            status_code=409,
            detail="并发冲突：该审批单已被其他审批人处理，请刷新后重试",
        )

    asset = get_asset(db, approval.asset_id)
    if asset.status != AssetStatus.PENDING_APPROVAL:
        raise HTTPException(status_code=400, detail="资产状态异常，不是待审批状态")

    approver_name = approver.real_name or approver.username if approver else "admin"
    approver_id = approver.id if approver else None

    now = datetime.now()

    all_pending_records = (
        db.query(ApprovalNodeRecord)
        .filter(
            ApprovalNodeRecord.approval_id == approval_id,
            ApprovalNodeRecord.status == ApprovalStatus.PENDING,
        )
        .with_for_update()
        .all()
    )

    if not all_pending_records:
        raise HTTPException(status_code=400, detail="当前没有待处理的审批节点")

    approval.updated_at = datetime.now()
    db.flush()

    pending_record = None
    is_direct_approver = False
    is_proxy_approver = False
    proxy_principal_name = None
    fuzzy_match_candidate = None
    node_mode = ApprovalMode.SINGLE

    for record in all_pending_records:
        if record.transfer_status and record.transfer_status == TransferStatus.TRANSFERRED:
            continue

        if approver:
            is_approver, is_exact = _user_is_approver_for_node(db, approver.id, record)
            if is_approver and is_exact:
                pending_record = record
                is_direct_approver = True
                node_mode = _get_node_mode(db, record.chain_node_id)
                break
            elif is_approver and not is_exact and fuzzy_match_candidate is None:
                fuzzy_match_candidate = record

    if not pending_record and fuzzy_match_candidate:
        pending_record = fuzzy_match_candidate
        is_direct_approver = True
        node_mode = _get_node_mode(db, pending_record.chain_node_id)

    if not pending_record and approver:
        for record in all_pending_records:
            if record.transfer_status and record.transfer_status == TransferStatus.TRANSFERRED:
                continue

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
                    if record.approver_role in principal_role_codes:
                        if _check_circular_proxy(db, principal.id, approver.id, approval.applicant):
                            raise HTTPException(status_code=400, detail="循环代理检测：代理人同时也是申请人，无法代理审批")

                        rec_mode = _get_node_mode(db, record.chain_node_id)
                        if rec_mode in (ApprovalMode.ALL_SIGN, ApprovalMode.OR_SIGN):
                            _check_proxy_conflict_for_countersign(db, approver, approval_id, record.level)

                        pending_record = record
                        is_proxy_approver = True
                        proxy_principal_name = principal.real_name or principal.username
                        node_mode = rec_mode
                        break
            if pending_record:
                break

    if not pending_record:
        raise HTTPException(
            status_code=409,
            detail="并发冲突：该节点已被其他审批人处理，请刷新后重试",
        )

    if approver and not is_direct_approver and not is_proxy_approver:
        raise HTTPException(
            status_code=403,
            detail=f"您没有权限审批此节点",
        )

    db.refresh(pending_record)
    if pending_record.status != ApprovalStatus.PENDING:
        raise HTTPException(
            status_code=409,
            detail="并发冲突：该节点已被其他审批人处理，请刷新后重试",
        )

    pending_record.status = ApprovalStatus.REJECTED
    pending_record.opinion = data.opinion
    pending_record.acted_at = now

    if is_proxy_approver and approver:
        pending_record.actual_approver = approver_name
        pending_record.proxy_source = proxy_principal_name

    same_level_records = (
        db.query(ApprovalNodeRecord)
        .filter(
            ApprovalNodeRecord.approval_id == approval_id,
            ApprovalNodeRecord.level == pending_record.level,
        )
        .with_for_update()
        .all()
    )

    db.flush()
    for r in same_level_records:
        if r is not pending_record:
            db.refresh(r)
        if r.status == ApprovalStatus.PENDING:
            r.status = ApprovalStatus.REJECTED
            r.opinion = f"节点被驳回：{data.opinion or '无意见'}"
            r.acted_at = now

    is_parallel_branch = pending_record.parallel_group_id is not None and pending_record.branch_id is not None

    all_records = (
        db.query(ApprovalNodeRecord)
        .filter(ApprovalNodeRecord.approval_id == approval_id)
        .all()
    )

    if is_parallel_branch:
        branch_id = pending_record.branch_id
        if check_branch_all_rejected(all_records, branch_id):
            return _finish_approval_as_rejected(
                db, approval, asset, approver_name, approver_id, data.opinion or f"并行分支全部驳回"
            )

        mode_desc = {
            ApprovalMode.SINGLE: "单人审批",
            ApprovalMode.ALL_SIGN: "会签",
            ApprovalMode.OR_SIGN: "或签",
        }.get(node_mode, "审批")
        branch_info = f"，分支{pending_record.branch_index + 1}" if pending_record.branch_index is not None else ""
        level_info = f"（第{pending_record.level}/{approval.total_levels}级{mode_desc}{branch_info}驳回）"
        proxy_info = f"（代理审批，代理人: {approver_name}，代原审批人: {pending_record.proxy_source}）" if pending_record.proxy_source else ""
        action_type = "领用" if approval.approval_type == ApprovalType.ALLOCATE else "报废"
        log = AssetLog(
            asset_id=asset.id,
            action=f"{action_type}审批节点驳回",
            operator=approver_name,
            operator_id=approver_id,
            detail=f"审批节点驳回{level_info}{proxy_info}。{data.opinion or ''}",
        )
        db.add(log)
        db.commit()
        db.refresh(approval)
        return approval

    remaining_records = (
        db.query(ApprovalNodeRecord)
        .filter(
            ApprovalNodeRecord.approval_id == approval_id,
            ApprovalNodeRecord.level > pending_record.level,
        )
        .all()
    )
    for r in remaining_records:
        r.status = ApprovalStatus.REJECTED

    return _finish_approval_as_rejected(db, approval, asset, approver_name, approver_id, data.opinion)


def withdraw_approval(db: Session, approval_id: int, reason: str | None = None, applicant: User | None = None) -> Approval:
    from app.auth import get_user_display_name

    approval = get_approval(db, approval_id)
    if approval.status != ApprovalStatus.PENDING:
        raise HTTPException(status_code=400, detail="审批单已处理，不可撤回")

    if applicant:
        applicant_name = get_user_display_name(applicant)
        if approval.applicant != applicant_name:
            from app.auth import is_admin_user
            if not is_admin_user(db, applicant.id):
                raise HTTPException(status_code=403, detail="只有申请人或管理员可以撤回审批")

    asset = get_asset(db, approval.asset_id)
    if asset.status != AssetStatus.PENDING_APPROVAL:
        raise HTTPException(status_code=400, detail="资产状态异常，无法撤回")

    now = datetime.now()

    approval.status = ApprovalStatus.WITHDRAWN
    approval.approval_opinion = reason

    node_records = (
        db.query(ApprovalNodeRecord)
        .filter(ApprovalNodeRecord.approval_id == approval_id)
        .all()
    )
    for record in node_records:
        if record.status == ApprovalStatus.PENDING:
            record.status = ApprovalStatus.WITHDRAWN
            record.acted_at = now
            record.opinion = "审批已撤回"

    asset.status = approval.previous_status

    applicant_display = applicant.real_name or applicant.username if applicant else approval.applicant
    applicant_id = applicant.id if applicant else None

    action_type = "领用" if approval.approval_type == ApprovalType.ALLOCATE else "报废"
    log = AssetLog(
        asset_id=asset.id,
        action=f"{action_type}审批撤回",
        operator=applicant_display,
        operator_id=applicant_id,
        detail=reason or f"申请人撤回{action_type}审批申请",
    )
    db.add(log)

    op_log = OperationLog(
        module="approval",
        action="withdraw",
        operator=applicant_display,
        operator_id=applicant_id,
        target_type="approval",
        target_id=approval_id,
        detail=reason or "撤回审批申请",
    )
    db.add(op_log)

    db.commit()
    db.refresh(approval)
    return approval


def get_approval_reminders(db: Session, approval_id: int) -> list[ApprovalReminder]:
    return (
        db.query(ApprovalReminder)
        .filter(ApprovalReminder.approval_id == approval_id)
        .order_by(ApprovalReminder.created_at.desc())
        .all()
    )


def _find_users_by_role(db: Session, role_code: str) -> list[User]:
    from app.models import Role, UserRole

    role = db.query(Role).filter(Role.code == role_code).first()
    if not role:
        return []
    user_roles = db.query(UserRole).filter(UserRole.role_id == role.id).all()
    user_ids = [ur.user_id for ur in user_roles]
    if not user_ids:
        return []
    return db.query(User).filter(User.id.in_(user_ids), User.is_active == True).all()


def _create_notification(
    db: Session,
    user_id: int,
    notification_type: NotificationType,
    title: str,
    content: str,
    related_id: int | None = None,
    related_type: str | None = None,
) -> Notification:
    notification = Notification(
        user_id=user_id,
        type=notification_type,
        title=title,
        content=content,
        related_id=related_id,
        related_type=related_type,
    )
    db.add(notification)
    return notification


def remind_approval(db: Session, approval_id: int, message: str | None = None, applicant: User | None = None) -> Approval:
    from app.auth import get_user_display_name

    approval = get_approval(db, approval_id)
    if approval.status != ApprovalStatus.PENDING:
        raise HTTPException(status_code=400, detail="审批单已处理，不可催办")

    if applicant:
        applicant_name = get_user_display_name(applicant)
        if approval.applicant != applicant_name:
            from app.auth import is_admin_user
            if not is_admin_user(db, applicant.id):
                raise HTTPException(status_code=403, detail="只有申请人或管理员可以催办审批")

    now = datetime.now()

    current_level_records = (
        db.query(ApprovalNodeRecord)
        .filter(
            ApprovalNodeRecord.approval_id == approval_id,
            ApprovalNodeRecord.level == approval.current_level,
        )
        .all()
    )
    if not current_level_records:
        raise HTTPException(status_code=400, detail="当前审批节点不存在")

    pending_records = [r for r in current_level_records if r.status == ApprovalStatus.PENDING and _is_active_record(r)]
    if not pending_records:
        raise HTTPException(status_code=400, detail="当前节点已处理，不可催办")

    last_reminder = (
        db.query(ApprovalReminder)
        .filter(
            ApprovalReminder.approval_id == approval_id,
            ApprovalReminder.level == approval.current_level,
        )
        .order_by(ApprovalReminder.created_at.desc())
        .first()
    )
    if last_reminder and (now - last_reminder.created_at) < timedelta(hours=24):
        remaining = timedelta(hours=24) - (now - last_reminder.created_at)
        hours = int(remaining.total_seconds() // 3600)
        minutes = int((remaining.total_seconds() % 3600) // 60)
        raise HTTPException(
            status_code=400,
            detail=f"同一节点24小时内只能催办一次，还需等待 {hours}小时{minutes}分钟 后可再次催办",
        )

    reminder_by = applicant.real_name or applicant.username if applicant else "system"
    reminder_by_id = applicant.id if applicant else None

    reminder = ApprovalReminder(
        approval_id=approval_id,
        level=approval.current_level,
        reminder_by=reminder_by,
        reminder_by_id=reminder_by_id,
        message=message,
    )
    db.add(reminder)
    db.flush()

    approval.reminder_count = approval.reminder_count + 1
    approval.last_reminder_at = now

    node_reminder_count = (
        db.query(ApprovalReminder)
        .filter(
            ApprovalReminder.approval_id == approval_id,
            ApprovalReminder.level == approval.current_level,
        )
        .count()
    )

    notified_roles = set()
    for record in pending_records:
        if record.approver_role in notified_roles:
            continue
        notified_roles.add(record.approver_role)
        approver_users = _find_users_by_role(db, record.approver_role)

        action_type = "领用" if approval.approval_type == ApprovalType.ALLOCATE else "报废"
        notification_title = f"审批催办：{action_type}申请"
        notification_content = (
            f"申请人 {approval.applicant} 对 {action_type}审批单（#{approval.id}）发起了催办，"
            f"请尽快处理。待审批人：{record.approver_name}"
        )
        if message:
            notification_content += f"\n催办留言：{message}"

        for user in approver_users:
            _create_notification(
                db,
                user_id=user.id,
                notification_type=NotificationType.APPROVAL_REMINDER,
                title=notification_title,
                content=notification_content,
                related_id=approval_id,
                related_type="approval",
            )

    if node_reminder_count >= 3:
        _trigger_escalation_by_reminder(db, approval, pending_records, node_reminder_count)

    applicant_display = applicant.real_name or applicant.username if applicant else "system"
    applicant_id = applicant.id if applicant else None

    node_mode = _get_node_mode(db, current_level_records[0].chain_node_id)
    mode_desc = {
        ApprovalMode.SINGLE: "单人审批",
        ApprovalMode.ALL_SIGN: "会签",
        ApprovalMode.OR_SIGN: "或签",
    }.get(node_mode, "审批")

    op_log = OperationLog(
        module="approval",
        action="remind",
        operator=applicant_display,
        operator_id=applicant_id,
        target_type="approval",
        target_id=approval_id,
        detail=f"第{node_reminder_count}次催办（{mode_desc}节点，共{len(current_level_records)}人，待审批{len(pending_records)}人），全局第{approval.reminder_count}次，节点：第{approval.current_level}级节点",
    )
    db.add(op_log)

    db.commit()
    db.refresh(approval)
    return approval


def _trigger_escalation_by_reminder(
    db: Session,
    approval: Approval,
    pending_records: list[ApprovalNodeRecord],
    node_reminder_count: int,
) -> None:
    now = datetime.now()
    asset = db.query(Asset).filter(Asset.id == approval.asset_id).first()
    if not asset or not pending_records:
        return

    current_level = pending_records[0].level
    chain_node_id = pending_records[0].chain_node_id
    node_mode = _get_node_mode(db, chain_node_id)
    escalation_strategy, escalation_target = _get_node_escalation_config(db, chain_node_id)

    if escalation_strategy == TimeoutEscalationStrategy.SKIP_NODE:
        for record in pending_records:
            if record.status == ApprovalStatus.PENDING:
                record.status = ApprovalStatus.ESCALATED
                record.is_escalated = True
                record.acted_at = now
                record.opinion = f"催办{node_reminder_count}次未响应，跳过当前节点"
        all_level_records = (
            db.query(ApprovalNodeRecord)
            .filter(
                ApprovalNodeRecord.approval_id == approval.id,
                ApprovalNodeRecord.level == current_level,
            )
            .all()
        )
        for r in all_level_records:
            if r.status == ApprovalStatus.PENDING and _is_active_record(r):
                if r not in pending_records:
                    r.status = ApprovalStatus.ESCALATED
                    r.is_escalated = True
                    r.acted_at = now
                    r.opinion = "会签节点跳过：其他审批人催办超时"
    elif escalation_strategy == TimeoutEscalationStrategy.AUTO_REJECT:
        for record in pending_records:
            if record.status == ApprovalStatus.PENDING:
                record.status = ApprovalStatus.REJECTED
                record.is_escalated = True
                record.acted_at = now
                record.opinion = f"催办{node_reminder_count}次未响应，策略配置为自动驳回"
    else:
        for record in pending_records:
            if record.status == ApprovalStatus.PENDING:
                record.status = ApprovalStatus.ESCALATED
                record.is_escalated = True
                record.acted_at = now
                record.opinion = f"催办{node_reminder_count}次未响应，自动升级"

    next_level, cycle_reason = _escalation_resolve_target_level(
        db, approval, pending_records[0].chain_node_level, escalation_strategy, escalation_target
    )

    if next_level is not None:
        approval.current_level = next_level
        _set_next_level_timeout(db, approval, "remind_escalation")

        mode_desc = {
            ApprovalMode.SINGLE: "单人审批",
            ApprovalMode.ALL_SIGN: "会签",
            ApprovalMode.OR_SIGN: "或签",
        }.get(node_mode, "审批")

        strategy_desc = {
            TimeoutEscalationStrategy.ESCALATE_TO_LEVEL: "升级",
            TimeoutEscalationStrategy.SKIP_NODE: "跳过",
            TimeoutEscalationStrategy.AUTO_REJECT: "驳回",
        }.get(escalation_strategy, "升级")

        log = AssetLog(
            asset_id=asset.id,
            action="催办超时升级" if escalation_strategy != TimeoutEscalationStrategy.SKIP_NODE else "催办超时跳过",
            operator="系统",
            operator_id=None,
            detail=f"第{current_level}/{approval.total_levels}级{mode_desc}催办{node_reminder_count}次未响应，{strategy_desc}到第{next_level}级（{strategy_desc}{len(pending_records)}人）",
        )
        db.add(log)

        op_log = OperationLog(
            module="approval",
            action="reminder_escalate" if escalation_strategy != TimeoutEscalationStrategy.SKIP_NODE else "reminder_skip",
            operator="系统",
            detail=f"审批单#{approval.id}第{current_level}级{mode_desc}催办{node_reminder_count}次未响应，{strategy_desc}到第{next_level}级（{strategy_desc}{len(pending_records)}人）",
        )
        db.add(op_log)
    else:
        if cycle_reason:
            final_reason = cycle_reason
        elif escalation_strategy == TimeoutEscalationStrategy.AUTO_REJECT:
            final_reason = f"催办{node_reminder_count}次未响应，超时策略配置为自动驳回"
        else:
            final_reason = f"最高级审批催办{node_reminder_count}次未响应，自动驳回"
        approval.status = ApprovalStatus.REJECTED
        approval.approver = "系统"
        approval.approval_opinion = final_reason

        asset.status = approval.previous_status

        remaining_records = (
            db.query(ApprovalNodeRecord)
            .filter(
                ApprovalNodeRecord.approval_id == approval.id,
                ApprovalNodeRecord.level > current_level,
                ApprovalNodeRecord.status == ApprovalStatus.PENDING,
                _not_transferred_sql(),
            )
            .all()
        )
        for r in remaining_records:
            r.status = ApprovalStatus.REJECTED

        log_detail = (
            f"（第{current_level}/{approval.total_levels}级）{final_reason}，资产状态恢复为{approval.previous_status.value}"
        )
        log = AssetLog(
            asset_id=asset.id,
            action="催办超时驳回",
            operator="系统",
            operator_id=None,
            detail=log_detail,
        )
        db.add(log)

        op_log = OperationLog(
            module="approval",
            action="reminder_reject",
            operator="系统",
            detail=f"审批单#{approval.id}{final_reason}",
        )
        db.add(op_log)


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
                _not_transferred_sql(),
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
                            _not_transferred_sql(),
                            ApprovalNodeRecord.approver_role.in_(list(principal_role_codes)),
                        )
                        .distinct()
                        .subquery()
                    )
                    for aid in db.query(Approval.id).filter(Approval.id.in_(proxy_ids)).all():
                        approval_obj = db.query(Approval).filter(Approval.id == aid[0]).first()
                        if (approval_obj
                                and approval_obj.status != ApprovalStatus.WITHDRAWN
                                and approval_obj.applicant != (current_user.real_name or current_user.username)
                                and approval_obj.applicant != current_user.username):
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


def get_approval_node_actions(db: Session, approval_id: int) -> list[ApprovalNodeAction]:
    return (
        db.query(ApprovalNodeAction)
        .filter(ApprovalNodeAction.approval_id == approval_id)
        .order_by(ApprovalNodeAction.created_at.asc())
        .all()
    )


def _get_user_by_id(db: Session, user_id: int) -> User:
    from app.auth import get_user_display_name

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return user


def _get_node_record(db: Session, node_record_id: int) -> ApprovalNodeRecord:
    record = db.query(ApprovalNodeRecord).filter(ApprovalNodeRecord.id == node_record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="审批节点记录不存在")
    return record


def _get_user_highest_role_rank(db: Session, user_id: int) -> int:
    role_codes = _get_user_role_codes(db, user_id)
    max_rank = 0
    for code in role_codes:
        rank = BUILTIN_ROLE_HIERARCHY.get(code, 0)
        if rank > max_rank:
            max_rank = rank
    return max_rank


def add_approval_signer(
    db: Session,
    approval_id: int,
    node_record_id: int,
    target_user_id: int,
    reason: str | None,
    operator: User,
) -> Approval:
    from app.auth import get_user_display_name

    approval = get_approval(db, approval_id, operator)
    if approval.status != ApprovalStatus.PENDING:
        raise HTTPException(status_code=400, detail="审批单已处理，不可加签")

    node_record = _get_node_record(db, node_record_id)
    if node_record.approval_id != approval_id:
        raise HTTPException(status_code=400, detail="节点记录不属于该审批单")

    if node_record.level != approval.current_level:
        raise HTTPException(status_code=400, detail="只能对当前审批节点进行加签")

    node_mode = _get_node_mode(db, node_record.chain_node_id)
    if node_mode != ApprovalMode.ALL_SIGN:
        raise HTTPException(status_code=400, detail="只能对会签节点进行加签")

    current_level_records = (
        db.query(ApprovalNodeRecord)
        .filter(
            ApprovalNodeRecord.approval_id == approval_id,
            ApprovalNodeRecord.level == approval.current_level,
        )
        .all()
    )

    active_records = _filter_active_records(current_level_records)

    approved_count = sum(1 for r in active_records if r.status == ApprovalStatus.APPROVED)
    if approved_count == 0:
        raise HTTPException(status_code=400, detail="会签节点尚未有人通过，不可加签")

    all_approved = all(r.status == ApprovalStatus.APPROVED for r in active_records)
    if all_approved:
        raise HTTPException(status_code=400, detail="会签节点已全员通过，不可加签")

    operator_name = get_user_display_name(operator)
    if approval.applicant != operator_name:
        from app.auth import is_admin_user
        if not is_admin_user(db, operator.id):
            raise HTTPException(status_code=403, detail="只有审批单申请人或管理员可以加签")

    target_user = _get_user_by_id(db, target_user_id)
    target_user_name = get_user_display_name(target_user)
    target_user_roles = _get_user_role_codes(db, target_user_id)
    if not target_user_roles:
        raise HTTPException(status_code=400, detail="目标用户没有分配角色，无法作为审批人")

    for record in active_records:
        if record.approver_name == target_user_name:
            raise HTTPException(status_code=400, detail="该用户已是当前节点的审批人")

    target_role = max(target_user_roles, key=lambda r: BUILTIN_ROLE_HIERARCHY.get(r, 0))

    existing_chain_approver = (
        db.query(ApprovalChainNodeApprover)
        .filter(
            ApprovalChainNodeApprover.chain_node_id == node_record.chain_node_id,
            ApprovalChainNodeApprover.approver_name == target_user_name,
        )
        .first()
    )
    chain_node_approver_id = existing_chain_approver.id if existing_chain_approver else None

    now = datetime.now()
    new_record = ApprovalNodeRecord(
        approval_id=approval_id,
        chain_node_id=node_record.chain_node_id,
        chain_node_approver_id=chain_node_approver_id,
        level=approval.current_level,
        chain_node_level=node_record.chain_node_level,
        approver_role=target_role,
        approver_name=target_user_name,
        status=ApprovalStatus.PENDING,
        record_type=ApprovalRecordType.ADDED_SIGNER,
        is_added_signer=True,
        added_signer_by=operator_name,
        added_signer_reason=reason,
    )
    db.add(new_record)
    db.flush()

    action = ApprovalNodeAction(
        approval_id=approval_id,
        node_record_id=node_record_id,
        level=approval.current_level,
        action_type=ApprovalNodeActionType.ADD_SIGNER,
        operator=operator_name,
        operator_id=operator.id,
        target_user=target_user_name,
        target_user_id=target_user_id,
        target_role=target_role,
        reason=reason,
    )
    db.add(action)

    op_log = OperationLog(
        module="approval",
        action="add_signer",
        operator=operator_name,
        operator_id=operator.id,
        target_type="approval",
        target_id=approval_id,
        detail=f"会签加签：追加审批人 {target_user_name}（角色：{target_role}）到第{approval.current_level}级会签节点。原因：{reason or '无'}",
    )
    db.add(op_log)

    asset = get_asset(db, approval.asset_id)
    log = AssetLog(
        asset_id=asset.id,
        action="会签加签",
        operator=operator_name,
        operator_id=operator.id,
        detail=f"第{approval.current_level}级会签节点追加审批人：{target_user_name}（角色：{target_role}）。原因：{reason or '无'}",
    )
    db.add(log)

    action_type = "领用" if approval.approval_type == ApprovalType.ALLOCATE else "报废"
    notification_title = f"审批加签通知：{action_type}申请"
    notification_content = (
        f"{operator_name} 对 {action_type}审批单（#{approval.id}）进行了加签操作，"
        f"您被追加为第{approval.current_level}级会签审批人，请尽快处理。"
    )
    if reason:
        notification_content += f"\n加签原因：{reason}"
    _create_notification(
        db,
        user_id=target_user_id,
        notification_type=NotificationType.APPROVAL_SUBMITTED,
        title=notification_title,
        content=notification_content,
        related_id=approval_id,
        related_type="approval",
    )

    db.commit()
    db.refresh(approval)
    return approval


def transfer_approval(
    db: Session,
    approval_id: int,
    node_record_id: int,
    target_user_id: int,
    reason: str | None,
    operator: User,
) -> Approval:
    from app.auth import get_user_display_name

    approval = get_approval(db, approval_id, operator)
    if approval.status != ApprovalStatus.PENDING:
        raise HTTPException(status_code=400, detail="审批单已处理，不可转审")

    node_record = _get_node_record(db, node_record_id)
    if node_record.approval_id != approval_id:
        raise HTTPException(status_code=400, detail="节点记录不属于该审批单")

    if node_record.level != approval.current_level:
        raise HTTPException(status_code=400, detail="只能对当前审批节点进行转审")

    if node_record.status != ApprovalStatus.PENDING:
        raise HTTPException(status_code=400, detail="该节点已处理，不可转审")

    if node_record.transfer_status == TransferStatus.TRANSFERRED:
        raise HTTPException(status_code=400, detail="该节点已转审，不可重复转审")

    operator_name = get_user_display_name(operator)
    operator_roles = _get_user_role_codes(db, operator.id)

    is_approver = False
    if node_record.approver_role in operator_roles:
        is_approver = True

    if not is_approver and operator_name == node_record.approver_name:
        is_approver = True

    if "super_admin" in operator_roles or "asset_admin" in operator_roles:
        is_approver = True

    if not is_approver:
        active_proxies = (
            db.query(ApprovalProxy)
            .filter(
                ApprovalProxy.proxy_user_id == operator.id,
                ApprovalProxy.is_active == True,
                ApprovalProxy.start_time <= datetime.now(),
                ApprovalProxy.end_time >= datetime.now(),
            )
            .all()
        )
        for ap in active_proxies:
            principal = db.query(User).filter(User.id == ap.principal_user_id).first()
            if principal:
                principal_role_codes = _get_user_role_codes(db, principal.id)
                if node_record.approver_role in principal_role_codes:
                    is_approver = True
                    break

    if not is_approver:
        raise HTTPException(status_code=403, detail="您不是该节点的审批人，无法转审")

    target_user = _get_user_by_id(db, target_user_id)
    target_user_name = get_user_display_name(target_user)

    if target_user_name == operator_name:
        raise HTTPException(status_code=400, detail="不能转审给自己")

    target_user_roles = _get_user_role_codes(db, target_user_id)
    if not target_user_roles:
        raise HTTPException(status_code=400, detail="目标用户没有分配角色，无法审批")

    operator_rank = _get_user_highest_role_rank(db, operator.id)
    target_rank = _get_user_highest_role_rank(db, target_user_id)

    if target_rank < operator_rank:
        raise HTTPException(status_code=400, detail="只能转审给同角色或更高角色的人员")

    current_level_records = (
        db.query(ApprovalNodeRecord)
        .filter(
            ApprovalNodeRecord.approval_id == approval_id,
            ApprovalNodeRecord.level == approval.current_level,
        )
        .all()
    )
    active_records = _filter_active_records(current_level_records)
    for record in active_records:
        if record.approver_name == target_user_name and record.status == ApprovalStatus.PENDING:
            raise HTTPException(status_code=400, detail="该用户已是当前节点的待审批人")

    target_role = max(target_user_roles, key=lambda r: BUILTIN_ROLE_HIERARCHY.get(r, 0))

    now = datetime.now()

    node_record.status = ApprovalStatus.APPROVED
    node_record.opinion = f"已转审给 {target_user_name}"
    node_record.transfer_status = TransferStatus.TRANSFERRED
    node_record.transferred_from = operator_name
    node_record.transferred_to = target_user_name
    node_record.transfer_reason = reason
    node_record.record_type = ApprovalRecordType.TRANSFERRED
    node_record.acted_at = now

    existing_chain_approver = (
        db.query(ApprovalChainNodeApprover)
        .filter(
            ApprovalChainNodeApprover.chain_node_id == node_record.chain_node_id,
            ApprovalChainNodeApprover.approver_name == target_user_name,
        )
        .first()
    )
    chain_node_approver_id = existing_chain_approver.id if existing_chain_approver else None

    new_record = ApprovalNodeRecord(
        approval_id=approval_id,
        chain_node_id=node_record.chain_node_id,
        chain_node_approver_id=chain_node_approver_id,
        level=approval.current_level,
        chain_node_level=node_record.chain_node_level,
        approver_role=target_role,
        approver_name=target_user_name,
        status=ApprovalStatus.PENDING,
        record_type=ApprovalRecordType.TRANSFERRED,
        transferred_from=operator_name,
        transfer_reason=reason,
        source_record_id=node_record.id,
    )
    db.add(new_record)
    db.flush()

    action = ApprovalNodeAction(
        approval_id=approval_id,
        node_record_id=node_record_id,
        level=approval.current_level,
        action_type=ApprovalNodeActionType.TRANSFER,
        operator=operator_name,
        operator_id=operator.id,
        target_user=target_user_name,
        target_user_id=target_user_id,
        target_role=target_role,
        reason=reason,
    )
    db.add(action)

    op_log = OperationLog(
        module="approval",
        action="transfer",
        operator=operator_name,
        operator_id=operator.id,
        target_type="approval",
        target_id=approval_id,
        detail=f"转审：将第{approval.current_level}级节点审批权从 {operator_name} 转交给 {target_user_name}（角色：{target_role}）。原因：{reason or '无'}",
    )
    db.add(op_log)

    asset = get_asset(db, approval.asset_id)
    log = AssetLog(
        asset_id=asset.id,
        action="审批转审",
        operator=operator_name,
        operator_id=operator.id,
        detail=f"第{approval.current_level}级节点转审：从 {operator_name} 转交给 {target_user_name}（角色：{target_role}）。原因：{reason or '无'}",
    )
    db.add(log)

    action_type = "领用" if approval.approval_type == ApprovalType.ALLOCATE else "报废"
    notification_title = f"审批转审通知：{action_type}申请"
    notification_content = (
        f"{operator_name} 将 {action_type}审批单（#{approval.id}）的第{approval.current_level}级审批权转交给您，"
        f"请尽快处理。"
    )
    if reason:
        notification_content += f"\n转审原因：{reason}"
    _create_notification(
        db,
        user_id=target_user_id,
        notification_type=NotificationType.APPROVAL_SUBMITTED,
        title=notification_title,
        content=notification_content,
        related_id=approval_id,
        related_type="approval",
    )

    node_mode = _get_node_mode(db, node_record.chain_node_id)
    level_complete = False

    updated_level_records = (
        db.query(ApprovalNodeRecord)
        .filter(
            ApprovalNodeRecord.approval_id == approval_id,
            ApprovalNodeRecord.level == approval.current_level,
        )
        .all()
    )
    active_records = _filter_active_records(updated_level_records)

    if node_mode == ApprovalMode.ALL_SIGN:
        all_approved = all(
            r.status == ApprovalStatus.APPROVED for r in active_records
        )
        level_complete = all_approved
    elif node_mode == ApprovalMode.OR_SIGN:
        any_approved = any(
            r.status == ApprovalStatus.APPROVED for r in active_records
        )
        if any_approved:
            for r in active_records:
                if r.status == ApprovalStatus.PENDING:
                    r.status = ApprovalStatus.APPROVED
                    r.opinion = "或签模式自动通过"
                    r.acted_at = now
            level_complete = True

    next_level = _get_next_record_level(db, approval_id, approval.current_level)

    if level_complete and next_level is not None:
        approval.current_level = next_level
        _set_next_level_timeout(db, approval, "transfer_approval")

        mode_desc = {
            ApprovalMode.SINGLE: "单人审批",
            ApprovalMode.ALL_SIGN: "会签",
            ApprovalMode.OR_SIGN: "或签",
        }.get(node_mode, "审批")

        level_desc = f"第{approval.current_level - 1}/{approval.total_levels}级{mode_desc}通过"
        level_log = AssetLog(
            asset_id=asset.id,
            action="多级审批通过",
            operator=operator_name,
            operator_id=operator.id,
            detail=f"{level_desc}，转审人: {operator_name}，转审给: {target_user_name}。原因：{reason or '无'}",
        )
        db.add(level_log)

    if level_complete and next_level is None:
        approval.status = ApprovalStatus.APPROVED
        approval.approver = operator_name
        approval.approval_opinion = f"转审后全员通过。原因：{reason or '无'}"

        if approval.approval_type == ApprovalType.ALLOCATE:
            asset.status = AssetStatus.ALLOCATED
            asset.assignee = approval.assignee
            final_action = "领用审批通过"
            final_detail = f"审批通过，领用人: {approval.assignee}。"
        elif approval.approval_type == ApprovalType.SCRAP:
            asset.status = AssetStatus.SCRAPPED
            asset.assignee = None
            final_action = "报废审批通过"
            final_detail = "审批通过。"

        final_log = AssetLog(
            asset_id=asset.id,
            action=final_action,
            operator=operator_name,
            operator_id=operator.id,
            detail=final_detail,
        )
        db.add(final_log)

    db.commit()
    db.refresh(approval)
    return approval


def build_approval_timeline(
    db: Session,
    approval_id: int,
) -> list[ApprovalTimelineEvent]:
    from app.auth import get_user_display_name

    approval = get_approval(db, approval_id)
    node_records = get_approval_node_records(db, approval_id)
    node_actions = get_approval_node_actions(db, approval_id)
    reminders = get_approval_reminders(db, approval_id)

    events: list[ApprovalTimelineEvent] = []

    events.append(
        ApprovalTimelineEvent(
            id=f"submit-{approval.id}",
            event_type="submit",
            event_type_cn="提交申请",
            operator=approval.applicant,
            level=1,
            reason=approval.reason,
            created_at=approval.created_at,
        )
    )

    all_items = []

    for record in node_records:
        all_items.append({
            "type": "record",
            "data": record,
            "time": record.acted_at or record.created_at,
        })

    for action in node_actions:
        all_items.append({
            "type": "action",
            "data": action,
            "time": action.created_at,
        })

    for reminder in reminders:
        all_items.append({
            "type": "reminder",
            "data": reminder,
            "time": reminder.created_at,
        })

    all_items.sort(key=lambda x: x["time"])

    for item in all_items:
        if item["type"] == "record":
            record = item["data"]
            if record.record_type == ApprovalRecordType.ADDED_SIGNER:
                events.append(
                    ApprovalTimelineEvent(
                        id=f"add-signer-{record.id}",
                        event_type="add_signer",
                        event_type_cn="会签加签",
                        operator=record.added_signer_by or "系统",
                        target_user=record.approver_name,
                        target_role=record.approver_role,
                        level=record.level,
                        reason=record.added_signer_reason,
                        created_at=record.created_at,
                    )
                )
                if record.acted_at:
                    status_cn = {
                        ApprovalStatus.APPROVED: "通过",
                        ApprovalStatus.REJECTED: "驳回",
                    }.get(record.status, record.status.value)
                    events.append(
                        ApprovalTimelineEvent(
                            id=f"approve-{record.id}",
                            event_type="approve" if record.status == ApprovalStatus.APPROVED else "reject",
                            event_type_cn=f"加签人审批{status_cn}",
                            operator=record.approver_name,
                            level=record.level,
                            opinion=record.opinion,
                            status=record.status.value,
                            created_at=record.acted_at,
                        )
                    )
            elif record.record_type == ApprovalRecordType.TRANSFERRED and record.source_record_id:
                if record.acted_at and record.transfer_status != TransferStatus.TRANSFERRED:
                    status_cn = {
                        ApprovalStatus.APPROVED: "通过",
                        ApprovalStatus.REJECTED: "驳回",
                    }.get(record.status, record.status.value)
                    events.append(
                        ApprovalTimelineEvent(
                            id=f"approve-{record.id}",
                            event_type="approve" if record.status == ApprovalStatus.APPROVED else "reject",
                            event_type_cn=f"转审接收人审批{status_cn}",
                            operator=record.approver_name,
                            level=record.level,
                            opinion=record.opinion,
                            status=record.status.value,
                            created_at=record.acted_at,
                        )
                    )
            elif record.acted_at and record.transfer_status != TransferStatus.TRANSFERRED:
                status_cn = {
                    ApprovalStatus.APPROVED: "通过",
                    ApprovalStatus.REJECTED: "驳回",
                    ApprovalStatus.WITHDRAWN: "已撤回",
                    ApprovalStatus.ESCALATED: "已升级",
                }.get(record.status, record.status.value)

                event_type = "approve" if record.status == ApprovalStatus.APPROVED else "reject"
                event_type_cn = f"审批{status_cn}"

                if record.proxy_source:
                    event_type_cn = f"代理审批{status_cn}"

                if record.is_escalated:
                    event_type_cn = f"超时升级{status_cn}"

                events.append(
                    ApprovalTimelineEvent(
                        id=f"approve-{record.id}",
                        event_type=event_type,
                        event_type_cn=event_type_cn,
                        operator=record.actual_approver or record.approver_name,
                        target_user=record.proxy_source,
                        level=record.level,
                        opinion=record.opinion,
                        status=record.status.value,
                        created_at=record.acted_at,
                    )
                )

        elif item["type"] == "action":
            action = item["data"]
            if action.action_type == ApprovalNodeActionType.ADD_SIGNER:
                pass
            elif action.action_type == ApprovalNodeActionType.TRANSFER:
                events.append(
                    ApprovalTimelineEvent(
                        id=f"transfer-{action.id}",
                        event_type="transfer",
                        event_type_cn="转审",
                        operator=action.operator,
                        operator_id=action.operator_id,
                        target_user=action.target_user,
                        target_role=action.target_role,
                        level=action.level,
                        reason=action.reason,
                        created_at=action.created_at,
                    )
                )

        elif item["type"] == "reminder":
            reminder = item["data"]
            events.append(
                ApprovalTimelineEvent(
                    id=f"reminder-{reminder.id}",
                    event_type="reminder",
                    event_type_cn="催办",
                    operator=reminder.reminder_by,
                    operator_id=reminder.reminder_by_id,
                    level=reminder.level,
                    reason=reminder.message,
                    created_at=reminder.created_at,
                )
            )

    if approval.status in (ApprovalStatus.APPROVED, ApprovalStatus.REJECTED):
        status_cn = "审批完成" if approval.status == ApprovalStatus.APPROVED else "审批驳回"
        events.append(
            ApprovalTimelineEvent(
                id=f"complete-{approval.id}",
                event_type="complete",
                event_type_cn=status_cn,
                operator=approval.approver or "系统",
                opinion=approval.approval_opinion,
                status=approval.status.value,
                created_at=approval.updated_at,
            )
        )
    elif approval.status == ApprovalStatus.WITHDRAWN:
        events.append(
            ApprovalTimelineEvent(
                id=f"withdraw-{approval.id}",
                event_type="withdraw",
                event_type_cn="审批撤回",
                operator=approval.applicant,
                reason=approval.approval_opinion,
                status=approval.status.value,
                created_at=approval.updated_at,
            )
        )

    return events


def _save_node_conditions(
    db: Session,
    node_id: int,
    conditions_data: list,
) -> None:
    for cond_data in conditions_data:
        condition = ApprovalChainCondition(
            chain_node_id=node_id,
            target_level=cond_data.target_level,
            logic=cond_data.logic,
            priority=cond_data.priority,
        )
        db.add(condition)
        db.flush()
        for rule_data in cond_data.rules:
            rule = ApprovalChainConditionRule(
                condition_id=condition.id,
                field=rule_data.field,
                operator=rule_data.operator,
                value=rule_data.value,
            )
            db.add(rule)


def _build_temp_nodes_for_cycle_check(data_nodes: list) -> list:
    temp_nodes = []
    for idx, node_data in enumerate(data_nodes):
        level = idx + 1
        temp_conditions = []
        for cond_data in (node_data.conditions or []):
            temp_rules = [
                ApprovalChainConditionRule(
                    id=i,
                    condition_id=0,
                    field=r.field,
                    operator=r.operator,
                    value=r.value,
                )
                for i, r in enumerate(cond_data.rules or [])
            ]
            temp_conditions.append(
                ApprovalChainCondition(
                    id=len(temp_conditions),
                    chain_node_id=0,
                    target_level=cond_data.target_level,
                    logic=cond_data.logic,
                    priority=cond_data.priority,
                    rules=temp_rules,
                )
            )
        temp_node = ApprovalChainNode(
            id=idx,
            chain_id=0,
            level=level,
            node_type=getattr(node_data, "node_type", ChainNodeType.APPROVAL),
            parallel_group_id=getattr(node_data, "parallel_group_id", None),
            branch_id=getattr(node_data, "branch_id", None),
            branch_index=getattr(node_data, "branch_index", None),
            mode=node_data.mode,
            timeout_minutes=node_data.timeout_minutes,
            default_next_level=getattr(node_data, "default_next_level", None),
            escalation_strategy=getattr(node_data, "escalation_strategy", TimeoutEscalationStrategy.ESCALATE_TO_LEVEL),
            escalation_target_level=getattr(node_data, "escalation_target_level", None),
            conditions=temp_conditions,
        )
        temp_nodes.append(temp_node)
    return temp_nodes


def create_approval_chain(db: Session, data: ApprovalChainCreate) -> ApprovalChain:
    temp_nodes = _build_temp_nodes_for_cycle_check(data.nodes)
    cycle = detect_cycle(temp_nodes)
    if cycle:
        cycle_str = " → ".join(f"L{l}" for l in cycle)
        raise HTTPException(
            status_code=400,
            detail=f"审批链存在环路：{cycle_str}，请检查条件分支配置",
        )

    parallel_errors = detect_parallel_deadlock(temp_nodes)
    if parallel_errors:
        raise HTTPException(
            status_code=400,
            detail=f"并行网关配置错误：{'; '.join(parallel_errors)}",
        )

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
        node_type = getattr(node_data, "node_type", ChainNodeType.APPROVAL)
        is_gateway = node_type in (ChainNodeType.PARALLEL_START, ChainNodeType.PARALLEL_END)

        if not is_gateway and not node_data.approvers:
            raise HTTPException(status_code=400, detail=f"第{idx + 1}级节点至少需要指定一个审批人")
        if not is_gateway and node_data.mode == ApprovalMode.SINGLE and len(node_data.approvers) != 1:
            raise HTTPException(status_code=400, detail=f"单人审批模式（第{idx + 1}级）只能指定一个审批人")

        node = ApprovalChainNode(
            chain_id=chain.id,
            level=idx + 1,
            node_type=node_type,
            parallel_group_id=getattr(node_data, "parallel_group_id", None),
            branch_id=getattr(node_data, "branch_id", None),
            branch_index=getattr(node_data, "branch_index", None),
            mode=node_data.mode,
            timeout_minutes=node_data.timeout_minutes,
            default_next_level=node_data.default_next_level,
            escalation_strategy=node_data.escalation_strategy,
            escalation_target_level=node_data.escalation_target_level,
        )
        db.add(node)
        db.flush()

        if not is_gateway:
            for approver_data in node_data.approvers:
                approver = ApprovalChainNodeApprover(
                    chain_node_id=node.id,
                    approver_role=approver_data.approver_role,
                    approver_name=approver_data.approver_name,
                )
                db.add(approver)

        if node_data.conditions:
            _save_node_conditions(db, node.id, node_data.conditions)

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
        .options(
            joinedload(ApprovalChainNode.approvers),
            joinedload(ApprovalChainNode.conditions).joinedload(ApprovalChainCondition.rules),
        )
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
        temp_nodes = _build_temp_nodes_for_cycle_check(data.nodes)
        cycle = detect_cycle(temp_nodes)
        if cycle:
            cycle_str = " → ".join(f"L{l}" for l in cycle)
            raise HTTPException(
                status_code=400,
                detail=f"审批链存在环路：{cycle_str}，请检查条件分支配置",
            )

        parallel_errors = detect_parallel_deadlock(temp_nodes)
        if parallel_errors:
            raise HTTPException(
                status_code=400,
                detail=f"并行网关配置错误：{'; '.join(parallel_errors)}",
            )

        existing_node_ids = [
            n.id for n in db.query(ApprovalChainNode.id)
            .filter(ApprovalChainNode.chain_id == chain_id).all()
        ]
        if existing_node_ids:
            condition_ids = [
                c.id for c in db.query(ApprovalChainCondition.id)
                .filter(ApprovalChainCondition.chain_node_id.in_(existing_node_ids)).all()
            ]
            if condition_ids:
                db.query(ApprovalChainConditionRule).filter(
                    ApprovalChainConditionRule.condition_id.in_(condition_ids)
                ).delete(synchronize_session=False)
            db.query(ApprovalChainCondition).filter(
                ApprovalChainCondition.chain_node_id.in_(existing_node_ids)
            ).delete(synchronize_session=False)
            db.query(ApprovalChainNodeApprover).filter(
                ApprovalChainNodeApprover.chain_node_id.in_(existing_node_ids)
            ).delete(synchronize_session=False)
            db.query(ApprovalChainNode).filter(
                ApprovalChainNode.chain_id == chain_id
            ).delete()

        for idx, node_data in enumerate(data.nodes):
            node_type = getattr(node_data, "node_type", ChainNodeType.APPROVAL)
            is_gateway = node_type in (ChainNodeType.PARALLEL_START, ChainNodeType.PARALLEL_END)

            if not is_gateway and not node_data.approvers:
                raise HTTPException(status_code=400, detail=f"第{idx + 1}级节点至少需要指定一个审批人")
            if not is_gateway and node_data.mode == ApprovalMode.SINGLE and len(node_data.approvers) != 1:
                raise HTTPException(status_code=400, detail=f"单人审批模式（第{idx + 1}级）只能指定一个审批人")

            node = ApprovalChainNode(
                chain_id=chain_id,
                level=idx + 1,
                node_type=node_type,
                parallel_group_id=getattr(node_data, "parallel_group_id", None),
                branch_id=getattr(node_data, "branch_id", None),
                branch_index=getattr(node_data, "branch_index", None),
                mode=node_data.mode,
                timeout_minutes=node_data.timeout_minutes,
                default_next_level=node_data.default_next_level,
                escalation_strategy=node_data.escalation_strategy,
                escalation_target_level=node_data.escalation_target_level,
            )
            db.add(node)
            db.flush()

            if not is_gateway:
                for approver_data in node_data.approvers:
                    approver = ApprovalChainNodeApprover(
                        chain_node_id=node.id,
                        approver_role=approver_data.approver_role,
                        approver_name=approver_data.approver_name,
                    )
                    db.add(approver)

            if node_data.conditions:
                _save_node_conditions(db, node.id, node_data.conditions)

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

    existing_node_ids = [
        n.id for n in db.query(ApprovalChainNode.id)
        .filter(ApprovalChainNode.chain_id == chain_id).all()
    ]
    if existing_node_ids:
        condition_ids = [
            c.id for c in db.query(ApprovalChainCondition.id)
            .filter(ApprovalChainCondition.chain_node_id.in_(existing_node_ids)).all()
        ]
        if condition_ids:
            db.query(ApprovalChainConditionRule).filter(
                ApprovalChainConditionRule.condition_id.in_(condition_ids)
            ).delete(synchronize_session=False)
        db.query(ApprovalChainCondition).filter(
            ApprovalChainCondition.chain_node_id.in_(existing_node_ids)
        ).delete(synchronize_session=False)
        db.query(ApprovalChainNodeApprover).filter(
            ApprovalChainNodeApprover.chain_node_id.in_(existing_node_ids)
        ).delete(synchronize_session=False)
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


def acquire_task_lock(db: Session, task_name: str, lock_ttl_seconds: int = 300, owner: str = "default") -> bool:
    from sqlalchemy import text

    now = datetime.now()
    expires_at = now + timedelta(seconds=lock_ttl_seconds)

    result = db.execute(
        text(
            "INSERT INTO task_locks (task_name, locked_by, locked_at, expires_at, created_at, updated_at) "
            "VALUES (:task_name, :owner, :now, :expires, :now, :now) "
            "ON CONFLICT(task_name) DO UPDATE SET "
            "  locked_by = :owner, locked_at = :now, expires_at = :expires, updated_at = :now "
            "WHERE locked_at IS NULL OR expires_at < :now"
        ),
        {"task_name": task_name, "owner": owner, "now": now, "expires": expires_at},
    )
    db.flush()

    return result.rowcount == 1


def release_task_lock(db: Session, task_name: str) -> None:
    from sqlalchemy import text

    db.execute(
        text(
            "UPDATE task_locks SET locked_by = NULL, locked_at = NULL, expires_at = NULL "
            "WHERE task_name = :task_name"
        ),
        {"task_name": task_name},
    )
    db.flush()


def check_and_process_timeouts(db: Session) -> list[dict]:
    import os

    worker_id = os.getpid()
    lock_name = "approval_timeout_check"
    lock_ttl = 120

    if not acquire_task_lock(db, lock_name, lock_ttl_seconds=lock_ttl, owner=f"worker-{worker_id}"):
        logger.debug("[超时检查] 未获取到任务锁，跳过本次执行")
        return []

    try:
        return _process_timeouts_internal(db)
    finally:
        release_task_lock(db, lock_name)


def _process_timeouts_internal(db: Session) -> list[dict]:
    from sqlalchemy import text, or_
    import uuid

    worker_id = f"timeout-{uuid.uuid4().hex[:8]}"
    now = datetime.now()
    stale_threshold = now - timedelta(minutes=10)
    timed_out_records = (
        db.query(ApprovalNodeRecord)
        .filter(
            ApprovalNodeRecord.status == ApprovalStatus.PENDING,
            or_(
                ApprovalNodeRecord.transfer_status.is_(None),
                ApprovalNodeRecord.transfer_status != TransferStatus.TRANSFERRED,
            ),
            ApprovalNodeRecord.timeout_at.isnot(None),
            ApprovalNodeRecord.timeout_at < now,
        )
        .all()
    )

    grouped: dict[tuple[int, int, str | None], list[ApprovalNodeRecord]] = {}
    for record in timed_out_records:
        key = (record.approval_id, record.level, record.branch_id)
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(record)

    processed = []
    processed_keys: set[tuple[int, int, str | None]] = set()

    for (approval_id, level, branch_id), records in grouped.items():
        if (approval_id, level, branch_id) in processed_keys:
            continue

        approval = db.query(Approval).filter(Approval.id == approval_id).first()
        if not approval or approval.status != ApprovalStatus.PENDING:
            continue

        is_parallel_branch = branch_id is not None
        if not is_parallel_branch and approval.current_level != level:
            continue

        asset = db.query(Asset).filter(Asset.id == approval.asset_id).first()
        if not asset:
            continue

        node_mode = _get_node_mode(db, records[0].chain_node_id)

        pending_records = [r for r in records if r.status == ApprovalStatus.PENDING and _is_active_record(r)]
        if not pending_records:
            continue

        if is_parallel_branch:
            lock_sql = (
                "UPDATE approvals SET processing_lock = :lock_id, processing_locked_at = :now "
                "WHERE id = :approval_id AND status = :status "
                "AND (processing_lock IS NULL OR processing_locked_at < :stale_threshold)"
            )
            lock_params = {
                "lock_id": worker_id,
                "now": now,
                "approval_id": approval_id,
                "status": ApprovalStatus.PENDING.name,
                "stale_threshold": stale_threshold,
            }
        else:
            lock_sql = (
                "UPDATE approvals SET processing_lock = :lock_id, processing_locked_at = :now "
                "WHERE id = :approval_id AND status = :status AND current_level = :level "
                "AND (processing_lock IS NULL OR processing_locked_at < :stale_threshold)"
            )
            lock_params = {
                "lock_id": worker_id,
                "now": now,
                "approval_id": approval_id,
                "status": ApprovalStatus.PENDING.name,
                "level": level,
                "stale_threshold": stale_threshold,
            }

        lock_result = db.execute(text(lock_sql), lock_params)
        db.flush()

        if lock_result.rowcount != 1:
            logger.debug(f"[超时处理] 审批单#{approval_id}第{level}级已被其他实例锁定，跳过")
            continue

        db.refresh(approval)

        savepoint = db.begin_nested()
        result_entry = None
        try:
            escalation_strategy, escalation_target = _get_node_escalation_config(
                db, pending_records[0].chain_node_id
            )

            if escalation_strategy == TimeoutEscalationStrategy.SKIP_NODE:
                for record in pending_records:
                    record.status = ApprovalStatus.ESCALATED
                    record.is_escalated = True
                    record.acted_at = now
                    record.opinion = "审批超时，跳过当前节点"
                all_level_records = (
                    db.query(ApprovalNodeRecord)
                    .filter(
                        ApprovalNodeRecord.approval_id == approval.id,
                        ApprovalNodeRecord.level == level,
                    )
                    .all()
                )
                for r in all_level_records:
                    if r.status == ApprovalStatus.PENDING and _is_active_record(r):
                        if r not in pending_records:
                            r.status = ApprovalStatus.ESCALATED
                            r.is_escalated = True
                            r.acted_at = now
                            r.opinion = "会签节点跳过：其他审批人超时"
            elif escalation_strategy == TimeoutEscalationStrategy.AUTO_REJECT:
                for record in pending_records:
                    record.status = ApprovalStatus.REJECTED
                    record.is_escalated = True
                    record.acted_at = now
                    record.opinion = "审批超时，策略配置为自动驳回"
            else:
                for record in pending_records:
                    record.status = ApprovalStatus.ESCALATED
                    record.is_escalated = True
                    record.acted_at = now
                    record.opinion = "审批超时，自动升级"

            if is_parallel_branch:
                if escalation_strategy == TimeoutEscalationStrategy.AUTO_REJECT:
                    all_records = (
                        db.query(ApprovalNodeRecord)
                        .filter(ApprovalNodeRecord.approval_id == approval.id)
                        .all()
                    )
                    if check_branch_all_rejected(all_records, branch_id):
                        approval.status = ApprovalStatus.REJECTED
                        approval.approver = "系统"
                        approval.approval_opinion = "并行分支超时全部驳回"
                        asset.status = approval.previous_status
                        remaining_pending = [
                            r for r in all_records
                            if r.status == ApprovalStatus.PENDING and _is_active_record(r)
                        ]
                        for r in remaining_pending:
                            r.status = ApprovalStatus.REJECTED
                        log = AssetLog(
                            asset_id=asset.id,
                            action="审批超时驳回",
                            operator="系统",
                            operator_id=None,
                            detail=f"并行分支{branch_id}超时全部驳回，审批单驳回",
                        )
                        db.add(log)
                        db.execute(
                            text(
                                "UPDATE approvals SET processing_lock = NULL, processing_locked_at = NULL "
                                "WHERE id = :approval_id AND processing_lock = :lock_id"
                            ),
                            {"approval_id": approval_id, "lock_id": worker_id},
                        )
                        db.flush()
                        savepoint.commit()
                        result_entry = {
                            "approval_id": approval.id,
                            "level": level,
                            "branch_id": branch_id,
                            "action": "rejected",
                            "reason": "并行分支超时全部驳回",
                        }
                        if result_entry is not None:
                            processed.append(result_entry)
                        processed_keys.add((approval_id, level, branch_id))
                        continue

                next_level = _get_next_record_level_in_branch(db, approval.id, level, branch_id)
                cycle_reason = None
            else:
                next_level, cycle_reason = _escalation_resolve_target_level(
                    db, approval, pending_records[0].chain_node_level, escalation_strategy, escalation_target
                )

            if next_level is not None:
                if is_parallel_branch:
                    _set_branch_level_timeout(db, approval.id, next_level, branch_id, "check_and_process_timeouts_branch")
                else:
                    approval.current_level = next_level
                    _set_next_level_timeout(db, approval, "check_and_process_timeouts")

                mode_desc = {
                    ApprovalMode.SINGLE: "单人审批",
                    ApprovalMode.ALL_SIGN: "会签",
                    ApprovalMode.OR_SIGN: "或签",
                }.get(node_mode, "审批")

                strategy_desc = {
                    TimeoutEscalationStrategy.ESCALATE_TO_LEVEL: "升级",
                    TimeoutEscalationStrategy.SKIP_NODE: "跳过",
                    TimeoutEscalationStrategy.AUTO_REJECT: "驳回",
                }.get(escalation_strategy, "升级")

                branch_info = f"，分支{records[0].branch_index + 1}" if is_parallel_branch and records[0].branch_index is not None else ""

                log = AssetLog(
                    asset_id=asset.id,
                    action="审批超时升级" if escalation_strategy != TimeoutEscalationStrategy.SKIP_NODE else "审批超时跳过",
                    operator="系统",
                    operator_id=None,
                    detail=f"第{level}/{approval.total_levels}级{mode_desc}{branch_info}超时，{strategy_desc}到第{next_level}级（{strategy_desc}{len(pending_records)}人）",
                )
                db.add(log)

                op_log = OperationLog(
                    module="approval",
                    action="timeout_escalate" if escalation_strategy != TimeoutEscalationStrategy.SKIP_NODE else "timeout_skip",
                    operator="系统",
                    detail=f"审批单#{approval.id}第{level}级{mode_desc}{branch_info}超时，{strategy_desc}到第{next_level}级（{strategy_desc}{len(pending_records)}人）",
                )
                db.add(op_log)

                result_entry = {
                    "approval_id": approval.id,
                    "level": level,
                    "branch_id": branch_id,
                    "action": "escalated" if escalation_strategy == TimeoutEscalationStrategy.ESCALATE_TO_LEVEL else "skipped",
                    "new_level": next_level,
                    "escalated_count": len(pending_records),
                    "strategy": escalation_strategy.value,
                }
            else:
                if is_parallel_branch:
                    db.execute(
                        text(
                            "UPDATE approvals SET processing_lock = NULL, processing_locked_at = NULL "
                            "WHERE id = :approval_id AND processing_lock = :lock_id"
                        ),
                        {"approval_id": approval_id, "lock_id": worker_id},
                    )
                    db.flush()
                    savepoint.commit()
                    if result_entry is not None:
                        processed.append(result_entry)
                    processed_keys.add((approval_id, level, branch_id))
                    continue

                if cycle_reason:
                    final_reason = cycle_reason
                elif escalation_strategy == TimeoutEscalationStrategy.AUTO_REJECT:
                    final_reason = "超时策略配置为自动驳回"
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
                        ApprovalNodeRecord.level > level,
                        ApprovalNodeRecord.status == ApprovalStatus.PENDING,
                        _not_transferred_sql(),
                    )
                    .all()
                )
                for r in remaining_records:
                    r.status = ApprovalStatus.REJECTED

                log_detail = (
                    f"（第{level}/{approval.total_levels}级）{final_reason}，资产状态恢复为{approval.previous_status.value}"
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

                result_entry = {
                    "approval_id": approval.id,
                    "level": level,
                    "action": "rejected",
                    "reason": final_reason,
                }

            db.execute(
                text(
                    "UPDATE approvals SET processing_lock = NULL, processing_locked_at = NULL "
                    "WHERE id = :approval_id AND processing_lock = :lock_id"
                ),
                {"approval_id": approval_id, "lock_id": worker_id},
            )
            db.flush()
            savepoint.commit()
        except Exception:
            savepoint.rollback()
            logger.exception(f"[超时处理] 审批单#{approval_id}第{level}级处理异常，保留processing_lock等待重试")
            continue

        if result_entry is not None:
            processed.append(result_entry)
        processed_keys.add((approval_id, level, branch_id))

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


def get_user_notifications(
    db: Session,
    user_id: int,
    is_read: bool | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Notification], int, int]:
    query = db.query(Notification).filter(Notification.user_id == user_id)

    if is_read is not None:
        query = query.filter(Notification.is_read == is_read)

    total = query.count()
    unread_count = db.query(Notification).filter(
        Notification.user_id == user_id,
        Notification.is_read == False,
    ).count()

    items = (
        query.order_by(Notification.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return items, total, unread_count


def get_notification(db: Session, notification_id: int, user_id: int) -> Notification:
    notification = db.query(Notification).filter(Notification.id == notification_id).first()
    if not notification:
        raise HTTPException(status_code=404, detail="通知不存在")
    if notification.user_id != user_id:
        from app.auth import is_admin_user
        user = db.query(User).filter(User.id == user_id).first()
        if not user or not is_admin_user(db, user_id):
            raise HTTPException(status_code=403, detail="无权查看此通知")
    return notification


def mark_notification_read(db: Session, notification_id: int, user_id: int) -> Notification:
    notification = get_notification(db, notification_id, user_id)
    if not notification.is_read:
        notification.is_read = True
        notification.read_at = datetime.now()
        db.commit()
        db.refresh(notification)
    return notification


def mark_all_notifications_read(db: Session, user_id: int) -> int:
    notifications = (
        db.query(Notification)
        .filter(
            Notification.user_id == user_id,
            Notification.is_read == False,
        )
        .all()
    )
    count = len(notifications)
    now = datetime.now()
    for n in notifications:
        n.is_read = True
        n.read_at = now
    if count > 0:
        db.commit()
    return count
