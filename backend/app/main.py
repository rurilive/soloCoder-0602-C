from contextlib import asynccontextmanager
import asyncio
import logging
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
from app.routers import notifications as notifications_router
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

logger = logging.getLogger(__name__)


async def _background_timeout_checker():
    while True:
        try:
            await asyncio.sleep(60)
            db: Session = SessionLocal()
            try:
                from app.crud import check_and_process_timeouts, expire_outdated_proxies
                processed = check_and_process_timeouts(db)
                expired = expire_outdated_proxies(db)
                if processed or expired:
                    logger.info(f"[后台任务] 超时处理: {len(processed)}条, 代理过期: {expired}条")
            except Exception as e:
                logger.error(f"[后台任务] 超时检查失败: {e}")
            finally:
                db.close()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"[后台任务] 异常: {e}")


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
        return
    finally:
        db.close()


def _migrate_add_timeout_proxy_columns():
    db: Session = SessionLocal()
    try:
        from sqlalchemy import inspect, text
        insp = inspect(engine)

        chain_node_cols = {c["name"] for c in insp.get_columns("approval_chain_nodes")}
        if "timeout_minutes" not in chain_node_cols:
            db.execute(text("ALTER TABLE approval_chain_nodes ADD COLUMN timeout_minutes INTEGER"))
            db.commit()
            print("[数据迁移] approval_chain_nodes 新增 timeout_minutes 列")

        node_record_cols = {c["name"] for c in insp.get_columns("approval_node_records")}
        new_cols = {
            "timeout_at": "DATETIME",
            "is_escalated": "BOOLEAN DEFAULT 0",
            "actual_approver": "VARCHAR(128)",
            "proxy_source": "VARCHAR(128)",
        }
        for col_name, col_type in new_cols.items():
            if col_name not in node_record_cols:
                db.execute(text(f"ALTER TABLE approval_node_records ADD COLUMN {col_name} {col_type}"))
                db.commit()
                print(f"[数据迁移] approval_node_records 新增 {col_name} 列")

        if not insp.has_table("approval_proxies"):
            print("[数据迁移] approval_proxies 表将由 SQLAlchemy 自动创建")

    except Exception as e:
        db.rollback()
        print(f"[数据迁移] 迁移失败: {e}")
    finally:
        db.close()


def _migrate_add_withdraw_reminder_columns():
    db: Session = SessionLocal()
    try:
        from sqlalchemy import inspect, text
        insp = inspect(engine)

        approval_cols = {c["name"] for c in insp.get_columns("approvals")}
        if "reminder_count" not in approval_cols:
            db.execute(text("ALTER TABLE approvals ADD COLUMN reminder_count INTEGER NOT NULL DEFAULT 0"))
            db.commit()
            print("[数据迁移] approvals 新增 reminder_count 列")

        if "last_reminder_at" not in approval_cols:
            db.execute(text("ALTER TABLE approvals ADD COLUMN last_reminder_at DATETIME"))
            db.commit()
            print("[数据迁移] approvals 新增 last_reminder_at 列")

        if not insp.has_table("approval_reminders"):
            print("[数据迁移] approval_reminders 表将由 SQLAlchemy 自动创建")

        if not insp.has_table("notifications"):
            print("[数据迁移] notifications 表将由 SQLAlchemy 自动创建")

    except Exception as e:
        db.rollback()
        print(f"[数据迁移] 撤回/催办迁移失败: {e}")
    finally:
        db.close()


def _migrate_add_countersign_columns():
    db: Session = SessionLocal()
    try:
        from sqlalchemy import inspect, text
        from app.models import ApprovalMode
        insp = inspect(engine)

        if insp.has_table("approval_chain_nodes"):
            chain_node_cols = {c["name"] for c in insp.get_columns("approval_chain_nodes")}
            if "mode" not in chain_node_cols:
                db.execute(text("ALTER TABLE approval_chain_nodes ADD COLUMN mode VARCHAR(32) NOT NULL DEFAULT 'single'"))
                db.commit()
                print("[数据迁移] approval_chain_nodes 新增 mode 列")

        if insp.has_table("approval_node_records"):
            node_record_cols = {c["name"] for c in insp.get_columns("approval_node_records")}
            if "chain_node_approver_id" not in node_record_cols:
                db.execute(text("ALTER TABLE approval_node_records ADD COLUMN chain_node_approver_id INTEGER"))
                db.commit()
                print("[数据迁移] approval_node_records 新增 chain_node_approver_id 列")

        if not insp.has_table("approval_chain_node_approvers"):
            print("[数据迁移] approval_chain_node_approvers 表将由 SQLAlchemy 自动创建")

        if insp.has_table("approval_chain_nodes") and "approver_role" in {c["name"] for c in insp.get_columns("approval_chain_nodes")}:
            existing_nodes = db.execute(text("SELECT id, chain_id, level, approver_role, approver_name, timeout_minutes FROM approval_chain_nodes WHERE id NOT IN (SELECT chain_node_id FROM approval_chain_node_approvers)")).fetchall()
            if existing_nodes:
                for node in existing_nodes:
                    db.execute(
                        text("INSERT INTO approval_chain_node_approvers (chain_node_id, approver_role, approver_name, created_at) VALUES (:chain_node_id, :approver_role, :approver_name, :created_at)"),
                        {
                            "chain_node_id": node[0],
                            "approver_role": node[3],
                            "approver_name": node[4],
                            "created_at": __import__("datetime").datetime.now(),
                        }
                    )
                db.commit()
                print(f"[数据迁移] 已将 {len(existing_nodes)} 条原有审批链节点数据迁移到 approval_chain_node_approvers 表")

    except Exception as e:
        db.rollback()
        print(f"[数据迁移] 会签功能迁移失败: {e}")
    finally:
        db.close()


def _migrate_add_conditional_branch_columns():
    db: Session = SessionLocal()
    try:
        from sqlalchemy import inspect, text
        insp = inspect(engine)

        if not insp.has_table("approval_chain_conditions"):
            print("[数据迁移] approval_chain_conditions 表将由 SQLAlchemy 自动创建")
        if not insp.has_table("approval_chain_condition_rules"):
            print("[数据迁移] approval_chain_condition_rules 表将由 SQLAlchemy 自动创建")

        if insp.has_table("approval_chain_nodes"):
            chain_node_cols = {c["name"] for c in insp.get_columns("approval_chain_nodes")}
            if "default_next_level" not in chain_node_cols:
                db.execute(text("ALTER TABLE approval_chain_nodes ADD COLUMN default_next_level INTEGER"))
                db.commit()
                print("[数据迁移] approval_chain_nodes 新增 default_next_level 列")

            if "approver_role" in chain_node_cols or "approver_name" in chain_node_cols:
                print("[数据迁移] 检测到 approval_chain_nodes 存在旧列，开始安全重建表...")
                db.execute(text("PRAGMA foreign_keys = OFF"))
                try:
                    db.execute(text("""
                        CREATE TABLE approval_chain_nodes_new (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            chain_id INTEGER NOT NULL,
                            level INTEGER NOT NULL,
                            mode VARCHAR(32) NOT NULL DEFAULT 'single',
                            timeout_minutes INTEGER,
                            default_next_level INTEGER,
                            created_at DATETIME NOT NULL,
                            CONSTRAINT fk_chain_nodes_chain FOREIGN KEY (chain_id) REFERENCES approval_chains (id)
                        )
                    """))
                    db.execute(text("""
                        INSERT INTO approval_chain_nodes_new (id, chain_id, level, mode, timeout_minutes, default_next_level, created_at)
                        SELECT id, chain_id, level, COALESCE(mode, 'single'), timeout_minutes, default_next_level, created_at
                        FROM approval_chain_nodes
                    """))
                    new_count = db.execute(text("SELECT COUNT(*) FROM approval_chain_nodes_new")).scalar()
                    old_count = db.execute(text("SELECT COUNT(*) FROM approval_chain_nodes")).scalar()
                    if new_count != old_count:
                        raise ValueError(f"数据不一致：旧表{old_count}条，新表{new_count}条")
                    db.execute(text("DROP TABLE approval_chain_nodes"))
                    db.execute(text("ALTER TABLE approval_chain_nodes_new RENAME TO approval_chain_nodes"))
                    db.execute(text("CREATE INDEX ix_approval_chain_nodes_chain_id ON approval_chain_nodes (chain_id)"))
                    db.commit()
                    print(f"[数据迁移] approval_chain_nodes 安全重建完成，移除旧列，保留 {new_count} 条数据")
                except Exception as rebuild_err:
                    db.rollback()
                    print(f"[数据迁移] 重建表失败，回滚：{rebuild_err}")
                    raise
                finally:
                    db.execute(text("PRAGMA foreign_keys = ON"))
                    db.commit()

        if insp.has_table("approval_node_records"):
            node_record_cols = {c["name"] for c in insp.get_columns("approval_node_records")}
            if "chain_node_level" not in node_record_cols:
                db.execute(text("ALTER TABLE approval_node_records ADD COLUMN chain_node_level INTEGER NOT NULL DEFAULT 0"))
                db.commit()
                print("[数据迁移] approval_node_records 新增 chain_node_level 列")

                db.execute(text("""
                    UPDATE approval_node_records
                    SET chain_node_level = (
                        SELECT level FROM approval_chain_nodes
                        WHERE approval_chain_nodes.id = approval_node_records.chain_node_id
                    )
                    WHERE chain_node_level = 0
                """))
                db.commit()
                print("[数据迁移] 已回填 approval_node_records.chain_node_level 历史数据")

    except Exception as e:
        db.rollback()
        print(f"[数据迁移] 条件分支功能迁移失败: {e}")
    finally:
        db.close()


def _migrate_add_signer_transfer_columns():
    db: Session = SessionLocal()
    try:
        from sqlalchemy import inspect, text
        insp = inspect(engine)

        if not insp.has_table("approval_node_actions"):
            print("[数据迁移] approval_node_actions 表将由 SQLAlchemy 自动创建")

        if insp.has_table("approval_node_records"):
            node_record_cols = {c["name"] for c in insp.get_columns("approval_node_records")}
            new_cols = {
                "record_type": "VARCHAR(32) NOT NULL DEFAULT 'normal'",
                "is_added_signer": "BOOLEAN NOT NULL DEFAULT 0",
                "added_signer_by": "VARCHAR(128)",
                "added_signer_reason": "TEXT",
                "transfer_status": "VARCHAR(32)",
                "transferred_from": "VARCHAR(128)",
                "transferred_to": "VARCHAR(128)",
                "transfer_reason": "TEXT",
                "source_record_id": "INTEGER",
            }
            for col_name, col_type in new_cols.items():
                if col_name not in node_record_cols:
                    db.execute(text(f"ALTER TABLE approval_node_records ADD COLUMN {col_name} {col_type}"))
                    db.commit()
                    print(f"[数据迁移] approval_node_records 新增 {col_name} 列")

    except Exception as e:
        db.rollback()
        print(f"[数据迁移] 加签转审功能迁移失败: {e}")
    finally:
        db.close()


def _migrate_processing_lock_columns():
    db: Session = SessionLocal()
    try:
        from sqlalchemy import inspect, text
        insp = inspect(engine)

        if not insp.has_table("task_locks"):
            db.execute(text(
                "CREATE TABLE task_locks ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "task_name VARCHAR(128) UNIQUE NOT NULL, "
                "locked_by VARCHAR(128), "
                "locked_at DATETIME, "
                "expires_at DATETIME, "
                "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                "updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"
                ")"
            ))
            db.execute(text("CREATE INDEX IF NOT EXISTS ix_task_locks_task_name ON task_locks(task_name)"))
            db.commit()
            print("[数据迁移] 新建 task_locks 表")

        approval_cols = {c["name"] for c in insp.get_columns("approvals")}
        if "processing_lock" not in approval_cols:
            db.execute(text("ALTER TABLE approvals ADD COLUMN processing_lock VARCHAR(128)"))
            db.commit()
            print("[数据迁移] approvals 新增 processing_lock 列")

        approval_cols = {c["name"] for c in insp.get_columns("approvals")}
        if "processing_locked_at" not in approval_cols:
            db.execute(text("ALTER TABLE approvals ADD COLUMN processing_locked_at DATETIME"))
            db.commit()
            print("[数据迁移] approvals 新增 processing_locked_at 列")

    except Exception as e:
        db.rollback()
        print(f"[数据迁移] processing_lock 并发锁迁移失败: {e}")
    finally:
        db.close()


def _migrate_escalation_strategy_columns():
    db: Session = SessionLocal()
    try:
        from sqlalchemy import inspect, text
        insp = inspect(engine)

        chain_node_cols = {c["name"] for c in insp.get_columns("approval_chain_nodes")}
        if "escalation_strategy" not in chain_node_cols:
            db.execute(text(
                "ALTER TABLE approval_chain_nodes ADD COLUMN escalation_strategy "
                "VARCHAR(32) NOT NULL DEFAULT 'escalate_to_level'"
            ))
            db.commit()
            print("[数据迁移] approval_chain_nodes 新增 escalation_strategy 列")

        if "escalation_target_level" not in chain_node_cols:
            db.execute(text(
                "ALTER TABLE approval_chain_nodes ADD COLUMN escalation_target_level INTEGER"
            ))
            db.commit()
            print("[数据迁移] approval_chain_nodes 新增 escalation_target_level 列")

    except Exception as e:
        db.rollback()
        print(f"[数据迁移] 升级策略字段迁移失败: {e}")
    finally:
        db.close()


def _migrate_parallel_gateway_columns():
    db: Session = SessionLocal()
    try:
        from sqlalchemy import inspect, text
        insp = inspect(engine)

        if insp.has_table("approval_chain_nodes"):
            chain_node_cols = {c["name"] for c in insp.get_columns("approval_chain_nodes")}
            new_chain_cols = {
                "node_type": "VARCHAR(32) NOT NULL DEFAULT 'approval'",
                "parallel_group_id": "VARCHAR(64)",
                "branch_id": "VARCHAR(64)",
                "branch_index": "INTEGER",
            }
            for col_name, col_type in new_chain_cols.items():
                if col_name not in chain_node_cols:
                    db.execute(text(f"ALTER TABLE approval_chain_nodes ADD COLUMN {col_name} {col_type}"))
                    db.commit()
                    print(f"[数据迁移] approval_chain_nodes 新增 {col_name} 列")

        if insp.has_table("approval_node_records"):
            node_record_cols = {c["name"] for c in insp.get_columns("approval_node_records")}
            new_record_cols = {
                "parallel_group_id": "VARCHAR(64)",
                "branch_id": "VARCHAR(64)",
                "branch_index": "INTEGER",
                "branch_complete": "BOOLEAN NOT NULL DEFAULT 0",
            }
            for col_name, col_type in new_record_cols.items():
                if col_name not in node_record_cols:
                    db.execute(text(f"ALTER TABLE approval_node_records ADD COLUMN {col_name} {col_type}"))
                    db.commit()
                    print(f"[数据迁移] approval_node_records 新增 {col_name} 列")

    except Exception as e:
        db.rollback()
        print(f"[数据迁移] 并行网关节点字段迁移失败: {e}")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _init_rbac_data()
    _migrate_purchase_department()
    _migrate_add_timeout_proxy_columns()
    _migrate_add_withdraw_reminder_columns()
    _migrate_add_countersign_columns()
    _migrate_add_conditional_branch_columns()
    _migrate_add_signer_transfer_columns()
    _migrate_processing_lock_columns()
    _migrate_escalation_strategy_columns()
    _migrate_parallel_gateway_columns()
    task = asyncio.create_task(_background_timeout_checker())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


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
app.include_router(notifications_router.router)


@app.get("/api/health")
def health_check():
    return {"status": "ok", "version": "1.0.0"}
