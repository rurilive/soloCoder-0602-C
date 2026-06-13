from datetime import datetime
from pydantic import BaseModel, Field
from app.models import AssetStatus, AssetCategory, ApprovalType, ApprovalStatus


class AssetCreate(BaseModel):
    name: str = Field(..., max_length=256)
    category: AssetCategory
    brand: str = Field(..., max_length=128)
    model: str = Field(..., max_length=128)
    serial_number: str = Field(..., max_length=128)
    assignee: str | None = None
    location: str | None = None
    notes: str | None = None
    purchase_date: str | None = None
    purchase_price: float | None = None


class AssetUpdate(BaseModel):
    name: str | None = Field(None, max_length=256)
    category: AssetCategory | None = None
    brand: str | None = Field(None, max_length=128)
    model: str | None = Field(None, max_length=128)
    serial_number: str | None = Field(None, max_length=128)
    assignee: str | None = None
    location: str | None = None
    notes: str | None = None
    purchase_date: str | None = None
    purchase_price: float | None = None


class AssetAllocate(BaseModel):
    assignee: str = Field(..., max_length=128)


class AssetReturn(BaseModel):
    notes: str | None = None


class AssetScrap(BaseModel):
    notes: str | None = None


class AssetResponse(BaseModel):
    id: int
    asset_tag: str
    name: str
    category: AssetCategory
    brand: str
    model: str
    serial_number: str
    status: AssetStatus
    assignee: str | None
    location: str | None
    notes: str | None
    purchase_date: str | None
    purchase_price: float | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AssetLogResponse(BaseModel):
    id: int
    asset_id: int
    action: str
    operator: str
    detail: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AssetListResponse(BaseModel):
    total: int
    items: list[AssetResponse]


class ImportErrorItem(BaseModel):
    row: int
    reason: str


class ImportResultResponse(BaseModel):
    success: bool
    total_rows: int
    success_count: int = 0
    errors: list[ImportErrorItem] = []


class ImportLogResponse(BaseModel):
    id: int
    total_rows: int
    success_count: int
    file_name: str
    operator: str
    detail: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ApprovalCreate(BaseModel):
    approval_type: ApprovalType
    applicant: str = Field(..., max_length=128)
    assignee: str | None = Field(None, max_length=128)
    reason: str | None = None


class ApprovalAction(BaseModel):
    opinion: str | None = None


class ApprovalResponse(BaseModel):
    id: int
    asset_id: int
    approval_type: ApprovalType
    status: ApprovalStatus
    applicant: str
    assignee: str | None
    reason: str | None
    approver: str | None
    approval_opinion: str | None
    previous_status: AssetStatus
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ApprovalNodeRecordResponse(BaseModel):
    id: int
    approval_id: int
    chain_node_id: int
    level: int
    approver_role: str
    approver_name: str
    status: ApprovalStatus
    opinion: str | None
    acted_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ApprovalDetailResponse(ApprovalResponse):
    asset_name: str | None = None
    asset_tag: str | None = None
    purchase_price: float | None = None
    node_records: list[ApprovalNodeRecordResponse] = []


class ApprovalListResponse(BaseModel):
    total: int
    items: list[ApprovalDetailResponse]


class ChainNodeCreate(BaseModel):
    approver_role: str = Field(..., max_length=64)
    approver_name: str = Field(..., max_length=128)


class ChainNodeUpdate(BaseModel):
    approver_role: str | None = Field(None, max_length=64)
    approver_name: str | None = Field(None, max_length=128)


class ChainNodeResponse(BaseModel):
    id: int
    chain_id: int
    level: int
    approver_role: str
    approver_name: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ApprovalChainCreate(BaseModel):
    name: str = Field(..., max_length=128)
    approval_type: ApprovalType
    min_price: float | None = None
    max_price: float | None = None
    is_default: bool = False
    nodes: list[ChainNodeCreate]


class ApprovalChainUpdate(BaseModel):
    name: str | None = Field(None, max_length=128)
    min_price: float | None = None
    max_price: float | None = None
    is_default: bool | None = None
    nodes: list[ChainNodeCreate] | None = None


class ApprovalChainResponse(BaseModel):
    id: int
    name: str
    approval_type: ApprovalType
    min_price: float | None
    max_price: float | None
    is_default: bool
    nodes: list[ChainNodeResponse] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ApprovalChainListResponse(BaseModel):
    total: int
    items: list[ApprovalChainResponse]


class ChainNodesReorder(BaseModel):
    node_ids: list[int]
