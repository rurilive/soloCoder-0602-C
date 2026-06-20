"""
验证并行网关功能的测试脚本
"""
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

def login():
    status, resp = api_call("POST", "/api/auth/login", {"username": "admin", "password": "admin123"})
    assert status == 200, f"登录失败: {resp}"
    return resp["access_token"]

def test_1_create_parallel_chain(token):
    """测试1: 创建含并行网关的审批链，验证 parallel_end 有 group_id"""
    print("\n=== 测试1: 创建含并行网关的审批链 ===")
    gid = "pg_test_" + str(os.getpid())
    chain_data = {
        "name": f"并行测试链-{os.getpid()}",
        "approval_type": "scrap",
        "min_price": 99999,
        "max_price": 99999,
        "nodes": [
            {"node_type": "approval", "mode": "single", "approvers": [{"approver_role": "部门主管", "approver_name": "张三"}]},
            {"node_type": "parallel_start", "parallel_group_id": gid, "approvers": []},
            {"node_type": "approval", "parallel_group_id": gid, "branch_id": "b1", "branch_index": 0, "mode": "single", "approvers": [{"approver_role": "财务", "approver_name": "李四"}]},
            {"node_type": "approval", "parallel_group_id": gid, "branch_id": "b2", "branch_index": 1, "mode": "single", "approvers": [{"approver_role": "行政", "approver_name": "王五"}]},
            {"node_type": "parallel_end", "parallel_group_id": gid, "approvers": []},
            {"node_type": "approval", "mode": "single", "approvers": [{"approver_role": "总经理", "approver_name": "赵六"}]},
        ],
    }
    status, resp = api_call("POST", "/api/approvals/chains", chain_data, token)
    print(f"状态: {status}")
    assert status == 201, f"创建失败: {resp}"
    
    chain_id = resp["id"]
    nodes = resp["nodes"]
    print(f"链ID: {chain_id}, 节点数: {len(nodes)}")
    
    end_node = next((n for n in nodes if n["node_type"] == "parallel_end"), None)
    assert end_node is not None, "找不到 parallel_end 节点"
    assert end_node.get("parallel_group_id") == gid, f"parallel_end 的 group_id 错误: {end_node.get('parallel_group_id')}"
    print(f"✅ parallel_end 节点 group_id 正确: {end_node['parallel_group_id']}")
    
    return chain_id, gid

def test_2_deadlock_detection(token):
    """测试2: 死锁检测 - 只有并行开始没有结束应该报错"""
    print("\n=== 测试2: 死锁检测 - 缺少并行结束节点 ===")
    gid = "pg_deadlock_" + str(os.getpid())
    chain_data = {
        "name": f"死锁测试链-{os.getpid()}",
        "approval_type": "scrap",
        "nodes": [
            {"node_type": "approval", "mode": "single", "approvers": [{"approver_role": "主管", "approver_name": "张三"}]},
            {"node_type": "parallel_start", "parallel_group_id": gid, "approvers": []},
            {"node_type": "approval", "parallel_group_id": gid, "branch_id": "b1", "branch_index": 0, "mode": "single", "approvers": [{"approver_role": "财务", "approver_name": "李四"}]},
        ],
    }
    status, resp = api_call("POST", "/api/approvals/chains", chain_data, token)
    print(f"状态: {status}")
    assert status != 201, "死锁检测失效：只有并行开始没有结束也创建成功了"
    print(f"✅ 死锁检测生效，拒绝创建: {resp.get('detail', '未知错误')}")

def test_3_check_branch_all_rejected_logic():
    """测试3: 验证 check_branch_all_rejected 逻辑 - 只有全部驳回才返回 True"""
    print("\n=== 测试3: check_branch_all_rejected 逻辑验证 ===")
    sys.path.insert(0, '/data/projects/work/soloCoder-0602/repos/c/backend')
    os.environ.setdefault("ASSET_JWT_SECRET", "test")
    from app.parallel_engine import check_branch_all_rejected
    from app.models import ApprovalStatus
    
    class FakeRecord:
        def __init__(self, branch_id, status, transfer_status=None):
            self.branch_id = branch_id
            self.status = status
            self.transfer_status = transfer_status
    
    # 测试1: 全部驳回 -> True
    records = [
        FakeRecord("b1", ApprovalStatus.REJECTED),
        FakeRecord("b1", ApprovalStatus.REJECTED),
    ]
    result = check_branch_all_rejected(records, "b1")
    assert result == True, f"全部驳回应该返回 True，实际是 {result}"
    print("✅ 全部驳回 -> True 正确")
    
    # 测试2: 部分驳回部分通过 -> False
    records = [
        FakeRecord("b1", ApprovalStatus.REJECTED),
        FakeRecord("b1", ApprovalStatus.APPROVED),
    ]
    result = check_branch_all_rejected(records, "b1")
    assert result == False, f"部分驳回应该返回 False，实际是 {result}"
    print("✅ 部分驳回部分通过 -> False 正确")
    
    # 测试3: 有待办 -> False
    records = [
        FakeRecord("b1", ApprovalStatus.REJECTED),
        FakeRecord("b1", ApprovalStatus.PENDING),
    ]
    result = check_branch_all_rejected(records, "b1")
    assert result == False, f"有待办应该返回 False，实际是 {result}"
    print("✅ 有待办 -> False 正确")
    
    # 测试4: 全部通过 -> False
    records = [
        FakeRecord("b1", ApprovalStatus.APPROVED),
        FakeRecord("b1", ApprovalStatus.APPROVED),
    ]
    result = check_branch_all_rejected(records, "b1")
    assert result == False, f"全部通过应该返回 False，实际是 {result}"
    print("✅ 全部通过 -> False 正确")

def test_4_function_signature_compatibility():
    """测试4: 函数签名兼容性 - 接受 group_id 字符串和 list 类型 chain_nodes"""
    print("\n=== 测试4: 函数签名兼容性验证 ===")
    sys.path.insert(0, '/data/projects/work/soloCoder-0602/repos/c/backend')
    from app.parallel_engine import (
        check_parallel_group_ready_to_merge,
        check_any_branch_rejected,
        check_branch_complete,
    )
    from app.models import ApprovalStatus, ChainNodeType, ApprovalMode, ApprovalChainNode
    
    # 用列表类型的 chain_nodes 调用
    chain_nodes_list = []
    records = []
    
    # 验证函数存在且能被调用（即使返回 False 也没关系，只要签名兼容）
    try:
        result = check_branch_complete(records, "b1", chain_nodes_list)
        print(f"✅ check_branch_complete 接受 list 类型参数, 返回: {result}")
    except TypeError as e:
        print(f"❌ check_branch_complete 签名不兼容: {e}")
        raise
    
    try:
        result = check_parallel_group_ready_to_merge(records, "pg_xxx", chain_nodes_list)
        print(f"✅ check_parallel_group_ready_to_merge 接受 (records, group_id: str, chain_nodes: list), 返回: {result}")
    except TypeError as e:
        print(f"❌ check_parallel_group_ready_to_merge 签名不兼容: {e}")
        raise
    
    try:
        result = check_any_branch_rejected(records, "pg_xxx")
        print(f"✅ check_any_branch_rejected 接受 (records, group_id: str) 2个参数, 返回: {result}")
    except TypeError as e:
        print(f"❌ check_any_branch_rejected 签名不兼容: {e}")
        raise
    
    try:
        result = check_any_branch_rejected(records, "pg_xxx", chain_nodes_list)
        print(f"✅ check_any_branch_rejected 接受 (records, group_id: str, chain_nodes: list) 3个参数, 返回: {result}")
    except TypeError as e:
        print(f"❌ check_any_branch_rejected 3参数签名不兼容: {e}")
        raise

def main():
    print("=== 并行网关功能修复验证 ===")
    
    token = login()
    print("登录成功")
    
    test_1_create_parallel_chain(token)
    test_2_deadlock_detection(token)
    test_3_check_branch_all_rejected_logic()
    test_4_function_signature_compatibility()
    
    print("\n=== 所有测试通过! ===")

if __name__ == "__main__":
    os.environ["ASSET_JWT_SECRET"] = "test-secret-key-parallel-gateway"
    main()
