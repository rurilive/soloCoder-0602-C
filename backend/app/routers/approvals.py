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
    ApprovalChainCreate,
    ApprovalChainUpdate,
    ApprovalChainResponse,
    ApprovalChainListResponse,
    ChainNodesReorder,
)
from app import crud

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


@router.get("/chains/list", response_model=ApprovalChainListResponse)
def list_approval_chains(
    approval_type: ApprovalType | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
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
def get_approval_chain(chain_id: int, db: Session = Depends(get_db)):
    chain = crud.get_approval_chain(db, chain_id)
    nodes = crud.get_chain_nodes(db, chain.id)
    result = ApprovalChainResponse.model_validate(chain)
    result.nodes = nodes
    return result


@router.post("/chains", response_model=ApprovalChainResponse, status_code=201)
def create_approval_chain(data: ApprovalChainCreate, db: Session = Depends(get_db)):
    chain = crud.create_approval_chain(db, data)
    nodes = crud.get_chain_nodes(db, chain.id)
    result = ApprovalChainResponse.model_validate(chain)
    result.nodes = nodes
    return result


@router.put("/chains/{chain_id}/reorder", response_model=ApprovalChainResponse)
def reorder_chain_nodes(chain_id: int, data: ChainNodesReorder, db: Session = Depends(get_db)):
    chain = crud.reorder_chain_nodes(db, chain_id, data)
    nodes = crud.get_chain_nodes(db, chain.id)
    result = ApprovalChainResponse.model_validate(chain)
    result.nodes = nodes
    return result


@router.put("/chains/{chain_id}", response_model=ApprovalChainResponse)
def update_approval_chain(chain_id: int, data: ApprovalChainUpdate, db: Session = Depends(get_db)):
    chain = crud.update_approval_chain(db, chain_id, data)
    nodes = crud.get_chain_nodes(db, chain.id)
    result = ApprovalChainResponse.model_validate(chain)
    result.nodes = nodes
    return result


@router.delete("/chains/{chain_id}", status_code=204)
def delete_approval_chain(chain_id: int, db: Session = Depends(get_db)):
    crud.delete_approval_chain(db, chain_id)


@router.post("/asset/{asset_id}", response_model=ApprovalResponse)
def create_approval(asset_id: int, data: ApprovalCreate, db: Session = Depends(get_db)):
    return crud.create_approval(db, asset_id, data)


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
        node_records = crud.get_approval_node_records(db, approval.id)
        approval_data = ApprovalDetailResponse.model_validate(approval)
        approval_data.asset_name = asset.name
        approval_data.asset_tag = asset.asset_tag
        approval_data.purchase_price = asset.purchase_price
        approval_data.node_records = node_records
        result.append(approval_data)
    return ApprovalListResponse(total=total, items=result)


@router.get("/{approval_id}", response_model=ApprovalDetailResponse)
def get_approval(approval_id: int, db: Session = Depends(get_db)):
    approval = crud.get_approval(db, approval_id)
    asset = crud.get_asset(db, approval.asset_id)
    node_records = crud.get_approval_node_records(db, approval.id)
    result = ApprovalDetailResponse.model_validate(approval)
    result.asset_name = asset.name
    result.asset_tag = asset.asset_tag
    result.purchase_price = asset.purchase_price
    result.node_records = node_records
    return result


@router.post("/{approval_id}/approve", response_model=ApprovalResponse)
def approve_approval(approval_id: int, data: ApprovalAction, db: Session = Depends(get_db)):
    return crud.approve_approval(db, approval_id, data)


@router.post("/{approval_id}/reject", response_model=ApprovalResponse)
def reject_approval(approval_id: int, data: ApprovalAction, db: Session = Depends(get_db)):
    return crud.reject_approval(db, approval_id, data)
