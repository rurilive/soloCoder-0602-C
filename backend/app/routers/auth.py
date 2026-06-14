from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import (
    create_access_token,
    get_password_hash,
    verify_password,
    get_current_user,
    get_user_roles,
    get_user_permission_list,
)
from app.models import User, UserRole, Role
from app.schemas import (
    Token,
    LoginRequest,
    RegisterRequest,
    PasswordChange,
    UserProfileResponse,
    RoleBrief,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _build_profile_response(db: Session, user: User) -> UserProfileResponse:
    user_data = {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "real_name": user.real_name,
        "is_active": user.is_active,
        "avatar": user.avatar,
        "department": user.department,
        "position": user.position,
        "phone": user.phone,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }
    roles = get_user_roles(db, user.id)
    permissions = get_user_permission_list(db, user.id)
    response = UserProfileResponse(**user_data)
    response.roles = [RoleBrief.model_validate(r) for r in roles]
    response.permissions = permissions
    return response


@router.post("/register", response_model=UserProfileResponse, status_code=status.HTTP_201_CREATED)
def register(user_data: RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.username == user_data.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="用户名已存在")

    existing = db.query(User).filter(User.email == user_data.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="邮箱已被注册")

    user = User(
        username=user_data.username,
        email=user_data.email,
        real_name=user_data.real_name,
        hashed_password=get_password_hash(user_data.password),
        department=user_data.department,
        position=user_data.position,
        phone=user_data.phone,
    )
    db.add(user)
    db.flush()

    employee_role = db.query(Role).filter(Role.code == "employee").first()
    if employee_role:
        db.add(UserRole(user_id=user.id, role_id=employee_role.id))

    db.commit()
    db.refresh(user)

    return _build_profile_response(db, user)


@router.post("/login", response_model=Token)
def login(user_data: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == user_data.username).first()

    if not user or not verify_password(user_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账号已被禁用，请联系管理员",
        )

    access_token = create_access_token(data={"sub": str(user.id)})
    return Token(access_token=access_token)


@router.get("/me", response_model=UserProfileResponse)
def get_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _build_profile_response(db, current_user)


@router.post("/change-password", status_code=status.HTTP_200_OK)
def change_password(
    data: PasswordChange,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(data.old_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="原密码错误",
        )
    current_user.hashed_password = get_password_hash(data.new_password)
    db.commit()
    return {"message": "密码修改成功"}
