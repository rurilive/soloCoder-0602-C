import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ["ASSET_JWT_SECRET"] = "test-secret-key-for-development"

from app.database import SessionLocal, Base, engine
from app.models import (
    User, Role, UserRole, Permission, RolePermission,
    Asset, Approval, ApprovalChain, ApprovalChainNode, ApprovalNodeRecord,
    AssetStatus, ApprovalType, ApprovalStatus, AssetCategory,
    DEFAULT_PERMISSIONS, DEFAULT_ROLES, SUPER_ADMIN_USER,
    OperationLog,
)
from app.auth import (
    get_password_hash, is_admin_user, is_dept_manager,
    get_user_dept, get_dept_user_names, apply_asset_data_scope,
    apply_approval_data_scope, get_user_display_name,
)

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
    print("测试3: 创建测试资产")
    print("=" * 60)

    assets_data = [
        {"name": "笔记本电脑1", "assignee": "李员工", "category": AssetCategory.COMPUTER},
        {"name": "笔记本电脑2", "assignee": "王员工", "category": AssetCategory.COMPUTER},
        {"name": "显示器1", "assignee": "张经理", "category": AssetCategory.MONITOR},
        {"name": "打印机1", "assignee": None, "category": AssetCategory.PRINTER},
        {"name": "网络设备1", "assignee": "资产管理员", "category": AssetCategory.NETWORK_DEVICE},
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
            )
            db.add(asset)
            db.flush()
            created_assets.append(asset)
        else:
            created_assets.append(existing)

    db.commit()
    print("✓ 测试资产创建完成")
    for asset in created_assets:
        print(f"  - {asset.asset_tag}: {asset.name} (使用人: {asset.assignee or '库存'})")

    print()
    print("=" * 60)
    print("测试4: 验证数据权限 - 资产列表")
    print("=" * 60)

    for desc, user in test_users:
        query = db.query(Asset)
        filtered_query = apply_asset_data_scope(query, db, user.id)
        count = filtered_query.count()
        assets = filtered_query.all()
        print(f"\n[{desc} - {user.username}]")
        print(f"  可见资产数量: {count}")
        for asset in assets:
            print(f"    - {asset.asset_tag}: {asset.name} (使用人: {asset.assignee or '库存'})")

    print()
    print("=" * 60)
    print("测试5: 验证辅助函数")
    print("=" * 60)

    for desc, user in test_users:
        print(f"\n[{desc} - {user.username}]")
        print(f"  is_admin_user: {is_admin_user(db, user.id)}")
        print(f"  is_dept_manager: {is_dept_manager(db, user.id)}")
        print(f"  get_user_dept: {get_user_dept(db, user.id)}")
        print(f"  display_name: {get_user_display_name(user)}")

    dept_users = get_dept_user_names(db, "研发部")
    print(f"\n研发部用户姓名列表: {dept_users}")

    print()
    print("=" * 60)
    print("测试6: 验证操作日志功能")
    print("=" * 60)

    from app.crud import create_operation_log, get_operation_logs

    log = create_operation_log(
        db=db,
        module="test",
        action="test_action",
        operator="测试用户",
        operator_id=test_users[0][1].id,
        target_type="asset",
        target_id=1,
        detail="这是一条测试操作日志",
        ip_address="127.0.0.1",
        user_agent="TestAgent/1.0",
        status="success",
    )
    print(f"✓ 创建操作日志成功, ID: {log.id}")

    logs, total = get_operation_logs(db, page=1, page_size=10)
    print(f"✓ 查询操作日志, 总数: {total}")

    print()
    print("=" * 60)
    print("所有测试通过!")
    print("=" * 60)

finally:
    db.close()
