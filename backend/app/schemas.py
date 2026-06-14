from datetime import datetime
from pydantic import BaseModel, Field, EmailStr, field_validator
from app.models import (
    AssetStatus, AssetCategory, ApprovalType, ApprovalStatus, NotificationType, ApprovalMode,
    ConditionOperator, ConditionField, ConditionLogic,
)


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
    purchase_department: str | None = None


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
    purchase_department: str | None = None


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
    purchase_department: str | None
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


class OperationLogResponse(BaseModel):
    id: int
    module: str
    action: str
    operator: str
    operator_id: int | None
    target_type: str | None
    target_id: int | None
    detail: str | None
    ip_address: str | None
    status: str
    error_message: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class OperationLogListResponse(BaseModel):
    total: int
    items: list[OperationLogResponse]


class ApprovalCreate(BaseModel):
    approval_type: ApprovalType
    applicant: str = Field(..., max_length=128)
    assignee: str | None = Field(None, max_length=128)
    reason: str | None = None


class ApprovalAction(BaseModel):
    opinion: str | None = None


class ApprovalWithdrawRequest(BaseModel):
    reason: str | None = Field(None, max_length=500)


class ApprovalRemindRequest(BaseModel):
    message: str | None = Field(None, max_length=500)


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
    current_level: int
    total_levels: int
    chain_id: int | None
    reminder_count: int = 0
    last_reminder_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ApprovalNodeRecordResponse(BaseModel):
    id: int
    approval_id: int
    chain_node_id: int
    chain_node_approver_id: int | None = None
    level: int
    approver_role: str
    approver_name: str
    status: ApprovalStatus
    opinion: str | None
    acted_at: datetime | None
    timeout_at: datetime | None = None
    is_escalated: bool = False
    actual_approver: str | None = None
    proxy_source: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ApprovalReminderResponse(BaseModel):
    id: int
    approval_id: int
    level: int
    reminder_by: str
    message: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ApprovalDetailResponse(ApprovalResponse):
    asset_name: str | None = None
    asset_tag: str | None = None
    purchase_price: float | None = None
    node_records: list[ApprovalNodeRecordResponse] = []
    reminders: list[ApprovalReminderResponse] = []


class ApprovalListResponse(BaseModel):
    total: int
    items: list[ApprovalDetailResponse]


class ChainNodeApproverCreate(BaseModel):
    approver_role: str = Field(..., max_length=64)
    approver_name: str = Field(..., max_length=128)


class ChainNodeApproverResponse(BaseModel):
    id: int
    chain_node_id: int
    approver_role: str
    approver_name: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ConditionRuleCreate(BaseModel):
    field: ConditionField
    operator: ConditionOperator
    value: list | dict | float | str | int | None = None


class ConditionRuleResponse(BaseModel):
    id: int
    condition_id: int
    field: ConditionField
    operator: ConditionOperator
    value: list | dict | float | str | int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ConditionCreate(BaseModel):
    target_level: int = Field(..., ge=1)
    logic: ConditionLogic = ConditionLogic.AND
    priority: int = 0
    rules: list[ConditionRuleCreate] = []


class ConditionResponse(BaseModel):
    id: int
    chain_node_id: int
    target_level: int
    logic: ConditionLogic
    priority: int
    rules: list[ConditionRuleResponse] = []
    created_at: datetime

    model_config = {"from_attributes": True}


class ChainNodeCreate(BaseModel):
    mode: ApprovalMode = ApprovalMode.SINGLE
    timeout_minutes: int | None = None
    default_next_level: int | None = Field(None, ge=1)
    approvers: list[ChainNodeApproverCreate]
    conditions: list[ConditionCreate] = []


class ChainNodeUpdate(BaseModel):
    mode: ApprovalMode | None = None
    timeout_minutes: int | None = None
    default_next_level: int | None = Field(None, ge=1)
    approvers: list[ChainNodeApproverCreate] | None = None
    conditions: list[ConditionCreate] | None = None


class ChainNodeResponse(BaseModel):
    id: int
    chain_id: int
    level: int
    mode: ApprovalMode
    timeout_minutes: int | None = None
    default_next_level: int | None = None
    approvers: list[ChainNodeApproverResponse] = []
    conditions: list[ConditionResponse] = []
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


# ==================== Auth Schemas ====================

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    user_id: int | None = None


class LoginRequest(BaseModel):
    username: str = Field(..., max_length=64)
    password: str = Field(..., min_length=1)


class RegisterRequest(BaseModel):
    username: str = Field(..., max_length=64)
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=128)
    real_name: str | None = Field(None, max_length=64)
    department: str | None = Field(None, max_length=128)
    position: str | None = Field(None, max_length=128)
    phone: str | None = Field(None, max_length=32)


class PasswordChange(BaseModel):
    old_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=6, max_length=128)


# ==================== Permission Schemas ====================

class PermissionResponse(BaseModel):
    id: int
    name: str
    code: str
    description: str | None
    module: str
    created_at: datetime

    model_config = {"from_attributes": True}


class PermissionListResponse(BaseModel):
    total: int
    items: list[PermissionResponse]


# ==================== Role Schemas ====================

class RoleCreate(BaseModel):
    name: str = Field(..., max_length=128)
    code: str = Field(..., max_length=64)
    description: str | None = Field(None, max_length=256)
    permission_ids: list[int] = []


class RoleUpdate(BaseModel):
    name: str | None = Field(None, max_length=128)
    description: str | None = Field(None, max_length=256)
    permission_ids: list[int] | None = None


class RoleBrief(BaseModel):
    id: int
    name: str
    code: str
    description: str | None

    model_config = {"from_attributes": True}


class RoleResponse(BaseModel):
    id: int
    name: str
    code: str
    description: str | None
    is_builtin: bool
    permissions: list[PermissionResponse] = []
    created_at: datetime

    model_config = {"from_attributes": True}


class RoleListResponse(BaseModel):
    total: int
    items: list[RoleResponse]


# ==================== User Schemas ====================

class UserCreate(BaseModel):
    username: str = Field(..., max_length=64)
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=128)
    real_name: str | None = Field(None, max_length=64)
    department: str | None = Field(None, max_length=128)
    position: str | None = Field(None, max_length=128)
    phone: str | None = Field(None, max_length=32)
    role_ids: list[int] = []


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    real_name: str | None = Field(None, max_length=64)
    department: str | None = Field(None, max_length=128)
    position: str | None = Field(None, max_length=128)
    phone: str | None = Field(None, max_length=32)
    is_active: bool | None = None
    avatar: str | None = Field(None, max_length=256)


class UserAssignRoles(BaseModel):
    role_ids: list[int]


class UserBrief(BaseModel):
    id: int
    username: str
    real_name: str | None
    avatar: str | None
    department: str | None
    position: str | None

    model_config = {"from_attributes": True}


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    real_name: str | None
    is_active: bool
    must_change_password: bool = False
    avatar: str | None
    department: str | None
    position: str | None
    phone: str | None
    roles: list[RoleBrief] = []
    permissions: list[str] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserListResponse(BaseModel):
    total: int
    items: list[UserResponse]


UserProfileResponse = UserResponse


class ModulePermissions(BaseModel):
    module: str
    permissions: list[PermissionResponse]


class PermissionTreeResponse(BaseModel):
    modules: list[ModulePermissions]


class ApprovalProxyCreate(BaseModel):
    proxy_user_id: int
    start_time: datetime
    end_time: datetime
    reason: str | None = Field(None, max_length=256)


class ApprovalProxyResponse(BaseModel):
    id: int
    principal_user_id: int
    proxy_user_id: int
    principal_name: str | None = None
    proxy_name: str | None = None
    start_time: datetime
    end_time: datetime
    is_active: bool
    reason: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ApprovalProxyListResponse(BaseModel):
    total: int
    items: list[ApprovalProxyResponse]


class NotificationResponse(BaseModel):
    id: int
    user_id: int
    type: NotificationType
    title: str
    content: str
    related_id: int | None = None
    related_type: str | None = None
    is_read: bool
    created_at: datetime
    read_at: datetime | None = None

    model_config = {"from_attributes": True}


class NotificationListResponse(BaseModel):
    total: int
    items: list[NotificationResponse]
    unread_count: int = 0
