import os
from datetime import datetime, timedelta, timezone
from typing import Callable

import bcrypt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, Role, UserRole, RolePermission, Permission
from app.schemas import TokenData

SECRET_KEY = os.environ.get("ASSET_JWT_SECRET")
if not SECRET_KEY:
    raise RuntimeError(
        "环境变量 ASSET_JWT_SECRET 未设置！请在启动服务前设置该变量，例如：\n"
        "  export ASSET_JWT_SECRET='your-strong-secret-key-here'"
    )
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7

MUST_CHANGE_PASSWORD_WHITELIST = {
    "/api/health",
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/change-password",
}

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def _get_user_permissions(db: Session, user_id: int) -> set[str]:
    role_ids = [
        ur.role_id for ur in db.query(UserRole).filter(UserRole.user_id == user_id).all()
    ]
    if not role_ids:
        return set()

    if db.query(Role).filter(Role.id.in_(role_ids), Role.code == "super_admin").first():
        return {"*"}

    perm_ids = [
        rp.permission_id
        for rp in db.query(RolePermission).filter(RolePermission.role_id.in_(role_ids)).all()
    ]
    if not perm_ids:
        return set()

    perms = db.query(Permission).filter(Permission.id.in_(perm_ids)).all()
    return {p.code for p in perms}


def get_user_roles(db: Session, user_id: int) -> list[Role]:
    user_roles = db.query(UserRole).filter(UserRole.user_id == user_id).all()
    role_ids = [ur.role_id for ur in user_roles]
    if not role_ids:
        return []
    return db.query(Role).filter(Role.id.in_(role_ids)).all()


def get_user_role_codes(db: Session, user_id: int) -> list[str]:
    roles = get_user_roles(db, user_id)
    return [r.code for r in roles]


def get_current_user(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无法验证凭据，请重新登录",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if token is None:
        raise credentials_exception
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id_str: str | None = payload.get("sub")
        if user_id_str is None:
            raise credentials_exception
        token_data = TokenData(user_id=int(user_id_str))
    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.id == token_data.user_id).first()
    if user is None:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账号已被禁用，请联系管理员",
        )
    if user.must_change_password and request.url.path not in MUST_CHANGE_PASSWORD_WHITELIST:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="首次登录必须修改密码，请先调用 /api/auth/change-password 接口修改密码",
        )
    return user


def get_optional_current_user(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User | None:
    """可选用户认证。

    返回值说明:
      - None: 未提供 token 或 token 无效（签名错误、过期、解析失败等）
      - User: 认证成功且用户处于可使用状态
      - HTTPException(403): token 有效但用户必须修改密码

    调用方应通过 `if user is None` 判断未登录场景，通过捕获 403 异常处理需改密场景。
    """
    if token is None:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id_str: str | None = payload.get("sub")
        if user_id_str is None:
            return None
        token_data = TokenData(user_id=int(user_id_str))
    except JWTError:
        return None

    user = db.query(User).filter(User.id == token_data.user_id).first()
    if user is None or not user.is_active:
        return None
    if user.must_change_password and request.url.path not in MUST_CHANGE_PASSWORD_WHITELIST:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="首次登录必须修改密码，请先调用 /api/auth/change-password 接口修改密码",
        )
    return user


def require_permissions(*permissions: str, require_all: bool = True) -> Callable:
    def dependency(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        user_perms = _get_user_permissions(db, current_user.id)
        if "*" in user_perms:
            return current_user

        if require_all:
            missing = [p for p in permissions if p not in user_perms]
            if missing:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"权限不足，需要权限: {', '.join(missing)}",
                )
        else:
            has_any = any(p in user_perms for p in permissions)
            if not has_any:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"权限不足，需要以下任一权限: {', '.join(permissions)}",
                )
        return current_user

    return dependency


def require_role(*role_codes: str) -> Callable:
    def dependency(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        user_role_codes = get_user_role_codes(db, current_user.id)
        if "super_admin" in user_role_codes:
            return current_user

        has_role = any(r in user_role_codes for r in role_codes)
        if not has_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"权限不足，需要角色: {', '.join(role_codes)}",
            )
        return current_user

    return dependency


def check_user_permission(db: Session, user_id: int, permission: str) -> bool:
    user_perms = _get_user_permissions(db, user_id)
    return "*" in user_perms or permission in user_perms


def get_user_permission_list(db: Session, user_id: int) -> list[str]:
    return sorted(list(_get_user_permissions(db, user_id)))


def build_user_response(db: Session, user: User):
    from app.schemas import UserResponse, RoleBrief

    user_data = {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "real_name": user.real_name,
        "is_active": user.is_active,
        "must_change_password": user.must_change_password,
        "avatar": user.avatar,
        "department": user.department,
        "position": user.position,
        "phone": user.phone,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }
    roles = get_user_roles(db, user.id)
    permissions = get_user_permission_list(db, user.id)
    response = UserResponse(**user_data)
    response.roles = [RoleBrief.model_validate(r) for r in roles]
    response.permissions = permissions
    return response


def is_admin_user(db: Session, user_id: int) -> bool:
    role_codes = get_user_role_codes(db, user_id)
    return "super_admin" in role_codes or "asset_admin" in role_codes


def is_dept_manager(db: Session, user_id: int) -> bool:
    role_codes = get_user_role_codes(db, user_id)
    return "dept_manager" in role_codes


def get_user_dept(db: Session, user_id: int) -> str | None:
    user = db.query(User).filter(User.id == user_id).first()
    return user.department if user else None


def get_dept_user_names(db: Session, dept_name: str | None) -> list[str]:
    if not dept_name:
        return []
    users = db.query(User).filter(User.department == dept_name, User.is_active == True).all()
    names = []
    for u in users:
        if u.real_name:
            names.append(u.real_name)
        names.append(u.username)
    return list(set(names))


def get_user_display_name(user: User) -> str:
    return user.real_name or user.username


def apply_asset_data_scope(query, db: Session, user_id: int):
    if is_admin_user(db, user_id):
        return query

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return query.filter(False)

    user_name = get_user_display_name(user)

    if is_dept_manager(db, user_id):
        dept_users = get_dept_user_names(db, user.department)
        from app.models import Asset
        from sqlalchemy import or_
        query = query.filter(
            or_(
                Asset.assignee.in_(dept_users),
                Asset.assignee == None,
            )
        )
    else:
        from app.models import Asset
        query = query.filter(Asset.assignee == user_name)

    return query


def apply_approval_data_scope(query, db: Session, user_id: int):
    if is_admin_user(db, user_id):
        return query

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return query.filter(False)

    user_name = get_user_display_name(user)
    user_role_codes = set(get_user_role_codes(db, user_id))

    from app.models import Approval, ApprovalNodeRecord, ApprovalStatus
    from sqlalchemy import or_

    if is_dept_manager(db, user_id):
        dept_users = get_dept_user_names(db, user.department)
        query = query.filter(
            or_(
                Approval.applicant.in_(dept_users),
                Approval.id.in_(
                    db.query(ApprovalNodeRecord.approval_id)
                    .filter(
                        ApprovalNodeRecord.status == ApprovalStatus.PENDING,
                        ApprovalNodeRecord.approver_role.in_(list(user_role_codes)),
                    )
                    .distinct()
                    .subquery()
                ),
            )
        )
    else:
        query = query.filter(
            or_(
                Approval.applicant == user_name,
                Approval.id.in_(
                    db.query(ApprovalNodeRecord.approval_id)
                    .filter(
                        ApprovalNodeRecord.status == ApprovalStatus.PENDING,
                        ApprovalNodeRecord.approver_role.in_(list(user_role_codes)),
                    )
                    .distinct()
                    .subquery()
                ),
            )
        )

    return query


def log_operation(
    db: Session,
    module: str,
    action: str,
    user: User | None = None,
    target_type: str | None = None,
    target_id: int | None = None,
    detail: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    status: str = "success",
    error_message: str | None = None,
):
    from app.crud import create_operation_log

    operator = user.real_name or user.username if user else "system"
    operator_id = user.id if user else None

    return create_operation_log(
        db=db,
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
