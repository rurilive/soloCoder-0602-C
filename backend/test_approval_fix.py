#!/usr/bin/env python3
import requests
import json

BASE_URL = "http://localhost:8000"

users = [
    {"username": "admin", "password": "admin123", "role": "超级管理员"},
    {"username": "asset_admin", "password": "123456", "role": "资产管理员", "roles": ["asset_admin"]},
    {"username": "dept_mgr", "password": "123456", "role": "研发部经理", "roles": ["dept_manager"]},
    {"username": "emp1", "password": "123456", "role": "研发部普通员工", "roles": ["employee"]},
    {"username": "emp2", "password": "123456", "role": "市场部普通员工", "roles": ["employee"]},
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


def test_approval_list(token, role_desc):
    url = f"{BASE_URL}/api/approvals?page_size=100"
    response = requests.get(url, headers=get_headers(token))
    if response.status_code == 200:
        result = response.json()
        items = result["items"]
        print(f"  列表可见审批单数量: {result['total']}")
        for item in items:
            print(f"    - #{item['id']}: {item['approval_type']} - {item['applicant']} - {item['status']}")
        return items
    else:
        print(f"  错误: {response.status_code} - {response.text}")
        return []


def test_approval_detail(token, approval_id, role_desc):
    url = f"{BASE_URL}/api/approvals/{approval_id}"
    response = requests.get(url, headers=get_headers(token))
    if response.status_code == 200:
        result = response.json()
        print(f"  ✓ 详情可见: #{result['id']}: {result['approval_type']} - {result['applicant']}")
        return True
    else:
        print(f"  ✗ 详情不可见: {response.status_code} - {response.json().get('detail', response.text)}")
        return False


def main():
    print("=" * 80)
    print("审批单权限修复验证 - 重点验证第二个修复")
    print("=" * 80)
    print("\n测试场景:")
    print("  审批链: Level 1 (dept_manager) -> Level 2 (asset_admin)")
    print("  所有审批节点状态都设置为 PENDING")
    print("  审批单 #1: 申请人=李员工(研发部)")
    print("  审批单 #2: 申请人=王员工(市场部)")
    print()
    print("旧逻辑(只匹配 current_level):")
    print("  - asset_admin 看不到任何审批单详情(因为 current_level=1, 只匹配 level 1)")
    print("新逻辑(匹配所有 PENDING 节点):")
    print("  - asset_admin 能看到审批单详情(因为 level 2 也是 PENDING)")
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
    print("步骤2: 验证审批单列表权限")
    print("=" * 80)

    approval_ids = []
    for user in users:
        token = tokens.get(user["username"])
        if not token:
            continue
        print(f"\n[{user['role']} - {user['username']}]")
        print("-" * 60)
        items = test_approval_list(token, user["role"])
        if not approval_ids and items:
            approval_ids = [item["id"] for item in items]

    print("\n" + "=" * 80)
    print("步骤3: 验证审批单详情权限 - 重点测试资产管理员")
    print("=" * 80)

    if not approval_ids:
        print("\n没有审批单数据，请先运行 create_test_approvals.py")
        return

    for approval_id in approval_ids:
        print(f"\n--- 审批单 #{approval_id} ---")
        for user in users:
            token = tokens.get(user["username"])
            if not token:
                continue
            print(f"\n[{user['role']} - {user['username']}]")
            result = test_approval_detail(token, approval_id, user["role"])

            # 验证关键点
            if "资产管理员" in user["role"] and result:
                print(f"    ✓ 修复验证: 资产管理员能看到审批单 #{approval_id} 详情，新逻辑生效!")
            if "资产管理员" in user["role"] and not result:
                print(f"    ✗ 修复验证: 资产管理员仍看不到审批单 #{approval_id} 详情，修复未生效!")

    print("\n" + "=" * 80)
    print("验证总结:")
    print("=" * 80)
    print("\n资产管理员(asset_admin)角色权限:")
    print("  - 拥有 asset_admin 角色")
    print("  - 审批单所有节点都是 PENDING 状态")
    print("  - 按照新逻辑，只要用户角色匹配任意 PENDING 节点的 approver_role，就能查看")
    print("  - 所以资产管理员应该能看到所有审批单的详情")
    print("\n如果资产管理员能看到审批单详情，说明第二个修复生效!")
    print("=" * 80)


if __name__ == "__main__":
    main()
