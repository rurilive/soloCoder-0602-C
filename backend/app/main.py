from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from app.database import engine, Base, SessionLocal
from app.routers import assets as assets_router
from app.routers import approvals as approvals_router
from app.routers import auth as auth_router
from app.routers import users as users_router
from app.routers import permissions as permissions_router
from app.routers import logs as logs_router
from app.models import (
    Permission,
    Role,
    RolePermission,
    User,
    UserRole,
    Asset,
    DEFAULT_PERMISSIONS,
    DEFAULT_ROLES,
    SUPER_ADMIN_USER,
)
from app.auth import get_password_hash


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


def _migrate_purchase_department():
    """
    一次性数据迁移：对所有 purchase_department 为 null 的资产，
    根据其 assignee 反查 User 表的 department 字段进行回填。
    assignee 也为 null 的保持不动。
    """
    db: Session = SessionLocal()
    try:
        assets_to_migrate = db.query(Asset).filter(Asset.purchase_department.is_(None)).all()
        if not assets_to_migrate:
            print("[数据迁移] 没有需要迁移的存量资产数据")
            return

        all_users = db.query(User).filter(User.is_active == True).all()
        user_dept_map = {}
        for user in all_users:
            display_name = user.real_name or user.username
            user_dept_map[display_name] = user.department
            user_dept_map[user.username] = user.department
            if user.real_name:
                user_dept_map[user.real_name] = user.department

        updated_count = 0
        skipped_count = 0

        for asset in assets_to_migrate:
            if asset.assignee is None:
                skipped_count += 1
                continue

            dept = user_dept_map.get(asset.assignee)
            if dept:
                asset.purchase_department = dept
                updated_count += 1
            else:
                skipped_count += 1

        db.commit()

        print(f"[数据迁移] 存量资产 purchase_department 迁移完成:")
        print(f"  - 总共有 {len(assets_to_migrate)} 条资产需要迁移")
        print(f"  - 成功回填 {updated_count} 条")
        print(f"  - 跳过 {skipped_count} 条（未分配或找不到对应用户）")

    except Exception as e:
        db.rollback()
        print(f"[数据迁移] 迁移失败: {e}")
        raise e
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _init_rbac_data()
    _migrate_purchase_department()
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

app.include_router(auth_router.router)
app.include_router(users_router.router)
app.include_router(permissions_router.router)
app.include_router(assets_router.router)
app.include_router(approvals_router.router)
app.include_router(logs_router.router)


@app.get("/api/health")
def health_check():
    return {"status": "ok", "version": "1.0.0"}
