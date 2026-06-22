import enum
from datetime import datetime
from sqlalchemy import String, Enum, DateTime, Text, Integer, ForeignKey, Boolean, UniqueConstraint, JSON, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class ConditionOperator(str, enum.Enum):
    EQ = "eq"
    NE = "ne"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    IN = "in"
    NOT_IN = "not_in"
    BETWEEN = "between"
    CONTAINS = "contains"


class ConditionField(str, enum.Enum):
    PRICE = "price"
    CATEGORY = "category"
    APPLICANT_DEPARTMENT = "applicant_department"


class ConditionLogic(str, enum.Enum):
    AND = "and"
    OR = "or"


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
    ESCALATED = "escalated"
    WITHDRAWN = "withdrawn"


class ApprovalMode(str, enum.Enum):
    SINGLE = "single"
    ALL_SIGN = "all_sign"
    OR_SIGN = "or_sign"


class ChainNodeType(str, enum.Enum):
    APPROVAL = "approval"
    PARALLEL_START = "parallel_start"
    PARALLEL_END = "parallel_end"
    SUB_PROCESS = "sub_process"


class TimeoutEscalationStrategy(str, enum.Enum):
    ESCALATE_TO_LEVEL = "escalate_to_level"
    AUTO_REJECT = "auto_reject"
    SKIP_NODE = "skip_node"


class EscalationTrigger(str, enum.Enum):
    TIMEOUT = "timeout"
    REMINDER = "reminder"


class ApprovalNodeActionType(str, enum.Enum):
    ADD_SIGNER = "add_signer"
    TRANSFER = "transfer"


class ApprovalRecordType(str, enum.Enum):
    NORMAL = "normal"
    ADDED_SIGNER = "added_signer"
    TRANSFERRED = "transferred"


class TransferStatus(str, enum.Enum):
    PENDING = "pending"
    TRANSFERRED = "transferred"


class NotificationType(str, enum.Enum):
    APPROVAL_REMINDER = "approval_reminder"
    APPROVAL_SUBMITTED = "approval_submitted"
    APPROVAL_APPROVED = "approval_approved"
    APPROVAL_REJECTED = "approval_rejected"
    APPROVAL_WITHDRAWN = "approval_withdrawn"
    APPROVAL_ESCALATED = "approval_escalated"
    SYSTEM = "system"


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
    purchase_department: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)


class ApprovalChain(Base):
    __tablename__ = "approval_chains"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    approval_type: Mapped[ApprovalType] = mapped_column(Enum(ApprovalType), nullable=False)
    min_price: Mapped[float | None] = mapped_column(nullable=True)
    max_price: Mapped[float | None] = mapped_column(nullable=True)
    is_default: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)


class ApprovalChainNode(Base):
    __tablename__ = "approval_chain_nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chain_id: Mapped[int] = mapped_column(Integer, ForeignKey("approval_chains.id"), nullable=False, index=True)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    node_type: Mapped[ChainNodeType] = mapped_column(Enum(ChainNodeType), default=ChainNodeType.APPROVAL, nullable=False)
    parallel_group_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    branch_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    branch_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mode: Mapped[ApprovalMode] = mapped_column(Enum(ApprovalMode), default=ApprovalMode.SINGLE, nullable=False)
    timeout_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    default_next_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    escalation_strategy: Mapped[TimeoutEscalationStrategy] = mapped_column(
        Enum(TimeoutEscalationStrategy),
        default=TimeoutEscalationStrategy.ESCALATE_TO_LEVEL,
        nullable=False,
    )
    escalation_target_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sub_process_chain_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("approval_chains.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)

    approvers: Mapped[list["ApprovalChainNodeApprover"]] = relationship(
        "ApprovalChainNodeApprover",
        back_populates="chain_node",
        cascade="all, delete-orphan",
    )

    conditions: Mapped[list["ApprovalChainCondition"]] = relationship(
        "ApprovalChainCondition",
        cascade="all, delete-orphan",
    )


class ApprovalChainNodeApprover(Base):
    __tablename__ = "approval_chain_node_approvers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chain_node_id: Mapped[int] = mapped_column(Integer, ForeignKey("approval_chain_nodes.id"), nullable=False, index=True)
    approver_role: Mapped[str] = mapped_column(String(64), nullable=False)
    approver_name: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)

    chain_node: Mapped["ApprovalChainNode"] = relationship("ApprovalChainNode", back_populates="approvers")


class ApprovalChainCondition(Base):
    __tablename__ = "approval_chain_conditions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chain_node_id: Mapped[int] = mapped_column(Integer, ForeignKey("approval_chain_nodes.id"), nullable=False, index=True)
    target_level: Mapped[int] = mapped_column(Integer, nullable=False)
    logic: Mapped[ConditionLogic] = mapped_column(Enum(ConditionLogic), default=ConditionLogic.AND, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)

    rules: Mapped[list["ApprovalChainConditionRule"]] = relationship(
        "ApprovalChainConditionRule",
        back_populates="condition",
        cascade="all, delete-orphan",
    )


class ApprovalChainConditionRule(Base):
    __tablename__ = "approval_chain_condition_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    condition_id: Mapped[int] = mapped_column(Integer, ForeignKey("approval_chain_conditions.id"), nullable=False, index=True)
    field: Mapped[ConditionField] = mapped_column(Enum(ConditionField), nullable=False)
    operator: Mapped[ConditionOperator] = mapped_column(Enum(ConditionOperator), nullable=False)
    value: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)

    condition: Mapped["ApprovalChainCondition"] = relationship("ApprovalChainCondition", back_populates="rules")


class ApprovalNodeRecord(Base):
    __tablename__ = "approval_node_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    approval_id: Mapped[int] = mapped_column(Integer, ForeignKey("approvals.id"), nullable=False, index=True)
    chain_node_id: Mapped[int] = mapped_column(Integer, ForeignKey("approval_chain_nodes.id"), nullable=False)
    chain_node_approver_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("approval_chain_node_approvers.id"), nullable=True)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    chain_node_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    parallel_group_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    branch_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    branch_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    branch_complete: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    approver_role: Mapped[str] = mapped_column(String(64), nullable=False)
    approver_name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[ApprovalStatus] = mapped_column(Enum(ApprovalStatus), default=ApprovalStatus.PENDING, nullable=False)
    opinion: Mapped[str | None] = mapped_column(Text, nullable=True)
    acted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    timeout_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_escalated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    escalation_strategy: Mapped[TimeoutEscalationStrategy | None] = mapped_column(Enum(TimeoutEscalationStrategy), nullable=True)
    escalation_trigger: Mapped[EscalationTrigger | None] = mapped_column(Enum(EscalationTrigger), nullable=True)
    actual_approver: Mapped[str | None] = mapped_column(String(128), nullable=True)
    proxy_source: Mapped[str | None] = mapped_column(String(128), nullable=True)
    record_type: Mapped[ApprovalRecordType] = mapped_column(Enum(ApprovalRecordType), default=ApprovalRecordType.NORMAL, nullable=False)
    is_added_signer: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    added_signer_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    added_signer_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    transfer_status: Mapped[TransferStatus | None] = mapped_column(Enum(TransferStatus), nullable=True)
    transferred_from: Mapped[str | None] = mapped_column(String(128), nullable=True)
    transferred_to: Mapped[str | None] = mapped_column(String(128), nullable=True)
    transfer_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_record_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("approval_node_records.id"), nullable=True)
    sub_process_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("approvals.id"), nullable=True)
    sub_process_nesting_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    parent_record_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("approval_node_records.id"), nullable=True)
    node_type: Mapped[ChainNodeType | None] = mapped_column(Enum(ChainNodeType), nullable=True)
    sub_process_chain_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("approval_chains.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)

    source_record: Mapped["ApprovalNodeRecord | None"] = relationship("ApprovalNodeRecord", remote_side=[id], foreign_keys=[source_record_id])
    parent_record: Mapped["ApprovalNodeRecord | None"] = relationship("ApprovalNodeRecord", remote_side=[id], foreign_keys=[parent_record_id])
    sub_process_records: Mapped[list["ApprovalNodeRecord"]] = relationship(
        "ApprovalNodeRecord",
        back_populates="parent_record",
        foreign_keys="ApprovalNodeRecord.parent_record_id",
    )
    sub_process_approval: Mapped["Approval | None"] = relationship(
        "Approval",
        foreign_keys=[sub_process_id],
        primaryjoin="ApprovalNodeRecord.sub_process_id == Approval.id",
    )


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(Integer, ForeignKey("assets.id"), nullable=False, index=True)
    approval_type: Mapped[ApprovalType] = mapped_column(Enum(ApprovalType), nullable=False)
    status: Mapped[ApprovalStatus] = mapped_column(Enum(ApprovalStatus), default=ApprovalStatus.PENDING, nullable=False)
    applicant: Mapped[str] = mapped_column(String(128), nullable=False)
    assignee: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    approver: Mapped[str | None] = mapped_column(String(128), nullable=True)
    approval_opinion: Mapped[str | None] = mapped_column(Text, nullable=True)
    previous_status: Mapped[AssetStatus] = mapped_column(Enum(AssetStatus), nullable=False)
    current_level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    total_levels: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    chain_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("approval_chains.id"), nullable=True)
    reminder_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_reminder_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    processing_lock: Mapped[str | None] = mapped_column(String(128), nullable=True, default=None)
    processing_locked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)


class ApprovalProxy(Base):
    __tablename__ = "approval_proxies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    principal_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    proxy_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)


class ApprovalReminder(Base):
    __tablename__ = "approval_reminders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    approval_id: Mapped[int] = mapped_column(Integer, ForeignKey("approvals.id"), nullable=False, index=True)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    reminder_by: Mapped[str] = mapped_column(String(128), nullable=False)
    reminder_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)


class ApprovalNodeAction(Base):
    __tablename__ = "approval_node_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    approval_id: Mapped[int] = mapped_column(Integer, ForeignKey("approvals.id"), nullable=False, index=True)
    node_record_id: Mapped[int] = mapped_column(Integer, ForeignKey("approval_node_records.id"), nullable=False, index=True)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    action_type: Mapped[ApprovalNodeActionType] = mapped_column(Enum(ApprovalNodeActionType), nullable=False)
    operator: Mapped[str] = mapped_column(String(128), nullable=False)
    operator_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    target_user: Mapped[str] = mapped_column(String(128), nullable=False)
    target_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    target_role: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    type: Mapped[NotificationType] = mapped_column(Enum(NotificationType), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    related_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    related_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AssetLog(Base):
    __tablename__ = "asset_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    operator: Mapped[str] = mapped_column(String(128), nullable=False)
    operator_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)


class ImportLog(Base):
    __tablename__ = "import_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False)
    file_name: Mapped[str] = mapped_column(String(256), nullable=False)
    operator: Mapped[str] = mapped_column(String(128), nullable=False)
    operator_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)


class OperationLog(Base):
    __tablename__ = "operation_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    module: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    operator: Mapped[str] = mapped_column(String(128), nullable=False)
    operator_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    target_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="success")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False, index=True)


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(256), nullable=True)
    module: Mapped[str] = mapped_column(String(64), nullable=False, default="general")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)

    roles: Mapped[list["RolePermission"]] = relationship("RolePermission", back_populates="permission", cascade="all, delete-orphan")


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(256), nullable=True)
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)

    permissions: Mapped[list["RolePermission"]] = relationship("RolePermission", back_populates="role", cascade="all, delete-orphan")
    users: Mapped[list["UserRole"]] = relationship("UserRole", back_populates="role", cascade="all, delete-orphan")


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (
        UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    role_id: Mapped[int] = mapped_column(Integer, ForeignKey("roles.id"), nullable=False, index=True)
    permission_id: Mapped[int] = mapped_column(Integer, ForeignKey("permissions.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)

    role: Mapped["Role"] = relationship("Role", back_populates="permissions")
    permission: Mapped["Permission"] = relationship("Permission", back_populates="roles")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    real_name: Mapped[str] = mapped_column(String(64), nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(256), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    avatar: Mapped[str | None] = mapped_column(String(256), nullable=True)
    department: Mapped[str | None] = mapped_column(String(128), nullable=True)
    position: Mapped[str | None] = mapped_column(String(128), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)

    roles: Mapped[list["UserRole"]] = relationship("UserRole", back_populates="user", cascade="all, delete-orphan")


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (
        UniqueConstraint("user_id", "role_id", name="uq_user_role"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    role_id: Mapped[int] = mapped_column(Integer, ForeignKey("roles.id"), nullable=False, index=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="roles")
    role: Mapped["Role"] = relationship("Role", back_populates="users")


class TaskLock(Base):
    __tablename__ = "task_locks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    locked_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)


DEFAULT_PERMISSIONS: list[dict] = [
    {"code": "asset:view", "name": "查看资产", "module": "asset", "description": "查看资产列表和详情"},
    {"code": "asset:create", "name": "创建资产", "module": "asset", "description": "新增资产入库"},
    {"code": "asset:edit", "name": "编辑资产", "module": "asset", "description": "修改资产信息"},
    {"code": "asset:delete", "name": "删除资产", "module": "asset", "description": "删除资产记录"},
    {"code": "asset:allocate", "name": "资产领用", "module": "asset", "description": "申请领用资产"},
    {"code": "asset:return", "name": "资产归还", "module": "asset", "description": "归还已领用资产"},
    {"code": "asset:scrap", "name": "资产报废", "module": "asset", "description": "申请报废资产"},
    {"code": "asset:import", "name": "批量导入", "module": "asset", "description": "批量导入资产数据"},
    {"code": "asset:export", "name": "批量导出", "module": "asset", "description": "批量导出资产数据"},

    {"code": "approval:view", "name": "查看审批", "module": "approval", "description": "查看审批单列表和详情"},
    {"code": "approval:submit", "name": "提交审批", "module": "approval", "description": "提交审批申请"},
    {"code": "approval:approve", "name": "审批通过", "module": "approval", "description": "通过待审批单据"},
    {"code": "approval:reject", "name": "审批驳回", "module": "approval", "description": "驳回待审批单据"},
    {"code": "approval:add_signer", "name": "会签加签", "module": "approval", "description": "在会签节点追加临时审批人"},
    {"code": "approval:transfer", "name": "转审", "module": "approval", "description": "将待审批单据转交给他人审批"},

    {"code": "chain:view", "name": "查看审批链", "module": "chain", "description": "查看审批链配置"},
    {"code": "chain:manage", "name": "管理审批链", "module": "chain", "description": "创建、修改、删除审批链"},

    {"code": "proxy:manage", "name": "管理审批代理", "module": "proxy", "description": "设置和取消审批代理"},
    {"code": "proxy:view", "name": "查看审批代理", "module": "proxy", "description": "查看审批代理设置"},

    {"code": "user:view", "name": "查看用户", "module": "user", "description": "查看用户列表和详情"},
    {"code": "user:create", "name": "创建用户", "module": "user", "description": "新增用户账号"},
    {"code": "user:edit", "name": "编辑用户", "module": "user", "description": "修改用户信息"},
    {"code": "user:delete", "name": "删除用户", "module": "user", "description": "删除用户账号"},
    {"code": "user:assign_role", "name": "分配角色", "module": "user", "description": "为用户分配角色"},

    {"code": "role:view", "name": "查看角色", "module": "role", "description": "查看角色列表和详情"},
    {"code": "role:create", "name": "创建角色", "module": "role", "description": "新增角色"},
    {"code": "role:edit", "name": "编辑角色", "module": "role", "description": "修改角色信息和权限"},
    {"code": "role:delete", "name": "删除角色", "module": "role", "description": "删除角色"},

    {"code": "log:view", "name": "查看日志", "module": "log", "description": "查看操作日志"},
]

DEFAULT_ROLES: list[dict] = [
    {
        "code": "super_admin",
        "name": "超级管理员",
        "description": "系统超级管理员，拥有所有权限",
        "is_builtin": True,
        "permissions": ["all"],
    },
    {
        "code": "asset_admin",
        "name": "资产管理员",
        "description": "管理资产全生命周期，包括入库、编辑、报废审批等",
        "is_builtin": True,
        "permissions": [
            "asset:view", "asset:create", "asset:edit", "asset:delete",
            "asset:allocate", "asset:return", "asset:scrap",
            "asset:import", "asset:export",
            "approval:view", "approval:submit", "approval:approve", "approval:reject",
            "approval:add_signer", "approval:transfer",
            "chain:view", "chain:manage",
            "proxy:manage", "proxy:view",
            "log:view",
        ],
    },
    {
        "code": "dept_manager",
        "name": "部门经理",
        "description": "部门经理，可审批本部门资产领用",
        "is_builtin": True,
        "permissions": [
            "asset:view",
            "approval:view", "approval:approve", "approval:reject",
            "approval:add_signer", "approval:transfer",
            "proxy:manage", "proxy:view",
        ],
    },
    {
        "code": "finance_manager",
        "name": "财务经理",
        "description": "财务经理，审批资产报废和高价值资产领用",
        "is_builtin": True,
        "permissions": [
            "asset:view", "asset:export",
            "approval:view", "approval:approve", "approval:reject",
            "approval:add_signer", "approval:transfer",
            "proxy:manage", "proxy:view",
            "log:view",
        ],
    },
    {
        "code": "employee",
        "name": "普通员工",
        "description": "普通员工，可查看资产和申请领用",
        "is_builtin": True,
        "permissions": [
            "asset:view",
            "asset:allocate", "asset:return",
            "approval:view", "approval:submit",
        ],
    },
]

SUPER_ADMIN_USER: dict = {
    "username": "admin",
    "email": "admin@example.com",
    "real_name": "系统管理员",
    "password": "admin123",
    "department": "IT部门",
    "position": "系统管理员",
}
