import enum
from datetime import datetime
from sqlalchemy import String, Enum, DateTime, Text, Integer
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class AssetStatus(str, enum.Enum):
    IN_STOCK = "in_stock"
    ALLOCATED = "allocated"
    RETURNED = "returned"
    SCRAPPED = "scrapped"
    PENDING_APPROVAL = "pending_approval"


class ApprovalType(str, enum.Enum):
    ALLOCATE = "allocate"
    SCRAP = "scrap"


class ApprovalStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class AssetCategory(str, enum.Enum):
    COMPUTER = "computer"
    MONITOR = "monitor"
    PRINTER = "printer"
    NETWORK_DEVICE = "network_device"
    PERIPHERAL = "peripheral"
    OTHER = "other"


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_tag: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    category: Mapped[AssetCategory] = mapped_column(Enum(AssetCategory), nullable=False)
    brand: Mapped[str] = mapped_column(String(128), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    serial_number: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    status: Mapped[AssetStatus] = mapped_column(Enum(AssetStatus), default=AssetStatus.IN_STOCK, nullable=False)
    assignee: Mapped[str | None] = mapped_column(String(128), nullable=True)
    location: Mapped[str | None] = mapped_column(String(256), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    purchase_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    purchase_price: Mapped[float | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    approval_type: Mapped[ApprovalType] = mapped_column(Enum(ApprovalType), nullable=False)
    status: Mapped[ApprovalStatus] = mapped_column(Enum(ApprovalStatus), default=ApprovalStatus.PENDING, nullable=False)
    applicant: Mapped[str] = mapped_column(String(128), nullable=False)
    assignee: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    approver: Mapped[str | None] = mapped_column(String(128), nullable=True)
    approval_opinion: Mapped[str | None] = mapped_column(Text, nullable=True)
    previous_status: Mapped[AssetStatus] = mapped_column(Enum(AssetStatus), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)


class AssetLog(Base):
    __tablename__ = "asset_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    operator: Mapped[str] = mapped_column(String(128), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)


class ImportLog(Base):
    __tablename__ = "import_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False)
    file_name: Mapped[str] = mapped_column(String(256), nullable=False)
    operator: Mapped[str] = mapped_column(String(128), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
