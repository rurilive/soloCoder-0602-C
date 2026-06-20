"""测试升级策略的核心逻辑"""
import sys
import os
sys.path.insert(0, '.')
os.environ['ASSET_JWT_SECRET'] = 'test-secret-key-for-testing'

from datetime import datetime, timedelta
from app.database import SessionLocal, Base, engine
from app.models import (
    Approval, ApprovalType, ApprovalStatus, ApprovalMode,
    ApprovalChain, ApprovalChainNode, ApprovalChainNodeApprover,
    ApprovalNodeRecord, TimeoutEscalationStrategy,
    Asset, AssetStatus, AssetCategory,
)
from app.crud import (
    _get_chain_node_map,
    _chain_node_level_to_record_level,
    _detect_escalation_cycle,
    _escalation_resolve_target_level,
    create_approval_chain,
)
from app.schemas import (
    ApprovalChainCreate, ChainNodeCreate, ChainNodeApproverCreate,
)
from app.condition_engine import detect_cycle
from app.auth import get_password_hash  # noqa: F401
from app.main import _migrate_escalation_strategy_columns

# 执行数据迁移
_migrate_escalation_strategy_columns()

db = SessionLocal()

try:
    # 清理旧测试数据
    db.query(ApprovalNodeRecord).delete()
    db.query(Approval).delete()
    db.query(Asset).delete()
    db.query(ApprovalChainNodeApprover).delete()
    db.query(ApprovalChainNode).delete()
    db.query(ApprovalChain).delete()
    db.commit()

    print("=" * 60)
    print("测试1: 环路检测 - 升级路径纳入配置时检测")
    print("=" * 60)

    # 测试 detect_cycle 函数是否将 escalation_target_level 纳入环路检测
    test_nodes_for_cycle = []
    for i in range(1, 5):
        node = ApprovalChainNode(
            id=i,
            chain_id=0,
            level=i,
            mode=ApprovalMode.SINGLE,
            timeout_minutes=5,
            default_next_level=None,
            escalation_strategy=TimeoutEscalationStrategy.ESCALATE_TO_LEVEL,
            escalation_target_level=None,
            conditions=[],
        )
        test_nodes_for_cycle.append(node)

    # 基线：没有条件、没有默认下一级、没有升级目标时，线性链路 L1→L2→L3→L4 不会有环路
    cycle_path = detect_cycle(test_nodes_for_cycle)
    has_cycle = cycle_path is not None
    print(f"  基线: 4级线性链路(无特殊配置)")
    print(f"    有环路: {has_cycle} (预期: False)")
    assert not has_cycle, "纯线性链路不应该有环路"
    print("  ✅ 基线测试通过")

    # 设置 L1 升级到 L3, L3 升级到 L1: 升级路径形成环路
    test_nodes_for_cycle[0].escalation_target_level = 3
    test_nodes_for_cycle[2].escalation_target_level = 1
    cycle_path = detect_cycle(test_nodes_for_cycle)
    has_cycle = cycle_path is not None
    print(f"  升级环路: L1→L3→L1 (通过escalation_target_level)")
    print(f"    有环路: {has_cycle}, 路径: {' → '.join(f'L{l}' for l in cycle_path) if cycle_path else '无'}")
    assert has_cycle, "升级路径形成的环路应该被检测到"
    assert 1 in cycle_path and 3 in cycle_path, "环路应该包含L1和L3"
    print("  ✅ 升级路径环路检测正确")

    # 把 L3 改成 AUTO_REJECT: 升级路径中断，不应该通过升级路径形成环路
    # 注意：线性下一级 L1→L2→L3→L4 仍然存在，但不会有环路
    test_nodes_for_cycle[2].escalation_strategy = TimeoutEscalationStrategy.AUTO_REJECT
    test_nodes_for_cycle[2].escalation_target_level = None
    cycle_path = detect_cycle(test_nodes_for_cycle)
    has_cycle = cycle_path is not None
    print(f"  L3改为自动驳回后: 升级路径中断")
    print(f"    有环路: {has_cycle} (预期: False)")
    assert not has_cycle, "L3是驳回策略后，不应该有环路"
    print("  ✅ 自动驳回节点中断升级环路")

    # 把 L3 改回 ESCALATE_TO_LEVEL 但目标改成 None
    test_nodes_for_cycle[2].escalation_strategy = TimeoutEscalationStrategy.ESCALATE_TO_LEVEL
    test_nodes_for_cycle[2].escalation_target_level = None
    cycle_path = detect_cycle(test_nodes_for_cycle)
    has_cycle = cycle_path is not None
    print(f"  L3升级目标为空: 升级到下一级(默认)")
    print(f"    有环路: {has_cycle} (预期: False)")
    assert not has_cycle, "升级目标为空时回退到线性下一级，不应该有环路"
    print("  ✅ 未配置升级目标时回退到正常路径")

    print()
    print("=" * 60)
    print("测试2: 创建包含三种策略的无环路审批链")
    print("=" * 60)

    chain_data = ApprovalChainCreate(
        name="测试升级策略审批链",
        approval_type=ApprovalType.ALLOCATE,
        nodes=[
            # L1: 升级到指定级别 -> L4
            ChainNodeCreate(
                mode=ApprovalMode.SINGLE,
                timeout_minutes=5,
                escalation_strategy=TimeoutEscalationStrategy.ESCALATE_TO_LEVEL,
                escalation_target_level=4,
                approvers=[ChainNodeApproverCreate(approver_role="部门主管", approver_name="张三")],
                conditions=[],
            ),
            # L2: 自动驳回
            ChainNodeCreate(
                mode=ApprovalMode.SINGLE,
                timeout_minutes=5,
                escalation_strategy=TimeoutEscalationStrategy.AUTO_REJECT,
                approvers=[ChainNodeApproverCreate(approver_role="财务经理", approver_name="李四")],
                conditions=[],
            ),
            # L3: 跳过当前节点（会签模式，测试会签收尾）
            ChainNodeCreate(
                mode=ApprovalMode.ALL_SIGN,
                timeout_minutes=5,
                escalation_strategy=TimeoutEscalationStrategy.SKIP_NODE,
                approvers=[
                    ChainNodeApproverCreate(approver_role="技术总监", approver_name="王五"),
                    ChainNodeApproverCreate(approver_role="技术总监", approver_name="赵六"),
                ],
                conditions=[],
            ),
            # L4: 升级到下一级（默认）
            ChainNodeCreate(
                mode=ApprovalMode.SINGLE,
                timeout_minutes=5,
                escalation_strategy=TimeoutEscalationStrategy.ESCALATE_TO_LEVEL,
                escalation_target_level=None,
                approvers=[ChainNodeApproverCreate(approver_role="CTO", approver_name="钱七")],
                conditions=[],
            ),
            # L5: 最后一级，升级到下一级（无下一级 -> 驳回）
            ChainNodeCreate(
                mode=ApprovalMode.SINGLE,
                timeout_minutes=5,
                escalation_strategy=TimeoutEscalationStrategy.ESCALATE_TO_LEVEL,
                escalation_target_level=None,
                approvers=[ChainNodeApproverCreate(approver_role="CEO", approver_name="孙八")],
                conditions=[],
            ),
        ],
    )

    chain = create_approval_chain(db, chain_data)
    chain_nodes_map = _get_chain_node_map(db, chain.id)
    chain_nodes_list = [chain_nodes_map[i] for i in sorted(chain_nodes_map.keys())]
    print(f"✅ 审批链创建成功，ID={chain.id}，共{len(chain_nodes_list)}级")
    for node in chain_nodes_list:
        strategy_desc = {
            "escalate_to_level": f"升级到L{node.escalation_target_level}" if node.escalation_target_level else "升级到下一级",
            "auto_reject": "自动驳回",
            "skip_node": "跳过节点",
        }.get(node.escalation_strategy.value, node.escalation_strategy.value)
        print(f"   L{node.level}: {node.mode.value} -> {strategy_desc}")

    print()
    print("=" * 60)
    print("测试3: _detect_escalation_cycle 函数测试")
    print("=" * 60)

    # 先创建一个有环路的审批链（直接插入，绕过create_approval_chain的检测）
    cycle_chain = ApprovalChain(name="环路测试链", approval_type=ApprovalType.ALLOCATE)
    db.add(cycle_chain)
    db.flush()

    cycle_nodes = []
    for i in range(1, 4):
        n = ApprovalChainNode(
            chain_id=cycle_chain.id,
            level=i,
            mode=ApprovalMode.SINGLE,
            timeout_minutes=5,
            escalation_strategy=TimeoutEscalationStrategy.ESCALATE_TO_LEVEL,
            escalation_target_level=None,
        )
        db.add(n)
        cycle_nodes.append(n)
    db.flush()

    # L1->L3, L3->L2, L2->L1: 形成环路
    cycle_nodes[0].escalation_target_level = 3  # L1 -> L3
    cycle_nodes[2].escalation_target_level = 2  # L3 -> L2
    cycle_nodes[1].escalation_target_level = 1  # L2 -> L1
    db.commit()

    has_cycle = _detect_escalation_cycle(db, cycle_chain.id, 1, 3)
    print(f"  L1升级到L3 (L1→L3→L2→L1): 环路={has_cycle} (预期: True)")
    assert has_cycle, "应该检测到环路"

    has_cycle = _detect_escalation_cycle(db, cycle_chain.id, 1, 2)
    print(f"  L1升级到L2 (L1→L2→L1): 环路={has_cycle} (预期: True)")
    assert has_cycle, "应该检测到环路"

    # 把L2改成自动驳回，破坏环路
    cycle_nodes[1].escalation_strategy = TimeoutEscalationStrategy.AUTO_REJECT
    cycle_nodes[1].escalation_target_level = None
    db.commit()

    has_cycle = _detect_escalation_cycle(db, cycle_chain.id, 1, 3)
    print(f"  L1升级到L3 (L2改为驳回后): 环路={has_cycle} (预期: False)")
    assert not has_cycle, "L2是驳回策略，不会继续沿升级路径"

    # 清理环路测试链
    db.query(ApprovalChainNode).filter(ApprovalChainNode.chain_id == cycle_chain.id).delete()
    db.query(ApprovalChain).filter(ApprovalChain.id == cycle_chain.id).delete()
    db.commit()

    print("  ✅ _detect_escalation_cycle 函数测试通过")

    print()
    print("=" * 60)
    print("测试4: 从审批链节点定义验证级别存在")
    print("=" * 60)

    chain_nodes = _get_chain_node_map(db, chain.id)
    print(f"  审批链节点级别: {sorted(chain_nodes.keys())}")
    assert 1 in chain_nodes, "L1 应该存在"
    assert 5 in chain_nodes, "L5 应该存在"
    assert 99 not in chain_nodes, "L99 不应该存在"
    print("  ✅ 级别存在性验证通过（从审批链节点定义查询）")

    print()
    print("=" * 60)
    print("测试5: 三种升级策略执行效果")
    print("=" * 60)

    # 创建测试资产
    asset = Asset(
        asset_tag="TEST-001",
        name="测试笔记本电脑",
        category=AssetCategory.COMPUTER,
        brand="测试品牌",
        model="测试型号",
        serial_number="SN-TEST-001",
        status=AssetStatus.IN_STOCK,
        location="办公室",
        purchase_price=5000.0,
        purchase_date="2024-01-01",
    )
    db.add(asset)
    db.flush()

    # 创建审批单
    approval = Approval(
        asset_id=asset.id,
        approval_type=ApprovalType.ALLOCATE,
        status=ApprovalStatus.PENDING,
        applicant="测试申请人",
        reason="测试升级策略",
        previous_status=asset.status,
        current_level=1,
        total_levels=5,
        chain_id=chain.id,
    )
    db.add(approval)
    db.flush()

    # 创建审批记录
    node_map = _get_chain_node_map(db, chain.id)
    node_levels = sorted(node_map.keys())
    approver_map = {}
    for level, node in node_map.items():
        approvers = db.query(ApprovalChainNodeApprover).filter(
            ApprovalChainNodeApprover.chain_node_id == node.id
        ).all()
        approver_map[level] = approvers

    for i, level in enumerate(node_levels):
        record_level = i + 1
        node = node_map[level]
        for j, approver in enumerate(approver_map[level]):
            record = ApprovalNodeRecord(
                approval_id=approval.id,
                chain_node_id=node.id,
                chain_node_approver_id=approver.id,
                level=record_level,
                chain_node_level=node.level,
                approver_role=approver.approver_role,
                approver_name=approver.approver_name,
                status=ApprovalStatus.PENDING,
                timeout_at=datetime.now() + timedelta(minutes=5),
            )
            db.add(record)
    db.commit()
    db.refresh(approval)

    print(f"  创建审批单#{approval.id}，共{approval.total_levels}级")

    # ---- 策略1: ESCALATE_TO_LEVEL (升级到指定级别 L1->L4) ----
    print()
    print("  【策略1】ESCALATE_TO_LEVEL: L1 -> L4")
    node_l1 = node_map[1]
    result_level, reason = _escalation_resolve_target_level(
        db, approval, 1,
        node_l1.escalation_strategy,
        node_l1.escalation_target_level,
    )
    print(f"    策略: {node_l1.escalation_strategy.value}, 目标: L{node_l1.escalation_target_level}")
    print(f"    结果: record_level={result_level}, reason='{reason}'")
    assert result_level is not None, "L1升级到L4应该成功"
    assert reason == "", "不应该有错误原因"
    # L4是第4个节点，记录级别应该是4
    record_level_l4 = _chain_node_level_to_record_level(db, approval.id, 4)
    assert result_level == record_level_l4, f"升级目标记录级别应该是L{record_level_l4}"
    print(f"    ✅ 正确：从链节点L1升级到链节点L4，对应记录级别L{record_level_l4}")

    # ---- 策略2: AUTO_REJECT (自动驳回) ----
    print()
    print("  【策略2】AUTO_REJECT: L2")
    node_l2 = node_map[2]
    result_level, reason = _escalation_resolve_target_level(
        db, approval, 2,
        node_l2.escalation_strategy,
        node_l2.escalation_target_level,
    )
    print(f"    策略: {node_l2.escalation_strategy.value}")
    print(f"    结果: level={result_level}, reason='{reason}'")
    assert result_level is None, "自动驳回应该返回None"
    assert "自动驳回" in reason, "驳回原因应该包含'自动驳回'"
    print("    ✅ 正确：自动驳回策略返回None和原因")

    # ---- 策略3: SKIP_NODE (跳过当前节点，会签) ----
    print()
    print("  【策略3】SKIP_NODE: L3 (会签)")
    # 模拟当前在L3
    approval.current_level = 3
    db.flush()
    node_l3 = node_map[3]
    result_level, reason = _escalation_resolve_target_level(
        db, approval, 3,
        node_l3.escalation_strategy,
        node_l3.escalation_target_level,
    )
    print(f"    策略: {node_l3.escalation_strategy.value}")
    print(f"    结果: level={result_level}, reason='{reason}'")
    assert result_level == 4, f"L3跳过应该到L4，实际得到L{result_level}"
    assert reason == "", "跳过不应该有错误原因"
    print("    ✅ 正确：跳过节点后流转到下一级L4")
    # 恢复
    approval.current_level = 1
    db.flush()

    # ---- 额外测试: 升级到不存在的级别 ----
    print()
    print("  【额外测试】升级到不存在的级别 L99")
    result_level, reason = _escalation_resolve_target_level(
        db, approval, 1,
        TimeoutEscalationStrategy.ESCALATE_TO_LEVEL,
        99,
    )
    print(f"    目标: L99")
    print(f"    结果: level={result_level}, reason='{reason}'")
    assert result_level is None, "升级到不存在级别应该驳回"
    assert "不在审批链定义中" in reason, "驳回原因应该说明不在审批链定义中"
    print("    ✅ 正确：从审批链节点定义验证，级别不存在时正确驳回")

    # ---- 额外测试: 最后一级升级到下一级 ----
    print()
    print("  【额外测试】L5 升级到下一级（无下一级）")
    # 模拟当前在L5
    approval.current_level = 5
    db.flush()
    node_l5 = node_map[5]
    result_level, reason = _escalation_resolve_target_level(
        db, approval, 5,
        node_l5.escalation_strategy,
        node_l5.escalation_target_level,
    )
    print(f"    策略: {node_l5.escalation_strategy.value}, 目标: {node_l5.escalation_target_level}")
    print(f"    结果: level={result_level}, reason='{reason}'")
    assert result_level is None, "最后一级没有下一级应该返回None"
    print("    ✅ 正确：最后一级无下一级时返回None（由调用方处理驳回）")
    # 恢复
    approval.current_level = 1
    db.flush()

    print()
    print("=" * 60)
    print("所有测试通过! ✅")
    print("=" * 60)
    print()
    print("总结:")
    print("  1. ✅ 升级到指定级别: 从审批链节点定义验证级别存在，沿升级路径做环路检测")
    print("  2. ✅ 自动驳回: 返回None并附带原因，由调用方执行驳回")
    print("  3. ✅ 跳过当前节点: 返回下一级记录级别，流转继续")
    print("  4. ✅ 环路检测: 沿escalation_target_level路径追踪，而非正常流转路径")
    print("  5. ✅ 级别存在性: 从ApprovalChainNode查询，而非ApprovalNodeRecord")

except Exception as e:
    db.rollback()
    import traceback
    traceback.print_exc()
    print(f"❌ 测试失败: {e}")
    sys.exit(1)
finally:
    db.close()
