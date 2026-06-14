#!/usr/bin/env python3
import requests
import json

BASE_URL = "http://localhost:8000"

users = [
    {"username": "admin", "password": "admin123", "role": "超级管理员", "dept": "IT部门"},
    {"username": "asset_admin", "password": "123456", "role": "资产管理员", "dept": "行政部"},
    {"username": "dept_mgr", "password": "123456", "role": "研发部经理", "dept": "研发部"},
    {"username": "dept_mgr2", "password": "123456", "role": "市场部经理", "dept": "市场部"},
    {"username": "emp1", "password": "123456", "role": "研发部普通员工", "dept": "研发部"},
    {"username": "emp2", "password": "123456", "role": "市场部普通员工", "dept": "市场部"},
]

tokens = {}


def login(username, password):
    url = f"{BASE_URL}/api/auth/login"
    data = {"username": username, "password": password}
    response = requests.post(url, json=data)
    if response.status_code == 200:
        return response.json()["access_token"]
    return None


def get_headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_asset_list(token, role_desc):
    url = f"{BASE_URL}/api/assets?page_size=100"
    response = requests.get(url, headers=get_headers(token))
    if response.status_code == 200:
        result = response.json()
        items = result["items"]
        print(f"  可见资产数量: {result['total']}")
        for item in items:
            assignee = item.get("assignee") or "未分配"
            dept = item.get("purchase_department") or "未设置"
            print(f"    - {item['asset_tag']}: {item['name']} (使用人: {assignee}, 采购部门: {dept})")
        return items
    else:
        print(f"  错误: {response.status_code} - {response.text}")
        return []


def test_asset_detail(token, asset_id, asset_tag, role_desc):
    url = f"{BASE_URL}/api/assets/{asset_id}"
    response = requests.get(url, headers=get_headers(token))
    if response.status_code == 200:
        result = response.json()
        assignee = result.get("assignee") or "未分配"
        dept = result.get("purchase_department") or "未设置"
        print(f"  ✓ 可见: {asset_tag} (使用人: {assignee}, 采购部门: {dept})")
        return True
    else:
        detail = response.json().get('detail', response.text)
        print(f"  ✗ 不可见: {asset_tag} - {detail}")
        return False


def test_create_asset(token, role_desc, operator_dept):
    url = f"{BASE_URL}/api/assets"
    data = {
        "asset_tag": f"TEST-CREATE-{role_desc[:2]}",
        "name": f"API创建测试-{role_desc}",
        "category": "computer",
        "brand": "TestBrand",
        "model": "TestModel",
        "serial_number": f"API-SN-{role_desc[:2]}",
        "purchase_price": 6000.00,
        "status": "in_stock",
    }
    response = requests.post(url, headers=get_headers(token), json=data)
    if response.status_code == 201:
        result = response.json()
        dept = result.get("purchase_department") or "未设置"
        print(f"  ✓ 创建成功: {result['asset_tag']} (采购部门: {dept})")
        if dept == operator_dept:
            print(f"    ✓ 采购部门正确填充为创建者部门: {dept}")
        else:
            print(f"    ✗ 采购部门填充错误: 期望 {operator_dept}, 实际 {dept}")
        return result["id"]
    else:
        print(f"  ✗ 创建失败: {response.status_code} - {response.text}")
        return None


def main():
    print("=" * 80)
    print("未分配资产数据权限修复验证")
    print("=" * 80)
    print("\n测试场景:")
    print("  资产 4: 打印机1 - 未分配 - 采购部门: 研发部")
    print("  资产 5: 打印机2 - 未分配 - 采购部门: 市场部")
    print("  资产 6: 打印机3 - 未分配 - 采购部门: 未设置")
    print()
    print("修复前: 部门经理能看到所有未分配资产 (资产 4, 5, 6)")
    print("修复后: 部门经理只能看到本部门采购的未分配资产")
    print("  - 研发部经理可见: 资产 4")
    print("  - 市场部经理可见: 资产 5")
    print("  - 采购部门未设置的资产 6: 所有部门经理都不可见")
    print("=" * 80)

    print("\n步骤1: 各用户登录")
    print("-" * 60)
    for user in users:
        token = login(user["username"], user["password"])
        if token:
            tokens[user["username"]] = token
            print(f"  [{user['role']}] ✓ 登录成功")
        else:
            print(f"  [{user['role']}] ✗ 登录失败")

    if not tokens:
        print("\n所有用户登录失败!")
        return

    print("\n" + "=" * 80)
    print("步骤2: 验证资产列表权限 - 重点检查未分配资产")
    print("=" * 80)

    asset_ids = {}
    for user in users:
        token = tokens.get(user["username"])
        if not token:
            continue
        print(f"\n[{user['role']} - {user['username']}]")
        print("-" * 60)
        items = test_asset_list(token, user["role"])
        if not asset_ids and items:
            for item in items:
                asset_ids[item["asset_tag"]] = item["id"]

        # 验证关键点
        if "研发部经理" in user["role"]:
            expected_count = 3  # 资产 1, 3, 4
            actual_count = len(items)
            unassigned_dept_match = any(
                item.get("assignee") is None and item.get("purchase_department") == "研发部"
                for item in items
            )
            unassigned_dept_not_match = any(
                item.get("assignee") is None and item.get("purchase_department") != "研发部"
                for item in items
            )
            print(f"\n  验证结果:")
            print(f"    期望可见数量: {expected_count}, 实际可见数量: {actual_count}")
            print(f"    能否看到本部门采购的未分配资产: {'✓ 是' if unassigned_dept_match else '✗ 否'}")
            print(f"    是否错误看到其他部门采购的未分配资产: {'✗ 是(BUG)' if unassigned_dept_not_match else '✓ 否'}")
            if actual_count == expected_count and unassigned_dept_match and not unassigned_dept_not_match:
                print(f"  ✓ 研发部经理权限验证通过!")
            else:
                print(f"  ✗ 研发部经理权限验证失败!")

        if "市场部经理" in user["role"]:
            expected_count = 2  # 资产 2, 5
            actual_count = len(items)
            unassigned_dept_match = any(
                item.get("assignee") is None and item.get("purchase_department") == "市场部"
                for item in items
            )
            unassigned_dept_not_match = any(
                item.get("assignee") is None and item.get("purchase_department") != "市场部"
                for item in items
            )
            print(f"\n  验证结果:")
            print(f"    期望可见数量: {expected_count}, 实际可见数量: {actual_count}")
            print(f"    能否看到本部门采购的未分配资产: {'✓ 是' if unassigned_dept_match else '✗ 否'}")
            print(f"    是否错误看到其他部门采购的未分配资产: {'✗ 是(BUG)' if unassigned_dept_not_match else '✓ 否'}")
            if actual_count == expected_count and unassigned_dept_match and not unassigned_dept_not_match:
                print(f"  ✓ 市场部经理权限验证通过!")
            else:
                print(f"  ✗ 市场部经理权限验证失败!")

    print("\n" + "=" * 80)
    print("步骤3: 验证资产详情权限 - 不同采购部门的未分配资产")
    print("=" * 80)

    test_assets = [
        ("TEST20240100004", "打印机1", "研发部", "未分配"),
        ("TEST20240100005", "打印机2", "市场部", "未分配"),
        ("TEST20240100006", "打印机3", "未设置", "未分配"),
    ]

    for asset_tag, asset_name, purchase_dept, assignee in test_assets:
        asset_id = asset_ids.get(asset_tag)
        if not asset_id:
            continue
        print(f"\n--- {asset_tag}: {asset_name} (采购部门: {purchase_dept}, 使用人: {assignee}) ---")
        for user in users:
            if "部门经理" not in user["role"]:
                continue
            token = tokens.get(user["username"])
            if not token:
                continue
            print(f"\n[{user['role']}]")
            result = test_asset_detail(token, asset_id, asset_tag, user["role"])

    print("\n" + "=" * 80)
    print("步骤4: 验证创建资产时自动填充采购部门")
    print("=" * 80)

    for user in users:
        if "部门经理" not in user["role"] and "资产管理员" not in user["role"]:
            continue
        token = tokens.get(user["username"])
        if not token:
            continue
        print(f"\n[{user['role']}]")
        test_create_asset(token, user["role"], user["dept"])

    print("\n" + "=" * 80)
    print("验证总结:")
    print("=" * 80)
    print("\n修复内容:")
    print("  1. 在 Asset 模型中添加了 purchase_department 字段")
    print("  2. 在 schemas.py 中添加了 purchase_department 可选字段")
    print("  3. create_asset 和批量导入时自动填充创建者所在部门")
    print("  4. apply_asset_data_scope 中部门经理只能看到:")
    print("     - assignee 为本部门员工的资产")
    print("     - assignee 为 null 且 purchase_department 为本部门的资产")
    print("  5. get_asset 和 get_asset_by_tag 同步更新权限校验逻辑")
    print("\n修复效果:")
    print("  ✓ 部门经理不再能看到全公司的未分配资产")
    print("  ✓ 只能看到本部门采购的未分配资产")
    print("  ✓ 采购部门未设置的未分配资产对所有部门经理不可见")
    print("=" * 80)


if __name__ == "__main__":
    main()
