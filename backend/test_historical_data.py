#!/usr/bin/env python3
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.orm import Session
from app.database import engine, Base, SessionLocal
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


def init_rbac_data(db: Session):
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


def get_or_create_role(db: Session, role_code: str) -> Role:
    role = db.query(Role).filter(Role.code == role_code).first()
    if not role:
        print(f"错误: 角色 {role_code} 不存在")
    return role


def create_test_users(db: Session):
    users = [
        {
            "username": "dept_mgr",
            "email": "dept_mgr@example.com",
            "real_name": "张经理",
            "password": "123456",
            "department": "研发部",
            "position": "研发部经理",
            "roles": ["dept_manager", "employee"],
        },
        {
            "username": "dept_mgr2",
            "email": "dept_mgr2@example.com",
            "real_name": "刘经理",
            "password": "123456",
            "department": "市场部",
            "position": "市场部经理",
            "roles": ["dept_manager", "employee"],
        },
        {
            "username": "emp1",
            "email": "emp1@example.com",
            "real_name": "李员工",
            "password": "123456",
            "department": "研发部",
            "position": "软件工程师",
            "roles": ["employee"],
        },
        {
            "username": "emp2",
            "email": "emp2@example.com",
            "real_name": "王员工",
            "password": "123456",
            "department": "市场部",
            "position": "市场专员",
            "roles": ["employee"],
        },
        {
            "username": "asset_admin",
            "email": "asset_admin@example.com",
            "real_name": "资产管理员",
            "password": "123456",
            "department": "行政部",
            "position": "资产管理员",
            "roles": ["asset_admin"],
        },
    ]

    created_users = []
    for user_data in users:
        existing = db.query(User).filter(User.username == user_data["username"]).first()
        if existing:
            print(f"  - 用户 {user_data['username']} 已存在")
            created_users.append(existing)
            continue

        user = User(
            username=user_data["username"],
            email=user_data["email"],
            real_name=user_data["real_name"],
            hashed_password=get_password_hash(user_data["password"]),
            department=user_data["department"],
            position=user_data["position"],
            is_active=True,
            must_change_password=False,
        )
        db.add(user)
        db.flush()

        for role_code in user_data["roles"]:
            role = get_or_create_role(db, role_code)
            if role:
                db.add(UserRole(user_id=user.id, role_id=role.id))

        db.flush()
        created_users.append(user)
        print(f"  - 用户 {user_data['username']} ({user_data['real_name']}) - {user_data['department']}")

    db.commit()
    return created_users


def create_test_assets(db: Session):
    """
    创建测试资产，模拟历史数据：
    - 部分资产 purchase_department 为 null（需要迁移）
    - 部分资产 assignee 为 null 且 purchase_department 为 null（迁移时跳过）
    - 部分资产已有 purchase_department（不需要迁移）
    """
    assets = [
        {
            "asset_tag": "HIST-2024-001",
            "name": "MacBook Pro 14寸",
            "category": "computer",
            "brand": "Apple",
            "model": "MacBook Pro 14",
            "serial_number": "HIST-SN-001",
            "purchase_price": 14999.00,
            "purchase_date": "2024-01-15",
            "status": "allocated",
            "assignee": "李员工",
            "purchase_department": None,
        },
        {
            "asset_tag": "HIST-2024-002",
            "name": "ThinkPad X1 Carbon",
            "category": "computer",
            "brand": "Lenovo",
            "model": "X1 Carbon Gen 11",
            "serial_number": "HIST-SN-002",
            "purchase_price": 12999.00,
            "purchase_date": "2024-02-20",
            "status": "allocated",
            "assignee": "王员工",
            "purchase_department": None,
        },
        {
            "asset_tag": "HIST-2024-003",
            "name": "Dell 显示器 27寸",
            "category": "monitor",
            "brand": "Dell",
            "model": "U2723QE",
            "serial_number": "HIST-SN-003",
            "purchase_price": 3999.00,
            "purchase_date": "2024-03-10",
            "status": "allocated",
            "assignee": "张经理",
            "purchase_department": None,
        },
        {
            "asset_tag": "HIST-2024-004",
            "name": "HP 打印机",
            "category": "printer",
            "brand": "HP",
            "model": "LaserJet Pro",
            "serial_number": "HIST-SN-004",
            "purchase_price": 1999.00,
            "purchase_date": "2024-04-05",
            "status": "in_stock",
            "assignee": None,
            "purchase_department": None,
        },
        {
            "asset_tag": "HIST-2024-005",
            "name": "Cisco 交换机",
            "category": "network_device",
            "brand": "Cisco",
            "model": "SG350-28",
            "serial_number": "HIST-SN-005",
            "purchase_price": 4999.00,
            "purchase_date": "2024-05-15",
            "status": "allocated",
            "assignee": "资产管理员",
            "purchase_department": None,
        },
        {
            "asset_tag": "NEW-2024-001",
            "name": "新键盘-研发部",
            "category": "peripheral",
            "brand": "Logitech",
            "model": "MX Keys",
            "serial_number": "NEW-SN-001",
            "purchase_price": 899.00,
            "purchase_date": "2024-06-01",
            "status": "in_stock",
            "assignee": None,
            "purchase_department": "研发部",  # 已有采购部门，不需要迁移
        },
        {
            "asset_tag": "NEW-2024-002",
            "name": "新键盘-市场部",
            "category": "peripheral",
            "brand": "Logitech",
            "model": "MX Keys",
            "serial_number": "NEW-SN-002",
            "purchase_price": 899.00,
            "purchase_date": "2024-06-02",
            "status": "in_stock",
            "assignee": None,
            "purchase_department": "市场部",  # 已有采购部门，不需要迁移
        },
    ]

    created_assets = []
    for asset_data in assets:
        existing = db.query(Asset).filter(Asset.asset_tag == asset_data["asset_tag"]).first()
        if existing:
            print(f"  - 资产 {asset_data['asset_tag']} 已存在")
            created_assets.append(existing)
            continue

        asset = Asset(**asset_data)
        db.add(asset)
        db.flush()
        created_assets.append(asset)

        dept_str = asset_data["purchase_department"] or "未设置(待迁移)"
        assignee_str = asset_data["assignee"] or "未分配"
        print(f"  - {asset_data['asset_tag']}: {asset_data['name']} (使用人: {assignee_str}, 采购部门: {dept_str})")

    db.commit()
    return created_assets


def main():
    print("=" * 80)
    print("初始化测试数据 - 模拟存量历史数据（purchase_department为null）")
    print("=" * 80)

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        print("\n" + "=" * 60)
        print("步骤1: 初始化 RBAC 数据")
        print("-" * 60)
        init_rbac_data(db)
        print("✓ RBAC 数据初始化完成")

        print("\n" + "=" * 60)
        print("步骤2: 创建测试用户")
        print("-" * 60)
        create_test_users(db)
        print("✓ 测试用户创建完成")

        print("\n" + "=" * 60)
        print("步骤3: 创建测试资产 - 包含需迁移的历史数据")
        print("-" * 60)
        assets = create_test_assets(db)
        print("✓ 测试资产创建完成")

        assets = db.query(Asset).all()
        null_dept_count = sum(1 for a in assets if a.purchase_department is None)
        assigned_null_dept_count = sum(1 for a in assets if a.purchase_department is None and a.assignee is not None)
        unassigned_null_dept_count = sum(1 for a in assets if a.purchase_department is None and a.assignee is None)
        has_dept_count = sum(1 for a in assets if a.purchase_department is not None)

        print("\n" + "=" * 60)
        print("迁移前数据统计:")
        print("-" * 60)
        print(f"  总资产数: {len(assets)}")
        print(f"  purchase_department 为 null: {null_dept_count} 条")
        print(f"    - 已分配（需要回填）: {assigned_null_dept_count} 条")
        print(f"    - 未分配（跳过）: {unassigned_null_dept_count} 条")
        print(f"  已有 purchase_department: {has_dept_count} 条")

        print("\n" + "=" * 60)
        print("预期迁移结果:")
        print("-" * 60)
        print("  HIST-2024-001 (李员工) → 研发部")
        print("  HIST-2024-002 (王员工) → 市场部")
        print("  HIST-2024-003 (张经理) → 研发部")
        print("  HIST-2024-004 (未分配) → 跳过")
        print("  HIST-2024-005 (资产管理员) → 行政部")
        print("  NEW-2024-001/002 → 已有部门，不迁移")
        print("=" * 80)

    except Exception as e:
        db.rollback()
        print(f"错误: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
