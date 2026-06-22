#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["ASSET_JWT_SECRET"] = "test-secret-key-for-development"

from datetime import datetime, timedelta
from sqlalchemy import text
from app.database import SessionLocal
from app.models import (
    User, Asset, Approval, ApprovalChain, ApprovalChainNode, ApprovalChainNodeApprover,
    ApprovalNodeRecord, OperationLog, Notification,
    ApprovalType, ApprovalStatus, AssetStatus, TimeoutEscalationStrategy, NotificationType,
)
from app import crud

db = SessionLocal()

try:
    print("=" * 70)
    print("审批超时自动升级功能测试")
    print("=" * 70)

    emp1 = db.query(User).filter(User.username == "test_applicant").first()
    dept_mgr = db.query(User).filter(User.username == "test_approver1").first()
    asset_admin = db.query(User).filter(User.username == "test_add_signer").first()
    super_admin = db.query(User).filter(User.username == "admin").first()

    if not emp1 or not dept_mgr or not asset_admin:
        print("❌ 缺少测试用户，请确保系统已初始化用户数据")
        sys.exit(1)

    test_asset = db.query(Asset).filter(Asset.status == AssetStatus.IN_STOCK).first()
    if not test_asset:
        print("❌ 缺少在库资产用于测试")
        sys.exit(1)

    print(f"\n1. 创建包含超时升级策略的审批链...")
    chain_name = "超时升级测试链"
    chain = db.query(ApprovalChain).filter(ApprovalChain.name == chain_name).first()
    if chain:
        db.query(ApprovalChainNodeApprover).filter(
            ApprovalChainNodeApprover.chain_node_id.in_(
                [n.id for n in db.query(ApprovalChainNode.id).filter(ApprovalChainNode.chain_id == chain.id).all()]
            )
        ).delete(synchronize_session=False)
        db.query(ApprovalChainNode).filter(ApprovalChainNode.chain_id == chain.id).delete(synchronize_session=False)
        db.query(ApprovalChain).filter(ApprovalChain.id == chain.id).delete(synchronize_session=False)
        db.commit()

    chain = ApprovalChain(
        name=chain_name,
        approval_type=ApprovalType.SCRAP,
        is_default=False,
    )
    db.add(chain)
    db.flush()

    node1 = ApprovalChainNode(
        chain_id=chain.id,
        level=1,
        timeout_minutes=1,
        escalation_strategy=TimeoutEscalationStrategy.ESCALATE_TO_LEVEL,
        escalation_target_level=2,
    )
    db.add(node1)
    db.flush()

    node1_approver = ApprovalChainNodeApprover(
        chain_node_id=node1.id,
        approver_role="dept_manager",
        approver_name="部门经理",
    )
    db.add(node1_approver)

    node2 = ApprovalChainNode(
        chain_id=chain.id,
        level=2,
        timeout_minutes=60,
        escalation_strategy=TimeoutEscalationStrategy.AUTO_REJECT,
    )
    db.add(node2)
    db.flush()

    node2_approver = ApprovalChainNodeApprover(
        chain_node_id=node2.id,
        approver_role="asset_admin",
        approver_name="资产管理员",
    )
    db.add(node2_approver)

    db.flush()
    print(f"  ✓ 创建审批链: {chain.name}")
    print(f"    Level 1: dept_manager, 超时1分钟, 升级策略: 升级到Level 2")
    print(f"    Level 2: asset_admin, 超时60分钟, 升级策略: 自动驳回")

    print(f"\n2. 创建测试审批单...")
    old_status = test_asset.status
    test_asset.status = AssetStatus.PENDING_APPROVAL

    approval = Approval(
        asset_id=test_asset.id,
        approval_type=ApprovalType.SCRAP,
        applicant=emp1.real_name,
        status=ApprovalStatus.PENDING,
        current_level=1,
        total_levels=2,
        chain_id=chain.id,
        reason="超时升级自动化测试",
        previous_status=old_status,
    )
    db.add(approval)
    db.flush()

    now = datetime.now()
    timeout_at = now - timedelta(seconds=30)

    record1 = ApprovalNodeRecord(
        approval_id=approval.id,
        chain_node_id=node1.id,
        chain_node_approver_id=node1_approver.id,
        level=1,
        chain_node_level=1,
        approver_role="dept_manager",
        approver_name="部门经理",
        status=ApprovalStatus.PENDING,
        timeout_at=timeout_at,
    )
    db.add(record1)

    record2 = ApprovalNodeRecord(
        approval_id=approval.id,
        chain_node_id=node2.id,
        chain_node_approver_id=node2_approver.id,
        level=2,
        chain_node_level=2,
        approver_role="asset_admin",
        approver_name="资产管理员",
        status=ApprovalStatus.PENDING,
    )
    db.add(record2)
    db.flush()

    print(f"  ✓ 创建审批单 #{approval.id}")
    print(f"    Level 1 记录超时时间设置为: {timeout_at.strftime('%Y-%m-%d %H:%M:%S')} (已超时30秒)")

    print(f"\n3. 清除可能存在的锁...")
    db.execute(
        text("UPDATE approvals SET processing_lock = NULL, processing_locked_at = NULL WHERE processing_lock IS NOT NULL")
    )
    db.flush()

    print(f"\n4. 运行超时检查 check_and_process_timeouts()...")
    before_ops = db.query(OperationLog).filter(OperationLog.module == "approval").count()
    before_notifs = db.query(Notification).count()

    results = crud.check_and_process_timeouts(db)
    print(f"  ✓ 超时处理完成，处理结果: {results}")

    print(f"\n5. 验证升级结果...")
    db.refresh(approval)
    print(f"  审批单当前级别: {approval.current_level} (预期: 2)")
    print(f"  审批单状态: {approval.status.value} (预期: pending)")

    record1_after = db.query(ApprovalNodeRecord).filter(
        ApprovalNodeRecord.approval_id == approval.id,
        ApprovalNodeRecord.level == 1,
    ).first()
    print(f"  Level 1 状态: {record1_after.status.value} (预期: escalated)")
    print(f"  Level 1 is_escalated: {record1_after.is_escalated} (预期: True)")
    print(f"  Level 1 意见: {record1_after.opinion}")

    record2_after = db.query(ApprovalNodeRecord).filter(
        ApprovalNodeRecord.approval_id == approval.id,
        ApprovalNodeRecord.level == 2,
    ).first()
    print(f"  Level 2 状态: {record2_after.status.value} (预期: pending)")
    print(f"  Level 2 timeout_at: {record2_after.timeout_at}")

    after_ops = db.query(OperationLog).filter(OperationLog.module == "approval").count()
    new_ops = after_ops - before_ops
    print(f"\n6. 操作日志检查: 新增 {new_ops} 条审批操作日志")

    op_logs = db.query(OperationLog).filter(
        OperationLog.module == "approval",
    ).order_by(OperationLog.id.desc()).limit(3).all()
    for log in op_logs:
        print(f"  - [{log.action}] {log.detail}")

    after_notifs = db.query(Notification).count()
    new_notifs = after_notifs - before_notifs
    print(f"\n7. 通知检查: 新增 {new_notifs} 条通知")

    escalated_notifs = db.query(Notification).filter(
        Notification.type == NotificationType.APPROVAL_ESCALATED,
        Notification.related_id == approval.id,
    ).all()
    print(f"  升级通知数量: {len(escalated_notifs)}")
    for notif in escalated_notifs:
        user = db.query(User).filter(User.id == notif.user_id).first()
        print(f"    - 通知用户: {user.real_name or user.username}, 标题: {notif.title}")
        print(f"      内容: {notif.content[:80]}...")

    print(f"\n8. Timeline 事件检查...")
    timeline = crud.build_approval_timeline(db, approval.id)
    escalate_events = [e for e in timeline if e.event_type == "escalate"]
    print(f"  Timeline 总事件数: {len(timeline)}")
    print(f"  升级事件数: {len(escalate_events)}")
    for evt in escalate_events:
        print(f"    - {evt.event_type_cn} | {evt.operator} | Level {evt.level} | {evt.opinion}")

    print(f"\n" + "=" * 70)
    all_ok = (
        approval.current_level == 2
        and approval.status == ApprovalStatus.PENDING
        and record1_after.status == ApprovalStatus.ESCALATED
        and record1_after.is_escalated == True
        and len(escalated_notifs) > 0
        and len(escalate_events) > 0
    )
    if all_ok:
        print("✅ 所有测试通过！超时自动升级功能正常工作。")
    else:
        print("❌ 部分测试未通过，请检查上述输出。")
    print("=" * 70)

    db.commit()

except Exception as e:
    db.rollback()
    print(f"\n❌ 测试出错: {e}")
    import traceback
    traceback.print_exc()
finally:
    db.close()
