"""
测试并行分支全部驳回时的即时驳回逻辑
"""
import os
import sys
import json
import urllib.request
import urllib.error

BASE_URL = "http://localhost:8000"
os.environ["ASSET_JWT_SECRET"] = "test-secret-key-parallel-gateway"

def api_call(method, path, data=None, token=None):
    url = BASE_URL + path
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            return e.code, json.loads(body)
        except:
            return e.code, {"detail": body}
    except Exception as e:
        return 0, {"detail": str(e)}

def main():
    print("=== 1. 登录 ===")
    status, resp = api_call("POST", "/api/auth/login", {"username": "admin", "password": "admin123"})
    assert status == 200, f"登录失败: {resp}"
    token = resp["access_token"]
    print(f"✅ 登录成功")

    print("\n=== 2. 创建含并行网关的审批链 ===")
    gid = "pg_reject_test_" + str(os.getpid())
    chain_data = {
        "name": f"驳回测试链-{os.getpid()}",
        "approval_type": "scrap",
        "min_price": 0,
        "max_price": 999999999,
        "nodes": [
            {"node_type": "parallel_start", "parallel_group_id": gid, "approvers": []},
            {"node_type": "approval", "parallel_group_id": gid, "branch_id": "b1", "branch_index": 0,
             "mode": "single", "approvers": [{"approver_role": "财务", "approver_name": "admin"}]},
            {"node_type": "approval", "parallel_group_id": gid, "branch_id": "b2", "branch_index": 1,
             "mode": "single", "approvers": [{"approver_role": "行政", "approver_name": "张三"}]},
            {"node_type": "parallel_end", "parallel_group_id": gid, "approvers": []},
            {"node_type": "approval", "mode": "single", "approvers": [{"approver_role": "总经理", "approver_name": "赵六"}]},
        ],
    }
    status, resp = api_call("POST", "/api/approvals/chains", chain_data, token)
    assert status == 201, f"创建链失败: {resp}"
    chain_id = resp["id"]
    print(f"✅ 审批链创建成功, ID={chain_id}, group_id={gid}")

    print("\n=== 3. 查找匹配的资产并创建审批单 ===")
    status, assets = api_call("GET", "/api/assets?status=in_stock&page_size=100", None, token)
    assert status == 200, f"获取资产失败: {assets}"
    chosen_asset = None
    for a in assets.get("items", []):
        if a.get("purchase_price") and 90000 < a["purchase_price"] < 110000:
            chosen_asset = a
            break
    if not chosen_asset:
        for a in assets.get("items", []):
            if a.get("purchase_price") and a["purchase_price"] > 1000:
                chosen_asset = a
                break
    if not chosen_asset:
        chosen_asset = assets["items"][0]
    print(f"选择资产 #{chosen_asset['id']}: 价格={chosen_asset.get('purchase_price')}")

    ap_data = {
        "approval_type": "scrap",
        "applicant": "admin",
        "assignee": "admin",
        "reason": "测试并行分支驳回",
    }
    status, approval = api_call("POST", f"/api/approvals/asset/{chosen_asset['id']}", ap_data, token)
    assert status in (200, 201), f"创建审批单失败: {approval}"
    approval_id = approval["id"]
    print(f"✅ 审批单创建成功, ID={approval_id}, 状态={approval['status']}")

    status, approval = api_call("GET", f"/api/approvals/{approval_id}", None, token)
    assert status == 200, f"获取审批详情失败: {approval}"
    print(f"已获取审批详情, total_levels={approval.get('total_levels')}")

    print("\n=== 4. 查看所有分支节点记录 ===")
    records = approval.get("node_records", [])
    print(f"节点记录总数: {len(records)}")
    pending_count = 0
    branch_ids = set()
    for r in records:
        tag = ""
        if r.get("branch_id"):
            tag = f" [branch={r.get('branch_id')}, idx={r.get('branch_index')}]"
        print(f"  L{r['level']}: {r['approver_name']} ({r['status']}){tag}")
        if r["status"] == "pending":
            pending_count += 1
        if r.get("branch_id"):
            branch_ids.add(r["branch_id"])
    print(f"待办数量: {pending_count}, 分支数: {len(branch_ids)}")
    assert pending_count >= 2, f"至少应有2个分支待办，实际{pending_count}"

    print("\n=== 5. 分支1驳回，验证整单被即时驳回且分支2待办被取消 ===")
    reject_data = {"opinion": "财务不同意，驳回"}
    status, resp = api_call("POST", f"/api/approvals/{approval_id}/reject", reject_data, token)
    print(f"驳回请求状态: {status}")
    assert status == 200, f"驳回失败: {resp}"
    approval_after = resp
    print(f"审批单状态: {approval_after['status']}")
    assert approval_after["status"] == "rejected", f"分支1驳回后整单应被驳回，实际是 {approval_after['status']}"
    print("✅ 整单已被驳回")

    print("\n=== 6. 验证分支2的待办被置为 WITHDRAWN ===")
    status, approval_detail = api_call("GET", f"/api/approvals/{approval_id}", None, token)
    assert status == 200, f"获取审批详情失败: {approval_detail}"
    all_records = approval_detail.get("node_records", [])
    b2_records = [r for r in all_records if r.get("branch_id") == "b2"]
    print(f"分支2的记录数: {len(b2_records)}")
    for r in b2_records:
        print(f"  L{r['level']}: {r['approver_name']} ({r['status']}) opinion={r.get('opinion')}")
        assert r["status"] == "withdrawn", f"分支2的节点应被置为 withdrawn，实际是 {r['status']}"
    print("✅ 分支2所有待办已被正确取消 (WITHDRAWN)")

    print("\n=== 所有测试通过！ ===")

if __name__ == "__main__":
    main()
