from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth import get_current_user, require_permissions, log_operation
from app.models import ApprovalStatus, ApprovalType, User
from app.schemas import (
    ApprovalCreate,
    ApprovalAction,
    ApprovalResponse,
    ApprovalDetailResponse,
    ApprovalListResponse,
    ApprovalChainCreate,
    ApprovalChainUpdate,
    ApprovalChainResponse,
    ApprovalChainListResponse,
    ChainNodesReorder,
    ApprovalProxyCreate,
    ApprovalProxyResponse,
    ApprovalProxyListResponse,
    ApprovalWithdrawRequest,
    ApprovalRemindRequest,
)
from app import crud

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


@router.get("/chains/list", response_model=ApprovalChainListResponse)
def list_approval_chains(
    approval_type: ApprovalType | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("chain:view")),
):
    items, total = crud.get_approval_chains(db, approval_type, page, page_size)
    result = []
    for chain in items:
        nodes = crud.get_chain_nodes(db, chain.id)
        chain_data = ApprovalChainResponse.model_validate(chain)
        chain_data.nodes = nodes
        result.append(chain_data)
    return ApprovalChainListResponse(total=total, items=result)


@router.get("/chains/{chain_id}", response_model=ApprovalChainResponse)
def get_approval_chain(
    chain_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("chain:view")),
):
    chain = crud.get_approval_chain(db, chain_id)
    nodes = crud.get_chain_nodes(db, chain.id)
    result = ApprovalChainResponse.model_validate(chain)
    result.nodes = nodes
    return result


@router.post("/chains", response_model=ApprovalChainResponse, status_code=201)
def create_approval_chain(
    data: ApprovalChainCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("chain:manage")),
):
    chain = crud.create_approval_chain(db, data)
    nodes = crud.get_chain_nodes(db, chain.id)
    result = ApprovalChainResponse.model_validate(chain)
    result.nodes = nodes
    return result


@router.put("/chains/{chain_id}/reorder", response_model=ApprovalChainResponse)
def reorder_chain_nodes(
    chain_id: int,
    data: ChainNodesReorder,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("chain:manage")),
):
    chain = crud.reorder_chain_nodes(db, chain_id, data)
    nodes = crud.get_chain_nodes(db, chain.id)
    result = ApprovalChainResponse.model_validate(chain)
    result.nodes = nodes
    return result


@router.put("/chains/{chain_id}", response_model=ApprovalChainResponse)
def update_approval_chain(
    chain_id: int,
    data: ApprovalChainUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("chain:manage")),
):
    chain = crud.update_approval_chain(db, chain_id, data)
    nodes = crud.get_chain_nodes(db, chain.id)
    result = ApprovalChainResponse.model_validate(chain)
    result.nodes = nodes
    return result


@router.delete("/chains/{chain_id}", status_code=204)
def delete_approval_chain(
    chain_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("chain:manage")),
):
    crud.delete_approval_chain(db, chain_id)


@router.post("/timeout/check")
def check_timeout(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("approval:approve")),
):
    processed = crud.check_and_process_timeouts(db)
    expired_proxies = crud.expire_outdated_proxies(db)
    return {
        "timeout_processed": processed,
        "expired_proxies": expired_proxies,
    }


@router.post("/proxies", response_model=ApprovalProxyResponse, status_code=201)
def create_proxy(
    request: Request,
    data: ApprovalProxyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("proxy:manage")),
):
    from app.auth import get_user_display_name
    proxy = crud.create_approval_proxy(db, data, current_user)
    result = ApprovalProxyResponse.model_validate(proxy)
    principal = db.query(User).filter(User.id == proxy.principal_user_id).first()
    proxy_user = db.query(User).filter(User.id == proxy.proxy_user_id).first()
    if principal:
        result.principal_name = get_user_display_name(principal)
    if proxy_user:
        result.proxy_name = get_user_display_name(proxy_user)
    log_operation(
        db,
        module="proxy",
        action="create",
        user=current_user,
        target_type="approval_proxy",
        target_id=proxy.id,
        detail=f"设置审批代理: 代理人 {result.proxy_name}, 时间 {data.start_time} ~ {data.end_time}",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return result


@router.get("/proxies/list", response_model=ApprovalProxyListResponse)
def list_proxies(
    is_active: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("proxy:view")),
):
    from app.auth import get_user_display_name
    items, total = crud.get_approval_proxies(db, current_user, is_active, page, page_size)
    result = []
    for proxy in items:
        resp = ApprovalProxyResponse.model_validate(proxy)
        principal = db.query(User).filter(User.id == proxy.principal_user_id).first()
        proxy_user = db.query(User).filter(User.id == proxy.proxy_user_id).first()
        if principal:
            resp.principal_name = get_user_display_name(principal)
        if proxy_user:
            resp.proxy_name = get_user_display_name(proxy_user)
        result.append(resp)
    return ApprovalProxyListResponse(total=total, items=result)


@router.delete("/proxies/{proxy_id}", response_model=ApprovalProxyResponse)
def cancel_proxy(
    request: Request,
    proxy_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("proxy:manage")),
):
    from app.auth import get_user_display_name
    proxy = crud.cancel_approval_proxy(db, proxy_id, current_user)
    result = ApprovalProxyResponse.model_validate(proxy)
    principal = db.query(User).filter(User.id == proxy.principal_user_id).first()
    proxy_user = db.query(User).filter(User.id == proxy.proxy_user_id).first()
    if principal:
        result.principal_name = get_user_display_name(principal)
    if proxy_user:
        result.proxy_name = get_user_display_name(proxy_user)
    log_operation(
        db,
        module="proxy",
        action="cancel",
        user=current_user,
        target_type="approval_proxy",
        target_id=proxy.id,
        detail=f"取消审批代理: 代理人 {result.proxy_name}",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return result


@router.post("/asset/{asset_id}", response_model=ApprovalResponse)
def create_approval(
    request: Request,
    asset_id: int,
    data: ApprovalCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("approval:submit")),
):
    approval = crud.create_approval(db, asset_id, data, current_user)
    log_operation(
        db,
        module="approval",
        action="submit",
        user=current_user,
        target_type="approval",
        target_id=approval.id,
        detail=f"提交审批单, 类型: {data.approval_type.value}",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return approval


@router.get("", response_model=ApprovalListResponse)
def list_approvals(
    status: ApprovalStatus | None = None,
    approval_type: ApprovalType | None = None,
    keyword: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("approval:view")),
):
    items, total = crud.get_approvals(db, status, approval_type, keyword, page, page_size, current_user)
    result = []
    for approval in items:
        asset = crud.get_asset(db, approval.asset_id, current_user)
        node_records = crud.get_approval_node_records(db, approval.id)
        approval_data = ApprovalDetailResponse.model_validate(approval)
        approval_data.asset_name = asset.name
        approval_data.asset_tag = asset.asset_tag
        approval_data.purchase_price = asset.purchase_price
        approval_data.node_records = node_records
        result.append(approval_data)
    return ApprovalListResponse(total=total, items=result)


@router.get("/pending/mine", response_model=ApprovalListResponse)
def list_my_pending_approvals(
    status: ApprovalStatus | None = None,
    approval_type: ApprovalType | None = None,
    keyword: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("approval:view")),
):
    items, total = crud.get_my_pending_approvals(
        db, current_user, status, approval_type, keyword, page, page_size
    )
    result = []
    for approval in items:
        asset = crud.get_asset(db, approval.asset_id, current_user)
        node_records = crud.get_approval_node_records(db, approval.id)
        approval_data = ApprovalDetailResponse.model_validate(approval)
        approval_data.asset_name = asset.name
        approval_data.asset_tag = asset.asset_tag
        approval_data.purchase_price = asset.purchase_price
        approval_data.node_records = node_records
        result.append(approval_data)
    return ApprovalListResponse(total=total, items=result)


@router.get("/submitted/mine", response_model=ApprovalListResponse)
def list_my_submitted_approvals(
    status: ApprovalStatus | None = None,
    approval_type: ApprovalType | None = None,
    keyword: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items, total = crud.get_my_submitted_approvals(
        db, current_user, status, approval_type, keyword, page, page_size
    )
    result = []
    for approval in items:
        asset = crud.get_asset(db, approval.asset_id, current_user)
        node_records = crud.get_approval_node_records(db, approval.id)
        approval_data = ApprovalDetailResponse.model_validate(approval)
        approval_data.asset_name = asset.name
        approval_data.asset_tag = asset.asset_tag
        approval_data.purchase_price = asset.purchase_price
        approval_data.node_records = node_records
        result.append(approval_data)
    return ApprovalListResponse(total=total, items=result)


@router.get("/{approval_id}", response_model=ApprovalDetailResponse)
def get_approval(
    approval_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("approval:view")),
):
    approval = crud.get_approval(db, approval_id, current_user)
    asset = crud.get_asset(db, approval.asset_id, current_user)
    node_records = crud.get_approval_node_records(db, approval.id)
    reminders = crud.get_approval_reminders(db, approval.id)
    result = ApprovalDetailResponse.model_validate(approval)
    result.asset_name = asset.name
    result.asset_tag = asset.asset_tag
    result.purchase_price = asset.purchase_price
    result.node_records = node_records
    result.reminders = reminders
    return result


@router.post("/{approval_id}/approve", response_model=ApprovalResponse)
def approve_approval(
    request: Request,
    approval_id: int,
    data: ApprovalAction,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("approval:approve")),
):
    crud.get_approval(db, approval_id, current_user)
    approval = crud.approve_approval(db, approval_id, data, current_user)
    log_operation(
        db,
        module="approval",
        action="approve",
        user=current_user,
        target_type="approval",
        target_id=approval_id,
        detail=f"审批通过, 意见: {data.opinion or '无'}",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return approval


@router.post("/{approval_id}/reject", response_model=ApprovalResponse)
def reject_approval(
    request: Request,
    approval_id: int,
    data: ApprovalAction,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("approval:reject")),
):
    crud.get_approval(db, approval_id, current_user)
    approval = crud.reject_approval(db, approval_id, data, current_user)
    log_operation(
        db,
        module="approval",
        action="reject",
        user=current_user,
        target_type="approval",
        target_id=approval_id,
        detail=f"审批驳回, 意见: {data.opinion or '无'}",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return approval


@router.post("/{approval_id}/withdraw", response_model=ApprovalResponse)
def withdraw_approval(
    request: Request,
    approval_id: int,
    data: ApprovalWithdrawRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    crud.get_approval(db, approval_id, current_user)
    approval = crud.withdraw_approval(db, approval_id, data.reason, current_user)
    log_operation(
        db,
        module="approval",
        action="withdraw",
        user=current_user,
        target_type="approval",
        target_id=approval_id,
        detail=f"撤回审批, 原因: {data.reason or '无'}",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return approval


@router.post("/{approval_id}/remind", response_model=ApprovalResponse)
def remind_approval(
    request: Request,
    approval_id: int,
    data: ApprovalRemindRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    crud.get_approval(db, approval_id, current_user)
    approval = crud.remind_approval(db, approval_id, data.message, current_user)
    log_operation(
        db,
        module="approval",
        action="remind",
        user=current_user,
        target_type="approval",
        target_id=approval_id,
        detail=f"催办审批, 留言: {data.message or '无'}",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return approval
