from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import (
    get_current_user,
    get_password_hash,
    require_permissions,
    build_user_response,
)
from app.models import User, Role, UserRole
from app.schemas import (
    UserCreate,
    UserUpdate,
    UserAssignRoles,
    UserResponse,
    UserListResponse,
    UserProfileResponse,
)

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("", response_model=UserListResponse)
def list_users(
    keyword: str | None = None,
    is_active: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(require_permissions("user:view")),
    db: Session = Depends(get_db),
):
    query = db.query(User)
    if keyword:
        like = f"%{keyword}%"
        query = query.filter(
            (User.username.like(like))
            | (User.real_name.like(like))
            | (User.email.like(like))
            | (User.department.like(like))
        )
    if is_active is not None:
        query = query.filter(User.is_active == is_active)

    total = query.count()
    items = (
        query.order_by(User.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    result = [build_user_response(db, u) for u in items]
    return UserListResponse(total=total, items=result)


@router.get("/{user_id}", response_model=UserProfileResponse)
def get_user(
    user_id: int,
    current_user: User = Depends(require_permissions("user:view")),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return build_user_response(db, user)


@router.post("", response_model=UserProfileResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    data: UserCreate,
    current_user: User = Depends(require_permissions("user:create")),
    db: Session = Depends(get_db),
):
    existing = db.query(User).filter(User.username == data.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="用户名已存在")
    existing = db.query(User).filter(User.email == data.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="邮箱已被注册")

    user = User(
        username=data.username,
        email=data.email,
        real_name=data.real_name,
        hashed_password=get_password_hash(data.password),
        department=data.department,
        position=data.position,
        phone=data.phone,
    )
    db.add(user)
    db.flush()

    role_ids = data.role_ids
    if not role_ids:
        employee_role = db.query(Role).filter(Role.code == "employee").first()
        if employee_role:
            role_ids = [employee_role.id]

    for rid in role_ids:
        role = db.query(Role).filter(Role.id == rid).first()
        if role:
            db.add(UserRole(user_id=user.id, role_id=rid))

    db.commit()
    db.refresh(user)
    return build_user_response(db, user)


@router.put("/{user_id}", response_model=UserProfileResponse)
def update_user(
    user_id: int,
    data: UserUpdate,
    current_user: User = Depends(require_permissions("user:edit")),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    update_data = data.model_dump(exclude_unset=True)
    if "email" in update_data and update_data["email"] != user.email:
        existing = db.query(User).filter(User.email == update_data["email"], User.id != user_id).first()
        if existing:
            raise HTTPException(status_code=400, detail="邮箱已被使用")

    for key, value in update_data.items():
        setattr(user, key, value)

    db.commit()
    db.refresh(user)
    return build_user_response(db, user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    current_user: User = Depends(require_permissions("user:delete")),
    db: Session = Depends(get_db),
):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="不能删除自己的账号")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    super_admin_role = db.query(Role).filter(Role.code == "super_admin").first()
    if super_admin_role:
        user_role_ids = [ur.role_id for ur in db.query(UserRole).filter(UserRole.user_id == user_id).all()]
        if super_admin_role.id in user_role_ids:
            admin_count = (
                db.query(UserRole)
                .filter(UserRole.role_id == super_admin_role.id)
                .count()
            )
            if admin_count <= 1:
                raise HTTPException(status_code=400, detail="不能删除最后一个超级管理员")

    db.query(UserRole).filter(UserRole.user_id == user_id).delete()
    db.delete(user)
    db.commit()


@router.put("/{user_id}/roles", response_model=UserProfileResponse)
def assign_roles(
    user_id: int,
    data: UserAssignRoles,
    current_user: User = Depends(require_permissions("user:assign_role")),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    db.query(UserRole).filter(UserRole.user_id == user_id).delete()

    for rid in data.role_ids:
        role = db.query(Role).filter(Role.id == rid).first()
        if role:
            db.add(UserRole(user_id=user_id, role_id=rid))

    db.commit()
    db.refresh(user)
    return build_user_response(db, user)
