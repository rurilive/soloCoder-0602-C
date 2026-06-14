from collections import defaultdict
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_current_user, require_permissions
from app.models import (
    User,
    Role,
    Permission,
    RolePermission,
)
from app.schemas import (
    RoleCreate,
    RoleUpdate,
    RoleResponse,
    RoleListResponse,
    PermissionResponse,
    PermissionListResponse,
    PermissionTreeResponse,
    ModulePermissions,
)

router = APIRouter(prefix="/api/permissions", tags=["permissions"])


def _build_role_response(db: Session, role: Role) -> RoleResponse:
    role_data = {
        "id": role.id,
        "name": role.name,
        "code": role.code,
        "description": role.description,
        "is_builtin": role.is_builtin,
        "created_at": role.created_at,
    }
    rp_list = db.query(RolePermission).filter(RolePermission.role_id == role.id).all()
    perm_ids = [rp.permission_id for rp in rp_list]
    perms = db.query(Permission).filter(Permission.id.in_(perm_ids)).all() if perm_ids else []
    response = RoleResponse(**role_data)
    response.permissions = [PermissionResponse.model_validate(p) for p in perms]
    return response


@router.get("/permissions", response_model=PermissionListResponse)
def list_permissions(
    module: str | None = None,
    current_user: User = Depends(require_permissions("role:view")),
    db: Session = Depends(get_db),
):
    query = db.query(Permission)
    if module:
        query = query.filter(Permission.module == module)
    total = query.count()
    items = query.order_by(Permission.module, Permission.id).all()
    return PermissionListResponse(total=total, items=items)


@router.get("/permissions/tree", response_model=PermissionTreeResponse)
def get_permission_tree(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    perms = db.query(Permission).order_by(Permission.module, Permission.id).all()
    grouped: dict[str, list[Permission]] = defaultdict(list)
    for p in perms:
        grouped[p.module].append(p)
    modules = [
        ModulePermissions(module=mod, permissions=list(ps))
        for mod, ps in sorted(grouped.items())
    ]
    return PermissionTreeResponse(modules=modules)


@router.get("/roles", response_model=RoleListResponse)
def list_roles(
    keyword: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    current_user: User = Depends(require_permissions("role:view")),
    db: Session = Depends(get_db),
):
    query = db.query(Role)
    if keyword:
        like = f"%{keyword}%"
        query = query.filter(
            (Role.name.like(like)) | (Role.code.like(like)) | (Role.description.like(like))
        )
    total = query.count()
    items = query.order_by(Role.id.asc()).offset((page - 1) * page_size).limit(page_size).all()
    result = [_build_role_response(db, r) for r in items]
    return RoleListResponse(total=total, items=result)


@router.get("/roles/all", response_model=list[RoleResponse])
def list_all_roles(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    items = db.query(Role).order_by(Role.id.asc()).all()
    return [_build_role_response(db, r) for r in items]


@router.get("/roles/{role_id}", response_model=RoleResponse)
def get_role(
    role_id: int,
    current_user: User = Depends(require_permissions("role:view")),
    db: Session = Depends(get_db),
):
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")
    return _build_role_response(db, role)


@router.post("/roles", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
def create_role(
    data: RoleCreate,
    current_user: User = Depends(require_permissions("role:create")),
    db: Session = Depends(get_db),
):
    existing = db.query(Role).filter(Role.code == data.code).first()
    if existing:
        raise HTTPException(status_code=400, detail="角色代码已存在")
    existing = db.query(Role).filter(Role.name == data.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="角色名称已存在")

    role = Role(
        name=data.name,
        code=data.code,
        description=data.description,
        is_builtin=False,
    )
    db.add(role)
    db.flush()

    for pid in data.permission_ids:
        perm = db.query(Permission).filter(Permission.id == pid).first()
        if perm:
            db.add(RolePermission(role_id=role.id, permission_id=pid))

    db.commit()
    db.refresh(role)
    return _build_role_response(db, role)


@router.put("/roles/{role_id}", response_model=RoleResponse)
def update_role(
    role_id: int,
    data: RoleUpdate,
    current_user: User = Depends(require_permissions("role:edit")),
    db: Session = Depends(get_db),
):
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")

    if data.name is not None and data.name != role.name:
        existing = db.query(Role).filter(Role.name == data.name, Role.id != role_id).first()
        if existing:
            raise HTTPException(status_code=400, detail="角色名称已存在")
        role.name = data.name

    if data.description is not None:
        role.description = data.description

    if data.permission_ids is not None:
        if not (role.is_builtin and role.code == "super_admin"):
            db.query(RolePermission).filter(RolePermission.role_id == role_id).delete()
            for pid in data.permission_ids:
                perm = db.query(Permission).filter(Permission.id == pid).first()
                if perm:
                    db.add(RolePermission(role_id=role.id, permission_id=pid))

    db.commit()
    db.refresh(role)
    return _build_role_response(db, role)


@router.delete("/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_role(
    role_id: int,
    current_user: User = Depends(require_permissions("role:delete")),
    db: Session = Depends(get_db),
):
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")
    if role.is_builtin:
        raise HTTPException(status_code=400, detail="内置角色不可删除")

    from app.models import UserRole
    assigned_count = db.query(UserRole).filter(UserRole.role_id == role_id).count()
    if assigned_count > 0:
        raise HTTPException(status_code=400, detail="该角色下还有用户，不可删除")

    db.query(RolePermission).filter(RolePermission.role_id == role_id).delete()
    db.delete(role)
    db.commit()
