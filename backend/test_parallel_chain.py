import os
import sys
import json
import urllib.request
import urllib.error

BASE_URL = "http://localhost:8000"

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
    print(f"状态: {status}")
    if status != 200:
        print(f"错误: {resp}")
        return 1
    token = resp["access_token"]
    print(f"登录成功, token 长度: {len(token)}")

    print("\n=== 2. 获取资产信息 ===")
    status, asset_resp = api_call("GET", "/api/assets/1", None, token)
    if status == 200:
        print(f"资产 #{asset_resp.get('id')}: 价格={asset_resp.get('purchase_price')}, 状态={asset_resp.get('status')}")
    else:
        print(f"获取资产失败: {asset_resp}")

    print("\n=== 3. 创建含并行网关的审批链 ===")
    chain_data = {
        "name": "测试并行审批链-" + str(os.getpid()),
        "approval_type": "allocate",
        "nodes": [
            {"node_type": "approval", "mode": "single", "approvers": [{"approver_role": "部门主管", "approver_name": "张三"}]},
            {"node_type": "parallel_start", "parallel_group_id": "pg_test_001", "approvers": []},
            {"node_type": "approval", "parallel_group_id": "pg_test_001", "branch_id": "branch_001", "branch_index": 0, "mode": "single", "approvers": [{"approver_role": "财务", "approver_name": "李四"}]},
            {"node_type": "approval", "parallel_group_id": "pg_test_001", "branch_id": "branch_002", "branch_index": 1, "mode": "single", "approvers": [{"approver_role": "行政", "approver_name": "王五"}]},
            {"node_type": "parallel_end", "parallel_group_id": "pg_test_001", "approvers": []},
            {"node_type": "approval", "mode": "single", "approvers": [{"approver_role": "总经理", "approver_name": "赵六"}]},
        ],
    }
    status, resp = api_call("POST", "/api/approvals/chains", chain_data, token)
    print(f"状态: {status}")
    print(f"响应: {json.dumps(resp, ensure_ascii=False, indent=2)[:2000]}")
    
    if status != 201:
        print("\n❌ 创建失败")
        return 1
    
    chain_id = resp["id"]
    nodes = resp.get("nodes", [])
    print(f"\n✅ 创建成功! 链ID: {chain_id}, 节点数: {len(nodes)}")
    for n in nodes:
        print(f"  L{n['level']}: {n['node_type']} "
              f"(group={n.get('parallel_group_id')}, "
              f"branch={n.get('branch_id')}, "
              f"idx={n.get('branch_index')})")
    
    print("\n=== 3. 验证并行结束节点有 group_id ===")
    end_node = next((n for n in nodes if n["node_type"] == "parallel_end"), None)
    if end_node and end_node.get("parallel_group_id"):
        print(f"✅ 并行结束节点 group_id: {end_node['parallel_group_id']}")
    else:
        print(f"❌ 并行结束节点 group_id 为空: {end_node}")
        return 1

    print("\n=== 4. 使用此审批链创建审批单 ===")
    approval_data = {
        "approval_type": "allocate",
        "applicant": "admin",
        "assignee": "张三",
        "reason": "测试并行审批",
    }
    status, resp = api_call("POST", "/api/approvals/asset/1", approval_data, token)
    print(f"状态: {status}")
    if status not in (200, 201):
        print(f"错误: {json.dumps(resp, ensure_ascii=False)}")
        return 1
    
    approval_id = resp.get("id")
    print(f"✅ 审批单创建成功, ID: {approval_id}")
    print(f"   当前状态: {resp.get('status')}")
    print(f"   当前级别: {resp.get('current_level')}")
    print(f"   总级别: {resp.get('total_levels')}")
    
    node_records = resp.get("node_records", [])
    print(f"\n审批节点记录数: {len(node_records)}")
    for r in node_records[:10]:
        print(f"  L{r['level']}: {r['approver_name']} ({r['status']}) "
              f"[group={r.get('parallel_group_id')}, branch={r.get('branch_id')}, idx={r.get('branch_index')}]")
    if len(node_records) > 10:
        print(f"  ... 还有 {len(node_records) - 10} 条")

    print("\n=== 5. 检查分支是否独立激活 ===")
    pending_records = [r for r in node_records if r["status"] == "pending" and r.get("branch_id")]
    branches = set(r["branch_id"] for r in pending_records)
    print(f"待办分支数: {len(branches)}")
    if len(branches) >= 2:
        print(f"✅ 多个分支同时激活: {branches}")
    else:
        print(f"⚠️  只有 {len(branches)} 个分支激活: {branches}")

    print("\n=== 所有测试通过! ===")
    return 0

if __name__ == "__main__":
    sys.exit(main())
