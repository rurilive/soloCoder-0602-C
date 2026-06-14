import enum
from datetime import datetime
from sqlalchemy import String, Enum, DateTime, Text, Integer, ForeignKey, Boolean, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
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
    approver_role: Mapped[str] = mapped_column(String(64), nullable=False)
    approver_name: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)


class ApprovalNodeRecord(Base):
    __tablename__ = "approval_node_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    approval_id: Mapped[int] = mapped_column(Integer, ForeignKey("approvals.id"), nullable=False, index=True)
    chain_node_id: Mapped[int] = mapped_column(Integer, ForeignKey("approval_chain_nodes.id"), nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    approver_role: Mapped[str] = mapped_column(String(64), nullable=False)
    approver_name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[ApprovalStatus] = mapped_column(Enum(ApprovalStatus), default=ApprovalStatus.PENDING, nullable=False)
    opinion: Mapped[str | None] = mapped_column(Text, nullable=True)
    acted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)


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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)


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

    {"code": "chain:view", "name": "查看审批链", "module": "chain", "description": "查看审批链配置"},
    {"code": "chain:manage", "name": "管理审批链", "module": "chain", "description": "创建、修改、删除审批链"},

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
            "chain:view", "chain:manage",
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
