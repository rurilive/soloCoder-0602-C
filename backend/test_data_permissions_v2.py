import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ["ASSET_JWT_SECRET"] = "test-secret-key-for-development"

from app.database import SessionLocal, Base, engine
from app.models import (
    User, Role, UserRole, Permission, RolePermission,
    Asset, AssetStatus, AssetCategory,
    DEFAULT_PERMISSIONS, DEFAULT_ROLES, SUPER_ADMIN_USER,
)
from app.auth import get_password_hash

Base.metadata.create_all(bind=engine)

db = SessionLocal()

try:
    print("=" * 60)
    print("测试1: 初始化 RBAC 数据")
    print("=" * 60)

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
            must_change_password=False,
        )
        db.add(user)
        db.flush()

        super_admin_role = db.query(Role).filter(Role.code == "super_admin").first()
        if super_admin_role:
            db.add(UserRole(user_id=user.id, role_id=super_admin_role.id))

    db.commit()
    print("✓ RBAC 数据初始化完成")

    print()
    print("=" * 60)
    print("测试2: 创建测试用户")
    print("=" * 60)

    dept_manager_role = db.query(Role).filter(Role.code == "dept_manager").first()
    employee_role = db.query(Role).filter(Role.code == "employee").first()
    asset_admin_role = db.query(Role).filter(Role.code == "asset_admin").first()

    test_users = []

    dept_mgr_user = db.query(User).filter(User.username == "dept_mgr").first()
    if not dept_mgr_user:
        dept_mgr_user = User(
            username="dept_mgr",
            email="dept_mgr@example.com",
            real_name="张经理",
            hashed_password=get_password_hash("123456"),
            department="研发部",
            position="部门经理",
            is_active=True,
            must_change_password=False,
        )
        db.add(dept_mgr_user)
        db.flush()
        db.add(UserRole(user_id=dept_mgr_user.id, role_id=dept_manager_role.id))
        db.commit()
        db.refresh(dept_mgr_user)
    test_users.append(("部门经理 (研发部)", dept_mgr_user))

    dept_mgr2_user = db.query(User).filter(User.username == "dept_mgr2").first()
    if not dept_mgr2_user:
        dept_mgr2_user = User(
            username="dept_mgr2",
            email="dept_mgr2@example.com",
            real_name="刘经理",
            hashed_password=get_password_hash("123456"),
            department="市场部",
            position="部门经理",
            is_active=True,
            must_change_password=False,
        )
        db.add(dept_mgr2_user)
        db.flush()
        db.add(UserRole(user_id=dept_mgr2_user.id, role_id=dept_manager_role.id))
        db.commit()
        db.refresh(dept_mgr2_user)
    test_users.append(("部门经理 (市场部)", dept_mgr2_user))

    employee1 = db.query(User).filter(User.username == "emp1").first()
    if not employee1:
        employee1 = User(
            username="emp1",
            email="emp1@example.com",
            real_name="李员工",
            hashed_password=get_password_hash("123456"),
            department="研发部",
            position="软件工程师",
            is_active=True,
            must_change_password=False,
        )
        db.add(employee1)
        db.flush()
        db.add(UserRole(user_id=employee1.id, role_id=employee_role.id))
        db.commit()
        db.refresh(employee1)
    test_users.append(("普通员工 (研发部)", employee1))

    employee2 = db.query(User).filter(User.username == "emp2").first()
    if not employee2:
        employee2 = User(
            username="emp2",
            email="emp2@example.com",
            real_name="王员工",
            hashed_password=get_password_hash("123456"),
            department="市场部",
            position="市场专员",
            is_active=True,
            must_change_password=False,
        )
        db.add(employee2)
        db.flush()
        db.add(UserRole(user_id=employee2.id, role_id=employee_role.id))
        db.commit()
        db.refresh(employee2)
    test_users.append(("普通员工 (市场部)", employee2))

    asset_admin = db.query(User).filter(User.username == "asset_admin").first()
    if not asset_admin:
        asset_admin = User(
            username="asset_admin",
            email="asset_admin@example.com",
            real_name="资产管理员",
            hashed_password=get_password_hash("123456"),
            department="行政部",
            position="资产管理员",
            is_active=True,
            must_change_password=False,
        )
        db.add(asset_admin)
        db.flush()
        db.add(UserRole(user_id=asset_admin.id, role_id=asset_admin_role.id))
        db.commit()
        db.refresh(asset_admin)
    test_users.append(("资产管理员", asset_admin))

    super_admin = db.query(User).filter(User.username == "admin").first()
    test_users.append(("超级管理员", super_admin))

    print("✓ 测试用户创建完成")
    for desc, user in test_users:
        print(f"  - {desc}: {user.username} ({user.real_name}) - {user.department}")

    print()
    print("=" * 60)
    print("测试3: 创建测试资产 - 包含不同采购部门的未分配资产")
    print("=" * 60)

    assets_data = [
        {"name": "笔记本电脑1", "assignee": "李员工", "category": AssetCategory.COMPUTER, "purchase_department": "研发部"},
        {"name": "笔记本电脑2", "assignee": "王员工", "category": AssetCategory.COMPUTER, "purchase_department": "市场部"},
        {"name": "显示器1", "assignee": "张经理", "category": AssetCategory.MONITOR, "purchase_department": "研发部"},
        {"name": "打印机1", "assignee": None, "category": AssetCategory.PRINTER, "purchase_department": "研发部"},
        {"name": "打印机2", "assignee": None, "category": AssetCategory.PRINTER, "purchase_department": "市场部"},
        {"name": "打印机3", "assignee": None, "category": AssetCategory.PRINTER, "purchase_department": None},
        {"name": "网络设备1", "assignee": "资产管理员", "category": AssetCategory.NETWORK_DEVICE, "purchase_department": "行政部"},
    ]

    created_assets = []
    for i, ad in enumerate(assets_data):
        asset_tag = f"TEST2024010{i+1:04d}"
        existing = db.query(Asset).filter(Asset.asset_tag == asset_tag).first()
        if not existing:
            asset = Asset(
                asset_tag=asset_tag,
                name=ad["name"],
                category=ad["category"],
                brand="TestBrand",
                model=f"Model{i+1}",
                serial_number=f"SN{i+1:08d}",
                status=AssetStatus.ALLOCATED if ad["assignee"] else AssetStatus.IN_STOCK,
                assignee=ad["assignee"],
                purchase_price=5000.0 + i * 1000,
                purchase_department=ad.get("purchase_department"),
            )
            db.add(asset)
            db.flush()
            created_assets.append(asset)
        else:
            created_assets.append(existing)

    db.commit()
    print("✓ 测试资产创建完成")
    for asset in created_assets:
        assignee = asset.assignee or "未分配"
        dept = asset.purchase_department or "未设置"
        print(f"  - {asset.asset_tag}: {asset.name} (使用人: {assignee}, 采购部门: {dept})")

    print()
    print("=" * 60)
    print("测试场景说明:")
    print("=" * 60)
    print("资产列表:")
    print("  1. TEST20240100001: 笔记本电脑1 - 李员工(研发部) - 采购部门: 研发部")
    print("  2. TEST20240100002: 笔记本电脑2 - 王员工(市场部) - 采购部门: 市场部")
    print("  3. TEST20240100003: 显示器1 - 张经理(研发部) - 采购部门: 研发部")
    print("  4. TEST20240100004: 打印机1 - 未分配 - 采购部门: 研发部 ✓ 研发部经理可见")
    print("  5. TEST20240100005: 打印机2 - 未分配 - 采购部门: 市场部 ✓ 市场部经理可见")
    print("  6. TEST20240100006: 打印机3 - 未分配 - 采购部门: 未设置 ✗ 所有部门经理都不可见")
    print("  7. TEST20240100007: 网络设备1 - 资产管理员 - 采购部门: 行政部")
    print()
    print("预期结果:")
    print("  研发部经理可见: 资产 1, 3, 4 (共3条)")
    print("  市场部经理可见: 资产 2, 5 (共2条)")
    print("  超级管理员/资产管理员可见: 全部 7 条")
    print("=" * 60)

finally:
    db.close()
