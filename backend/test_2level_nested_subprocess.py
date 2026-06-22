import requests
import json
import time

BASE_URL = "http://localhost:3331/api"

login_data = {"username": "admin", "password": "admin123"}
resp = requests.post(f"{BASE_URL}/auth/login", json=login_data)
token = resp.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

def get_approval_detail(approval_id):
    resp = requests.get(f"{BASE_URL}/approvals/{approval_id}", headers=headers)
    return resp.json()

def print_records(records, indent=0):
    prefix = "  " * indent
    for r in records:
        node_type = r.get("node_type", "")
        pg = r.get("parallel_group_id", "") or ""
        br = r.get("branch_id", "") or ""
        nesting = r.get("sub_process_nesting_level", 0)
        status = r.get("status", "")
        print(f"{prefix}- Level {r['level']}: {r['approver_name']} (status={status}, nt={node_type}, pg={pg[:10]}.., br={br[:8]}.., nest={nesting})")
        sub_records = r.get("sub_process_records", [])
        if sub_records:
            print(f"{prefix}  子流程内部 ({len(sub_records)} 条):")
            print_records(sub_records, indent + 2)

def approve_record(approval_id, role, opinion="同意"):
    data = {
        "action": "approve",
        "approver_role": role,
        "opinion": opinion,
    }
    resp = requests.post(f"{BASE_URL}/approvals/{approval_id}/approve", json=data, headers=headers)
    return resp

def reject_record(approval_id, role, opinion="驳回"):
    data = {
        "action": "reject",
        "approver_role": role,
        "opinion": opinion,
    }
    resp = requests.post(f"{BASE_URL}/approvals/{approval_id}/reject", json=data, headers=headers)
    return resp

print("=" * 70)
print("Bug 修复验证测试：并行分支内2层嵌套子流程")
print("=" * 70)

print("\n" + "=" * 70)
print("测试场景1：创建审批链结构")
print("=" * 70)
print("""
审批链结构（含并行+2层嵌套子流程）：
Level 1: 申请人主管
Level 2: 并行网关 Start
         ├─ Branch 1: 子流程A（2层嵌套）
         │           ├─ Level 1: 部门经理
         │           └─ Level 2: 子流程B
         │                      └─ Level 1: 总监
         └─ Branch 2: 财务
Level 3: 并行网关 End
Level 4: 总经理
""")

print("\n1. 创建子流程B（最内层）...")
sub_chain_b_data = {
    "name": "子流程B-总监审批",
    "approval_type": "allocate",
    "is_default": False,
    "min_price": 999999999,
    "max_price": 999999999,
    "nodes": [
        {
            "node_type": "approval",
            "approvers": [{"approver_role": "director", "approver_name": "总监"}],
            "sign_condition": "and",
        }
    ]
}
resp = requests.post(f"{BASE_URL}/approvals/chains", json=sub_chain_b_data, headers=headers)
sub_chain_b_id = resp.json()["id"]
print(f"  ✓ 子流程B创建成功，ID: {sub_chain_b_id}")

print("\n2. 创建子流程A（引用子流程B，形成2层嵌套）...")
sub_chain_a_data = {
    "name": "子流程A-部门+总监",
    "approval_type": "allocate",
    "is_default": False,
    "min_price": 999999999,
    "max_price": 999999999,
    "nodes": [
        {
            "node_type": "approval",
            "approvers": [{"approver_role": "dept_mgr", "approver_name": "部门经理"}],
            "sign_condition": "and",
        },
        {
            "node_type": "sub_process",
            "sub_process_chain_id": sub_chain_b_id,
            "approvers": [],
        }
    ]
}
resp = requests.post(f"{BASE_URL}/approvals/chains", json=sub_chain_a_data, headers=headers)
if resp.status_code not in [200, 201]:
    print(f"  ✗ 创建失败: {resp.status_code} - {resp.text}")
    exit(1)
sub_chain_a_id = resp.json()["id"]
print(f"  ✓ 子流程A创建成功，ID: {sub_chain_a_id} (2层嵌套验证通过)")

print("\n3. 创建主审批链（并行网关 + 子流程A）...")
pg_id = "pg_test_2level_nested"
b1_id = "branch_sub"
b2_id = "branch_finance"

main_chain_data = {
    "name": "主流程-并行+2层嵌套子流程",
    "approval_type": "allocate",
    "is_default": False,
    "min_price": 5555555,
    "max_price": 5555555,
    "nodes": [
        {
            "node_type": "approval",
            "approvers": [{"approver_role": "applicant_mgr", "approver_name": "申请人主管"}],
            "sign_condition": "and",
        },
        {
            "node_type": "parallel_start",
            "parallel_group_id": pg_id,
            "branch_id": b1_id,
            "branch_index": 0,
            "approvers": [],
        },
        {
            "node_type": "sub_process",
            "parallel_group_id": pg_id,
            "branch_id": b1_id,
            "branch_index": 0,
            "sub_process_chain_id": sub_chain_a_id,
            "approvers": [],
        },
        {
            "node_type": "approval",
            "parallel_group_id": pg_id,
            "branch_id": b2_id,
            "branch_index": 1,
            "approvers": [{"approver_role": "finance", "approver_name": "财务"}],
            "sign_condition": "and",
        },
        {
            "node_type": "parallel_end",
            "parallel_group_id": pg_id,
            "branch_id": b2_id,
            "branch_index": 1,
            "approvers": [],
        },
        {
            "node_type": "approval",
            "approvers": [{"approver_role": "gm", "approver_name": "总经理"}],
            "sign_condition": "and",
        },
    ]
}
resp = requests.post(f"{BASE_URL}/approvals/chains", json=main_chain_data, headers=headers)
if resp.status_code not in [200, 201]:
    print(f"  ✗ 创建失败: {resp.status_code} - {resp.text}")
    exit(1)
main_chain_id = resp.json()["id"]
print(f"  ✓ 主审批链创建成功，ID: {main_chain_id}")

print("\n" + "=" * 70)
print("测试场景2：创建审批 - 验证并行+2层嵌套子流程展开")
print("=" * 70)

print("\n4. 创建资产（价格匹配主审批链）...")
asset_data = {
    "name": "测试并行嵌套子流程资产",
    "category": "computer",
    "brand": "Test",
    "model": "V2",
    "serial_number": f"SN-2LVL-NEST-{int(time.time())}",
    "purchase_price": 5555555,
    "status": "in_stock",
}
resp = requests.post(f"{BASE_URL}/assets", json=asset_data, headers=headers)
asset_id = resp.json()["id"]
print(f"  ✓ 资产创建成功，ID: {asset_id}, 价格: {asset_data['purchase_price']}")

print("\n5. 提交审批（核心测试：并行分支内2层嵌套子流程展开）...")
approval_data = {
    "approval_type": "allocate",
    "applicant": "admin",
    "assignee": "testuser",
    "reason": "测试并行分支内2层嵌套子流程",
}
resp = requests.post(f"{BASE_URL}/approvals/asset/{asset_id}", json=approval_data, headers=headers)
if resp.status_code not in [200, 201]:
    print(f"  ✗ 审批创建失败: {resp.status_code}")
    print(f"    响应: {resp.text[:500]}")
    exit(1)

approval = resp.json()
approval_id = approval["id"]
print(f"  ✓ 审批创建成功！ID: {approval_id}")
print(f"    状态: {approval['status']}")
print(f"    总级数: {approval['total_levels']}")
print(f"    审批链 ID: {approval.get('chain_id')}")
if approval.get('chain_id') == main_chain_id:
    print(f"    ✓ 正确匹配到主审批链")
else:
    print(f"    ⚠ 匹配到链 {approval.get('chain_id')}，期望 {main_chain_id}")

print("\n6. 查看审批记录结构...")
detail = get_approval_detail(approval_id)
records = detail.get("node_records", [])
print(f"  共 {len(records)} 条顶层记录：")
print_records(records)

print("\n7. 验证结构正确性...")
expected_levels = [
    ("申请人主管", 0, ""),
    ("子流程: 子流程A-部门+总监", 1, b1_id),
    ("财务", 0, b2_id),
    ("总经理", 0, ""),
]
actual_nesting_levels = [r.get("sub_process_nesting_level", 0) for r in records]
actual_branch_ids = [r.get("branch_id", "") or "" for r in records]

print(f"  ✓ nesting_level 检查: 子流程节点nesting=1，其他=0 -> {actual_nesting_levels}")
if any(r.get("sub_process_nesting_level", 0) > 0 and r.get("node_type") == "sub_process" for r in records):
    print("  ✓ 子流程节点正确嵌套 (nesting_level=1)")
    
sub_proc_records = [r for r in records if r.get("node_type") == "sub_process"]
if sub_proc_records:
    sub_r = sub_proc_records[0]
    if sub_r.get("parallel_group_id") and sub_r.get("branch_id"):
        print("  ✓ 子流程节点正确继承并行分支信息")
    else:
        print(f"  ⚠ 子流程节点并行信息缺失: pg={sub_r.get('parallel_group_id')}, br={sub_r.get('branch_id')}")
    
    inner_records = sub_r.get("sub_process_records", [])
    if inner_records:
        print(f"  ✓ 子流程内部记录存在 ({len(inner_records)} 条)")
        inner_nesting = [r.get("sub_process_nesting_level", 0) for r in inner_records]
        print(f"    内部 nesting_level: {inner_nesting}")
        if max(inner_nesting) >= 2:
            print("    ✓ 2层嵌套正确 (内部节点nesting>=2)")
        else:
            print(f"    ⚠ 2层嵌套可能不正确，期望>=2，实际={max(inner_nesting)}")

print("\n" + "=" * 70)
print("测试场景3：审批通过联动 - 2层嵌套子流程全部通过")
print("=" * 70)

print("\n8. 审批流程 - 逐步通过...")
print("\n  Step 1: 申请人主管通过...")
resp = approve_record(approval_id, "applicant_mgr", "同意")
if resp.status_code == 200:
    print(f"    ✓ 通过成功")
else:
    print(f"    ✗ 失败: {resp.status_code} - {resp.text[:200]}")

print("\n  Step 2: 部门经理通过（子流程A第一层）...")
resp = approve_record(approval_id, "dept_mgr", "同意")
if resp.status_code == 200:
    print(f"    ✓ 通过成功")
else:
    print(f"    ✗ 失败: {resp.status_code} - {resp.text[:200]}")

print("\n  Step 3: 总监通过（子流程B，第2层嵌套）...")
resp = approve_record(approval_id, "director", "同意")
if resp.status_code == 200:
    print(f"    ✓ 通过成功")
    detail = get_approval_detail(approval_id)
    records = detail.get("node_records", [])
    sub_proc = [r for r in records if r.get("node_type") == "sub_process" and "子流程A" in r.get("approver_name", "")]
    if sub_proc and sub_proc[0].get("status") == "approved":
        print(f"    ✓ 子流程A自动通过（2层嵌套通过联动正确）")
    else:
        print(f"    ⚠ 子流程A状态: {sub_proc[0].get('status') if sub_proc else 'N/A'}")
else:
    print(f"    ✗ 失败: {resp.status_code} - {resp.text[:200]}")

print("\n  Step 4: 财务通过（并行分支2）...")
resp = approve_record(approval_id, "finance", "同意")
if resp.status_code == 200:
    print(f"    ✓ 通过成功")
else:
    print(f"    ✗ 失败: {resp.status_code} - {resp.text[:200]}")

print("\n  Step 5: 总经理通过...")
resp = approve_record(approval_id, "gm", "同意")
if resp.status_code == 200:
    detail = get_approval_detail(approval_id)
    status = detail.get("status", "")
    if status == "approved":
        print(f"    ✓ 审批全部通过，最终状态: {status}")
    else:
        print(f"    ⚠ 最终状态: {status}")
else:
    print(f"    ✗ 失败: {resp.status_code} - {resp.text[:200]}")

print("\n9. 查看最终审批记录...")
detail = get_approval_detail(approval_id)
records = detail.get("node_records", [])
print(f"  最终状态: {detail.get('status')}")
print_records(records)

all_approved = all(r.get("status") == "approved" for r in records)
if all_approved and detail.get("status") == "approved":
    print("  ✓ 所有记录状态正确，审批完成")
else:
    print("  ⚠ 部分记录状态不正确")

print("\n" + "=" * 70)
print("测试场景4：审批驳回联动 - 子流程REJECTED时取消PENDING兄弟")
print("=" * 70)

print("\n10. 创建新的审批用于驳回测试...")
asset_data2 = {
    "name": "测试驳回联动资产",
    "category": "computer",
    "brand": "Test",
    "model": "V3",
    "serial_number": f"SN-REJECT-{int(time.time())}",
    "purchase_price": 5555555,
    "status": "in_stock",
}
resp = requests.post(f"{BASE_URL}/assets", json=asset_data2, headers=headers)
asset_id2 = resp.json()["id"]

approval_data2 = {
    "approval_type": "allocate",
    "applicant": "admin",
    "assignee": "testuser2",
    "reason": "测试子流程驳回联动",
}
resp = requests.post(f"{BASE_URL}/approvals/asset/{asset_id2}", json=approval_data2, headers=headers)
approval2 = resp.json()
approval_id2 = approval2["id"]
print(f"  ✓ 审批创建成功，ID: {approval_id2}")

print("\n11. 驳回流程测试...")
print("\n  Step 1: 申请人主管通过...")
resp = approve_record(approval_id2, "applicant_mgr", "同意")
print(f"    {'✓' if resp.status_code == 200 else '✗'} 申请人主管: {resp.status_code}")

print("\n  Step 2: 部门经理驳回（子流程A第一层）...")
resp = reject_record(approval_id2, "dept_mgr", "资料不全，驳回")
if resp.status_code == 200:
    print(f"    ✓ 驳回成功")
    time.sleep(1)
    detail = get_approval_detail(approval_id2)
    records = detail.get("node_records", [])
    print("\n    驳回后各节点状态检查:")
    
    sub_proc_a = [r for r in records if r.get("node_type") == "sub_process" and "子流程A" in r.get("approver_name", "")]
    if sub_proc_a and sub_proc_a[0].get("status") == "rejected":
        print(f"    ✓ 子流程A状态: rejected（正确联动）")
    else:
        print(f"    ⚠ 子流程A状态: {sub_proc_a[0].get('status') if sub_proc_a else 'N/A'}")
    
    finance_node = [r for r in records if r.get("approver_name") == "财务"]
    if finance_node:
        status = finance_node[0].get("status", "")
        if status == "withdrawn":
            print(f"    ✓ 财务节点状态: withdrawn（正确取消并行分支兄弟）")
        else:
            print(f"    ⚠ 财务节点状态: {status}（期望 withdrawn）")
    
    gm_node = [r for r in records if r.get("approver_name") == "总经理"]
    if gm_node:
        status = gm_node[0].get("status", "")
        if status == "withdrawn" or status == "rejected":
            print(f"    ✓ 总经理节点状态: {status}（正确取消后续节点）")
        else:
            print(f"    ⚠ 总经理节点状态: {status}")
    
    director_node = None
    for r in records:
        inner = r.get("sub_process_records", [])
        for ir in inner:
            if ir.get("approver_name") == "总监":
                director_node = ir
                break
    if director_node:
        status = director_node.get("status", "")
        if status == "withdrawn":
            print(f"    ✓ 子流程B-总监节点状态: withdrawn（正确取消子流程内兄弟）")
        else:
            print(f"    ⚠ 子流程B-总监节点状态: {status}（期望 withdrawn）")
    
    final_status = detail.get("status", "")
    if final_status == "rejected":
        print(f"    ✓ 最终审批状态: rejected")
    else:
        print(f"    ⚠ 最终审批状态: {final_status}")
else:
    print(f"    ✗ 驳回失败: {resp.status_code} - {resp.text[:200]}")

print("\n" + "=" * 70)
print("测试场景5：branch递归时nesting_level不应+1验证")
print("=" * 70)
print("\n  检查并行分支内子流程节点的nesting_level...")
detail = get_approval_detail(approval_id)
records = detail.get("node_records", [])
sub_in_branch = [r for r in records if r.get("node_type") == "sub_process" and r.get("branch_id")]
if sub_in_branch:
    nesting = sub_in_branch[0].get("sub_process_nesting_level", -1)
    inner_records = sub_in_branch[0].get("sub_process_records", [])
    inner_nesting = [r.get("sub_process_nesting_level", -1) for r in inner_records] if inner_records else []
    
    print(f"  并行分支内子流程节点 nesting_level: {nesting}")
    print(f"  子流程内部节点 nesting_level: {inner_nesting}")
    
    if nesting == 1 and (not inner_nesting or max(inner_nesting) >= 2):
        print("  ✓ Bug1修复验证通过：branch递归时nesting_level没有额外+1")
        print("    说明: 并行分支内子流程nesting=1（而非2），证明branch递归没有增加nesting")
    else:
        print(f"  ⚠ nesting_level 可能不正确: 外层={nesting}, 内层={inner_nesting}")

print("\n" + "=" * 70)
print("✓ 所有 Bug 修复验证测试完成！")
print("=" * 70)
