from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from app.database import engine, Base, SessionLocal
from app.routers import assets as assets_router
from app.routers import approvals as approvals_router
from app.routers import auth as auth_router
from app.routers import users as users_router
from app.routers import permissions as permissions_router
from app.models import (
    Permission,
    Role,
    RolePermission,
    User,
    UserRole,
    DEFAULT_PERMISSIONS,
    DEFAULT_ROLES,
    SUPER_ADMIN_USER,
)
from app.auth import get_password_hash

MUST_CHANGE_PASSWORD_WHITELIST = {
    "/api/health",
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/change-password",
}


async def must_change_password_middleware(request: Request, call_next):
    request.state.is_chpwd_whitelist = (
        request.url.path in MUST_CHANGE_PASSWORD_WHITELIST
    )
    return await call_next(request)


def _init_rbac_data():
    db: Session = SessionLocal()
    try:
        for perm_data in DEFAULT_PERMISSIONS:
            existing = db.query(Permission).filter(Permission.code == perm_data["code"]).first()
            if not existing:
                db.add(Permission(**perm_data))
        db.flush()

        all_perms = {p.code: p.id for p in db.query(Permission).all()}

        for role_data in DEFAULT_ROLES:
            existing = db.query(Role).filter(Role.code == role_data["code"]).first()
            if not existing:
                role = Role(
                    name=role_data["name"],
                    code=role_data["code"],
                    description=role_data["description"],
                    is_builtin=role_data["is_builtin"],
                )
                db.add(role)
                db.flush()

                perm_codes = role_data["permissions"]
                if perm_codes == ["all"]:
                    perm_ids = list(all_perms.values())
                else:
                    perm_ids = [all_perms[c] for c in perm_codes if c in all_perms]

                for pid in perm_ids:
                    db.add(RolePermission(role_id=role.id, permission_id=pid))

        db.flush()

        admin_user = db.query(User).filter(User.username == SUPER_ADMIN_USER["username"]).first()
        if not admin_user:
            user = User(
                username=SUPER_ADMIN_USER["username"],
                email=SUPER_ADMIN_USER["email"],
                real_name=SUPER_ADMIN_USER["real_name"],
                hashed_password=get_password_hash(SUPER_ADMIN_USER["password"]),
                department=SUPER_ADMIN_USER["department"],
                position=SUPER_ADMIN_USER["position"],
                is_active=True,
                must_change_password=True,
            )
            db.add(user)
            db.flush()

            super_admin_role = db.query(Role).filter(Role.code == "super_admin").first()
            if super_admin_role:
                db.add(UserRole(user_id=user.id, role_id=super_admin_role.id))

        db.commit()
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _init_rbac_data()
    yield


app = FastAPI(
    title="企业内部资产管理系统",
    description="管理电脑、显示器等设备，支持入库、领用、归还、报废流程及二维码标签。集成用户认证与RBAC权限体系。",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.middleware("http")(must_change_password_middleware)

app.include_router(auth_router.router)
app.include_router(users_router.router)
app.include_router(permissions_router.router)
app.include_router(assets_router.router)
app.include_router(approvals_router.router)


@app.get("/api/health")
def health_check():
    return {"status": "ok", "version": "1.0.0"}
