from datetime import datetime
from pydantic import BaseModel, Field
from app.models import AssetStatus, AssetCategory


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
