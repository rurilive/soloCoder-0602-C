#!/usr/bin/env python3
import requests
import json

BASE_URL = "http://localhost:8000"

users = [
    {"username": "admin", "password": "admin123", "role": "超级管理员"},
    {"username": "asset_admin", "password": "123456", "role": "资产管理员"},
    {"username": "dept_mgr", "password": "123456", "role": "研发部经理"},
    {"username": "emp1", "password": "123456", "role": "研发部普通员工"},
    {"username": "emp2", "password": "123456", "role": "市场部普通员工"},
]

tokens = {}


def login(username, password):
    url = f"{BASE_URL}/api/auth/login"
    data = {"username": username, "password": password}
    response = requests.post(url, json=data)
    if response.status_code == 200:
        result = response.json()
        return result["access_token"]
    else:
        print(f"  登录失败: {response.status_code} - {response.text}")
        return None


def get_headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_asset_list(token, role_desc):
    url = f"{BASE_URL}/api/assets?page_size=100"
    response = requests.get(url, headers=get_headers(token))
    if response.status_code == 200:
        result = response.json()
        items = result["items"]
        print(f"\n  可见资产数量: {result['total']}")
        for item in items:
            assignee = item.get("assignee") or "未分配"
            print(f"    - {item['asset_tag']}: {item['name']} (使用人: {assignee})")
        
        has_unassigned = any(item.get("assignee") is None for item in items)
        if "部门经理" in role_desc:
            print(f"  ✓ 是否能看到未分配资产: {'是' if has_unassigned else '否'}")
        
        return items
    else:
        print(f"  错误: {response.status_code} - {response.text}")
        return []


def test_asset_detail(token, asset_id, role_desc):
    url = f"{BASE_URL}/api/assets/{asset_id}"
    response = requests.get(url, headers=get_headers(token))
    if response.status_code == 200:
        result = response.json()
        item = result
        assignee = item.get("assignee") or "未分配"
        print(f"  ✓ 资产详情: {item['asset_tag']}: {item['name']} (使用人: {assignee})")
        return True
    else:
        print(f"  ✗ 资产详情失败: {response.status_code} - {response.json().get('detail', response.text)}")
        return False


def test_approval_list(token, role_desc):
    url = f"{BASE_URL}/api/approvals?page_size=100"
    response = requests.get(url, headers=get_headers(token))
    if response.status_code == 200:
        result = response.json()
        items = result["items"]
        print(f"\n  可见审批单数量: {result['total']}")
        for item in items:
            print(f"    - 审批单#{item['id']}: {item['approval_type']} - {item['applicant']} - {item['status']}")
        return items
    else:
        print(f"  错误: {response.status_code} - {response.text}")
        return []


def test_approval_detail(token, approval_id, role_desc):
    url = f"{BASE_URL}/api/approvals/{approval_id}"
    response = requests.get(url, headers=get_headers(token))
    if response.status_code == 200:
        result = response.json()
        item = result
        print(f"  ✓ 审批单详情: #{item['id']}: {item['approval_type']} - {item['applicant']} - {item['status']}")
        return True
    else:
        print(f"  ✗ 审批单详情失败: {response.status_code} - {response.json().get('detail', response.text)}")
        return False


def test_create_asset(token, role_desc):
    url = f"{BASE_URL}/api/assets"
    data = {
        "asset_tag": "TEST-API-001",
        "name": "API测试笔记本",
        "category": "computer",
        "brand": "TestBrand",
        "model": "TestModel",
        "serial_number": "API-SN-001",
        "purchase_date": "2024-01-01",
        "purchase_price": 6000.00,
        "location": "办公室",
        "status": "in_stock",
    }
    response = requests.post(url, headers=get_headers(token), json=data)
    if response.status_code == 201:
        result = response.json()
        print(f"  ✓ 创建资产成功: {result['asset_tag']}")
        return result["id"]
    else:
        print(f"  创建资产失败: {response.status_code} - {response.text}")
        return None


def main():
    print("=" * 80)
    print("接口测试 - 验证数据权限修复效果")
    print("=" * 80)

    print("\n步骤1: 各用户登录获取 token")
    print("-" * 60)
    for user in users:
        print(f"\n[{user['role']} - {user['username']}]")
        token = login(user["username"], user["password"])
        if token:
            tokens[user["username"]] = token
            print(f"  ✓ 登录成功")

    if not tokens:
        print("\n所有用户登录失败，请检查数据库中是否有测试用户")
        return

    print("\n" + "=" * 80)
    print("步骤2: 验证资产数据权限 - 重点检查部门经理能否看到未分配资产")
    print("=" * 80)

    for user in users:
        token = tokens.get(user["username"])
        if not token:
            continue
        print(f"\n[{user['role']} - {user['username']}]")
        print("-" * 60)
        assets = test_asset_list(token, user["role"])

    print("\n" + "=" * 80)
    print("步骤3: 验证资产详情权限 - 部门经理查看未分配资产详情")
    print("=" * 80)

    admin_token = tokens.get("admin")
    if admin_token:
        print("\n[超级管理员] - 先查找一个未分配资产的 ID")
        admin_assets = test_asset_list(admin_token, "超级管理员")
        unassigned_asset = None
        for asset in admin_assets:
            if asset.get("assignee") is None:
                unassigned_asset = asset
                break

        if unassigned_asset:
            asset_id = unassigned_asset["id"]
            asset_tag = unassigned_asset["asset_tag"]
            print(f"\n选择未分配资产: {asset_tag} (ID: {asset_id})")

            for user in users:
                token = tokens.get(user["username"])
                if not token:
                    continue
                print(f"\n[{user['role']} - {user['username']}] 查看资产 {asset_tag} 详情:")
                test_asset_detail(token, asset_id, user["role"])

    print("\n" + "=" * 80)
    print("步骤4: 验证审批单数据权限")
    print("=" * 80)

    for user in users:
        token = tokens.get(user["username"])
        if not token:
            continue
        print(f"\n[{user['role']} - {user['username']}]")
        print("-" * 60)
        test_approval_list(token, user["role"])

    print("\n" + "=" * 80)
    print("步骤5: 验证操作审计日志")
    print("=" * 80)

    admin_token = tokens.get("admin")
    if admin_token:
        print("\n[超级管理员] - 查看操作日志")
        url = f"{BASE_URL}/api/logs/operations?page_size=10"
        response = requests.get(url, headers=get_headers(admin_token))
        if response.status_code == 200:
            result = response.json()
            items = result["items"]
            print(f"  操作日志总数: {result['total']}")
            for item in items[:5]:
                print(f"    - {item['created_at']} | {item['module']} | {item['action']} | {item['operator']}")
        else:
            print(f"  错误: {response.status_code} - {response.text}")

    print("\n" + "=" * 80)
    print("测试完成!")
    print("=" * 80)


if __name__ == "__main__":
    main()
