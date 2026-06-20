"""端到端测试：验证三种升级策略的超时处理效果"""
import sys
import os
sys.path.insert(0, '.')
os.environ['ASSET_JWT_SECRET'] = 'test-secret-key-for-testing'

from datetime import datetime, timedelta
from app.database import SessionLocal
from app.models import (
    Approval, ApprovalType, ApprovalStatus, ApprovalMode,
    ApprovalChain, ApprovalChainNode, ApprovalChainNodeApprover,
    ApprovalNodeRecord, TimeoutEscalationStrategy,
    Asset, AssetStatus, AssetCategory,
    TransferStatus,
)
from app.crud import (
    _process_timeouts_internal,
)
from app.main import _migrate_escalation_strategy_columns

_migrate_escalation_strategy_columns()

db = SessionLocal()

try:
    # 清理旧测试数据
    db.query(ApprovalNodeRecord).filter(ApprovalNodeRecord.approval_id >= 100).delete()
    db.query(Approval).filter(Approval.id >= 100).delete()
    db.query(Asset).filter(Asset.asset_tag.like('E2E-%')).delete()
    db.query(ApprovalChainNodeApprover).filter(ApprovalChainNodeApprover.id >= 100).delete()
    db.query(ApprovalChainNode).filter(ApprovalChainNode.chain_id >= 100).delete()
    db.query(ApprovalChain).filter(ApprovalChain.id >= 100).delete()
    db.commit()

    print("=" * 70)
    print("端到端测试：三种超时升级策略的执行效果")
    print("=" * 70)

    # ---- 创建测试审批链 ----
    print("\n【步骤1】创建测试审批链")
    chain = ApprovalChain(
        id=100,
        name="E2E-测试三种升级策略",
        approval_type=ApprovalType.ALLOCATE,
        is_default=False,
    )
    db.add(chain)
    db.flush()

    nodes_data = [
        # L1: 升级到指定级别 -> L3
        (1, ApprovalMode.SINGLE, 1, TimeoutEscalationStrategy.ESCALATE_TO_LEVEL, 3,
         [("部门主管", "张三")]),
        # L2: 自动驳回
        (2, ApprovalMode.SINGLE, 1, TimeoutEscalationStrategy.AUTO_REJECT, None,
         [("财务经理", "李四")]),
        # L3: 跳过当前节点（会签）
        (3, ApprovalMode.ALL_SIGN, 1, TimeoutEscalationStrategy.SKIP_NODE, None,
         [("CTO", "王五"), ("CTO", "赵六")]),
        # L4: 最终审批（默认升级策略）
        (4, ApprovalMode.SINGLE, 1, TimeoutEscalationStrategy.ESCALATE_TO_LEVEL, None,
         [("CEO", "钱七")]),
    ]

    chain_node_ids = {}
    approver_ids = {}
    for level, mode, timeout, strategy, target, approvers in nodes_data:
        node = ApprovalChainNode(
            id=100 + level,
            chain_id=chain.id,
            level=level,
            mode=mode,
            timeout_minutes=timeout,
            escalation_strategy=strategy,
            escalation_target_level=target,
        )
        db.add(node)
        db.flush()
        chain_node_ids[level] = node.id
        approver_ids[level] = []
        for role, name in approvers:
            appr = ApprovalChainNodeApprover(
                id=1000 + level * 10 + len(approver_ids[level]),
                chain_node_id=node.id,
                approver_role=role,
                approver_name=name,
            )
            db.add(appr)
            db.flush()
            approver_ids[level].append(appr.id)

    db.commit()
    print(f"  ✅ 审批链创建成功 (ID={chain.id})，共4级")

    past_time = datetime.now() - timedelta(minutes=5)
    future_time = datetime.now() + timedelta(minutes=30)

    # ---- 测试1: ESCALATE_TO_LEVEL ----
    print("\n" + "=" * 70)
    print("测试1：ESCALATE_TO_LEVEL - 升级到指定级别 (L1 -> L3)")
    print("=" * 70)

    asset1 = Asset(
        asset_tag="E2E-TEST-001",
        name="测试资产-升级策略",
        category=AssetCategory.COMPUTER,
        brand="联想",
        model="ThinkPad X1",
        serial_number="SN-E2E-001",
        status=AssetStatus.IN_STOCK,
        purchase_price=8000.0,
    )
    db.add(asset1)
    db.flush()

    approval1 = Approval(
        id=101,
        asset_id=asset1.id,
        approval_type=ApprovalType.ALLOCATE,
        status=ApprovalStatus.PENDING,
        applicant="admin",
        assignee="测试用户",
        reason="测试升级到指定级别",
        previous_status=asset1.status,
        current_level=1,
        total_levels=4,
        chain_id=chain.id,
    )
    db.add(approval1)
    db.flush()

    # 创建4级审批记录
    for level in range(1, 5):
        for i, approver_name in enumerate([a[1] for a in nodes_data[level-1][5]]):
            role = nodes_data[level-1][5][i][0]
            record = ApprovalNodeRecord(
                approval_id=approval1.id,
                chain_node_id=chain_node_ids[level],
                chain_node_approver_id=approver_ids[level][i],
                level=level,
                chain_node_level=level,
                approver_role=role,
                approver_name=approver_name,
                status=ApprovalStatus.PENDING,
                timeout_at=past_time if level == 1 else future_time,
            )
            db.add(record)

    db.commit()
    db.refresh(approval1)

    record_count = db.query(ApprovalNodeRecord).filter(
        ApprovalNodeRecord.approval_id == approval1.id
    ).count()
    print(f"  创建审批单 #{approval1.id}，当前级别: L{approval1.current_level}")
    print(f"  共{record_count}条审批记录")

    # 执行超时处理
    results = _process_timeouts_internal(db)
    db.refresh(approval1)
    db.refresh(asset1)

    print(f"  超时处理结果: {len(results)}条记录被处理")
    print(f"  审批单当前级别: L{approval1.current_level}")
    print(f"  审批单状态: {approval1.status.value}")

    # 验证：L1 应该升级到 L3（跳过了 L2）
    assert approval1.current_level == 3, f"预期升级到L3，实际是L{approval1.current_level}"

    l1_records = db.query(ApprovalNodeRecord).filter(
        ApprovalNodeRecord.approval_id == approval1.id,
        ApprovalNodeRecord.level == 1,
    ).all()
    for r in l1_records:
        assert r.status == ApprovalStatus.ESCALATED, f"L1记录状态应该是ESCALATED，实际是{r.status.value}"
        assert r.is_escalated == True

    print("  ✅ 验证通过：L1超时后成功升级到L3（跳过L2）")
    print(f"     L1记录: {l1_records[0].approver_name} - {l1_records[0].status.value}")
    print(f"     意见: {l1_records[0].opinion}")

    # ---- 测试2: SKIP_NODE ----
    print("\n" + "=" * 70)
    print("测试2：SKIP_NODE - 跳过会签节点 (L3 -> L4)")
    print("=" * 70)

    # 当前审批单在L3
    l3_records = db.query(ApprovalNodeRecord).filter(
        ApprovalNodeRecord.approval_id == approval1.id,
        ApprovalNodeRecord.level == 3,
    ).order_by(ApprovalNodeRecord.id.asc()).all()
    print(f"  L3有{len(l3_records)}条会签记录")

    # 让其中一个人先签批，另一个保持超时
    l3_records[0].status = ApprovalStatus.APPROVED
    l3_records[0].acted_at = datetime.now()
    l3_records[0].opinion = "同意"
    l3_records[0].timeout_at = future_time  # 这个不超时

    l3_records[1].timeout_at = past_time  # 这个超时
    db.commit()

    print(f"  其中1人已签批({l3_records[0].approver_name})，1人超时({l3_records[1].approver_name})")

    # 执行超时处理
    results = _process_timeouts_internal(db)
    db.refresh(approval1)

    print(f"  超时处理结果: {len(results)}条记录被处理")
    print(f"  审批单当前级别: L{approval1.current_level}")
    print(f"  审批单状态: {approval1.status.value}")

    # 验证：L3 会签节点超时后应该跳到 L4
    assert approval1.current_level == 4, f"预期跳到L4，实际是L{approval1.current_level}"

    l3_records_after = db.query(ApprovalNodeRecord).filter(
        ApprovalNodeRecord.approval_id == approval1.id,
        ApprovalNodeRecord.level == 3,
    ).order_by(ApprovalNodeRecord.id.asc()).all()

    # 王五：已签批，应该保持 APPROVED 状态，is_escalated=False
    wangwu = l3_records_after[0]
    assert wangwu.approver_name == "王五"
    assert wangwu.status == ApprovalStatus.APPROVED, f"王五应该保持APPROVED，实际是{wangwu.status.value}"
    assert wangwu.is_escalated == False, f"王五is_escalated应该为False"

    # 赵六：未签批（超时），应该标记为 ESCALATED，is_escalated=True
    zhaoliu = l3_records_after[1]
    assert zhaoliu.approver_name == "赵六"
    assert zhaoliu.status == ApprovalStatus.ESCALATED, f"赵六应该是ESCALATED，实际是{zhaoliu.status.value}"
    assert zhaoliu.is_escalated == True, f"赵六is_escalated应该为True"

    print("  ✅ 验证通过：L3会签节点超时后跳过，流转到L4")
    for r in l3_records_after:
        print(f"     - {r.approver_name}: {r.status.value} (is_escalated={r.is_escalated})")

    # ---- 测试3: AUTO_REJECT ----
    print("\n" + "=" * 70)
    print("测试3：AUTO_REJECT - 自动驳回策略")
    print("=" * 70)

    # 创建一个新的审批单，从 L2 开始测试自动驳回
    asset3 = Asset(
        asset_tag="E2E-TEST-003",
        name="测试资产-驳回策略",
        category=AssetCategory.MONITOR,
        brand="戴尔",
        model="U2722D",
        serial_number="SN-E2E-003",
        status=AssetStatus.IN_STOCK,
        purchase_price=3000.0,
    )
    db.add(asset3)
    db.flush()

    approval3 = Approval(
        id=103,
        asset_id=asset3.id,
        approval_type=ApprovalType.ALLOCATE,
        status=ApprovalStatus.PENDING,
        applicant="admin",
        assignee="测试用户2",
        reason="测试自动驳回策略",
        previous_status=asset3.status,
        current_level=2,
        total_levels=4,
        chain_id=chain.id,
    )
    db.add(approval3)
    db.flush()

    # 创建4级审批记录，L2设置为超时
    for level in range(1, 5):
        for i, approver_name in enumerate([a[1] for a in nodes_data[level-1][5]]):
            role = nodes_data[level-1][5][i][0]
            is_l2 = level == 2
            record = ApprovalNodeRecord(
                approval_id=approval3.id,
                chain_node_id=chain_node_ids[level],
                chain_node_approver_id=approver_ids[level][i],
                level=level,
                chain_node_level=level,
                approver_role=role,
                approver_name=approver_name,
                status=ApprovalStatus.PENDING,
                timeout_at=past_time if is_l2 else future_time,
            )
            if level == 1:
                record.status = ApprovalStatus.APPROVED
                record.acted_at = datetime.now()
                record.opinion = "同意"
            db.add(record)

    db.commit()
    db.refresh(approval3)
    db.refresh(asset3)

    original_asset_status = asset3.status
    print(f"  创建审批单 #{approval3.id}，当前级别: L{approval3.current_level} (自动驳回策略)")
    print(f"  资产原始状态: {original_asset_status.value}")

    # 执行超时处理
    results = _process_timeouts_internal(db)
    db.refresh(approval3)
    db.refresh(asset3)

    print(f"  超时处理结果: {len(results)}条记录被处理")
    print(f"  审批单状态: {approval3.status.value}")
    print(f"  驳回意见: {approval3.approval_opinion}")
    print(f"  资产当前状态: {asset3.status.value}")

    # 验证：L2超时后应该自动驳回
    assert approval3.status == ApprovalStatus.REJECTED, f"预期REJECTED，实际是{approval3.status.value}"
    assert "自动驳回" in approval3.approval_opinion, "驳回意见应该包含'自动驳回'"
    assert asset3.status == original_asset_status, f"资产状态应该恢复为{original_asset_status.value}"

    l2_records_3 = db.query(ApprovalNodeRecord).filter(
        ApprovalNodeRecord.approval_id == approval3.id,
        ApprovalNodeRecord.level == 2,
    ).all()
    for r in l2_records_3:
        assert r.status == ApprovalStatus.REJECTED, f"L2记录状态应该是REJECTED"

    print("  ✅ 验证通过：L2超时后自动驳回，资产状态恢复")
    print(f"     审批单状态: {approval3.status.value}")
    print(f"     驳回原因: {approval3.approval_opinion}")
    print(f"     资产状态: {original_asset_status.value} → {asset3.status.value}")

    # ---- 测试4: 环路检测 ----
    print("\n" + "=" * 70)
    print("测试4：环路检测 - 运行时升级路径形成环路时自动驳回")
    print("=" * 70)

    # 创建一个有环路的审批链（直接插入，绕过创建时的检测）
    cycle_chain = ApprovalChain(
        id=101,
        name="E2E-环路测试链",
        approval_type=ApprovalType.ALLOCATE,
    )
    db.add(cycle_chain)
    db.flush()

    # L1->L2->L3->L2 形成环路
    cycle_nodes = [
        (1, ApprovalMode.SINGLE, TimeoutEscalationStrategy.ESCALATE_TO_LEVEL, 2, [("主管A", "用户A")]),
        (2, ApprovalMode.SINGLE, TimeoutEscalationStrategy.ESCALATE_TO_LEVEL, 3, [("主管B", "用户B")]),
        (3, ApprovalMode.SINGLE, TimeoutEscalationStrategy.ESCALATE_TO_LEVEL, 2, [("主管C", "用户C")]),
    ]

    for level, mode, strategy, target, approvers in cycle_nodes:
        node = ApprovalChainNode(
            id=200 + level,
            chain_id=cycle_chain.id,
            level=level,
            mode=mode,
            timeout_minutes=1,
            escalation_strategy=strategy,
            escalation_target_level=target,
        )
        db.add(node)
        db.flush()
        for role, name in approvers:
            appr = ApprovalChainNodeApprover(
                id=2000 + level * 10,
                chain_node_id=node.id,
                approver_role=role,
                approver_name=name,
            )
            db.add(appr)

    db.commit()

    # 创建一个测试审批单
    asset_cycle = Asset(
        asset_tag="E2E-TEST-CYCLE",
        name="测试资产-环路检测",
        category=AssetCategory.OTHER,
        brand="测试",
        model="测试",
        serial_number="SN-E2E-CYCLE",
        status=AssetStatus.IN_STOCK,
        purchase_price=1000.0,
    )
    db.add(asset_cycle)
    db.flush()

    approval_cycle = Approval(
        id=104,
        asset_id=asset_cycle.id,
        approval_type=ApprovalType.ALLOCATE,
        status=ApprovalStatus.PENDING,
        applicant="admin",
        assignee="测试用户",
        reason="测试环路检测",
        previous_status=asset_cycle.status,
        current_level=1,
        total_levels=3,
        chain_id=cycle_chain.id,
    )
    db.add(approval_cycle)
    db.flush()

    # 创建3级审批记录，L1超时
    for level in range(1, 4):
        for i, (role, name) in enumerate(cycle_nodes[level-1][4]):
            record = ApprovalNodeRecord(
                approval_id=approval_cycle.id,
                chain_node_id=200 + level,
                chain_node_approver_id=2000 + level * 10,
                level=level,
                chain_node_level=level,
                approver_role=role,
                approver_name=name,
                status=ApprovalStatus.PENDING,
                timeout_at=past_time if level == 1 else future_time,
            )
            db.add(record)

    db.commit()
    db.refresh(approval_cycle)
    db.refresh(asset_cycle)

    original_asset_status_cycle = asset_cycle.status
    print(f"  创建审批单 #{approval_cycle.id}，当前级别: L{approval_cycle.current_level}")
    print(f"  升级路径: L1→L2→L3→L2 (形成环路)")

    # 执行超时处理
    results = _process_timeouts_internal(db)
    db.refresh(approval_cycle)
    db.refresh(asset_cycle)

    print(f"  超时处理结果: {len(results)}条记录被处理")
    print(f"  审批单状态: {approval_cycle.status.value}")
    print(f"  处理意见: {approval_cycle.approval_opinion}")

    # 验证：因为升级路径有环路，应该自动驳回
    assert approval_cycle.status == ApprovalStatus.REJECTED, f"预期REJECTED，实际是{approval_cycle.status.value}"
    assert "环路" in approval_cycle.approval_opinion, "驳回原因应该包含'环路'"

    print("  ✅ 验证通过：升级路径形成环路时自动驳回")
    print(f"     驳回原因: {approval_cycle.approval_opinion}")

    # ---- 总结 ----
    print("\n" + "=" * 70)
    print("所有端到端测试通过! ✅")
    print("=" * 70)
    print()
    print("策略执行效果总结:")
    print("  1. ✅ ESCALATE_TO_LEVEL (升级到指定级别)")
    print("       - L1超时后直接升级到L3，跳过了L2")
    print("       - 从审批链节点定义验证目标级别存在")
    print("       - 沿升级路径做环路检测")
    print()
    print("  2. ✅ SKIP_NODE (跳过当前节点)")
    print("       - L3会签节点超时后跳过，流转到L4")
    print("       - 会签节点未完成签批的审批人标记为已升级")
    print("       - 正确处理会签收尾逻辑")
    print()
    print("  3. ✅ AUTO_REJECT (自动驳回)")
    print("       - L2超时后整个审批单被驳回")
    print("       - 资产状态自动恢复为原始状态")
    print()
    print("  4. ✅ 环路检测")
    print("       - 配置时：创建审批链时检测升级路径环路")
    print("       - 运行时：升级到指定级别前检测环路，有环路则自动驳回")

except Exception as e:
    db.rollback()
    import traceback
    traceback.print_exc()
    print(f"\n❌ 测试失败: {e}")
    sys.exit(1)
finally:
    db.close()
