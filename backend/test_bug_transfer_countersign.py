#!/usr/bin/env python3
"""
复现并验证：转审后会签无法全员通过的bug
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.orm import Session
from datetime import datetime
from app.database import SessionLocal
from app.models import (
    User, UserRole, Role, Asset,
    ApprovalChain, ApprovalChainNode, ApprovalChainNodeApprover,
    ApprovalMode, ApprovalType, AssetCategory, AssetStatus,
    ApprovalStatus, TransferStatus,
)
from app.auth import get_user_display_name, get_password_hash
from app import crud
from app.schemas import (
    ApprovalCreate, ApprovalAction,
    ApprovalAddSignerRequest, ApprovalTransferRequest,
    ApprovalChainCreate, ChainNodeCreate, ChainNodeApproverCreate,
    AssetCreate,
)


def create_test_user(db, username, real_name, role_codes, dept="研发部"):
    user = db.query(User).filter(User.username == username).first()
    if user:
        return user
    user = User(
        username=username, email=f"{username}@test.com", real_name=real_name,
        hashed_password=get_password_hash("123456"), department=dept,
        position="测试用户", is_active=True,
    )
    db.add(user)
    db.flush()
    for role_code in role_codes:
        role = db.query(Role).filter(Role.code == role_code).first()
        if role:
            db.add(UserRole(user_id=user.id, role_id=role.id))
    db.commit()
    db.refresh(user)
    return user


def create_test_asset(db, operator):
    asset_data = AssetCreate(
        name="BUG复现-测试笔记本", category=AssetCategory.COMPUTER,
        brand="Test", model="TestPro", serial_number=f"BUG-{datetime.now().timestamp()}",
        purchase_price=8000.0, purchase_department=operator.department,
    )
    return crud.create_asset(db, asset_data, operator)


def create_countersign_chain(db):
    chain_data = ApprovalChainCreate(
        name="BUG复现-会签链", approval_type=ApprovalType.ALLOCATE, is_default=False,
        nodes=[
            ChainNodeCreate(
                mode=ApprovalMode.ALL_SIGN,
                approvers=[
                    ChainNodeApproverCreate(approver_role="dept_manager", approver_name="经理A"),
                    ChainNodeApproverCreate(approver_role="dept_manager", approver_name="经理B"),
                ],
            ),
        ],
    )
    return crud.create_approval_chain(db, chain_data)


def cleanup(db, user_ids, asset_ids, chain_ids):
    try:
        from app.models import (
            Approval, ApprovalNodeRecord, ApprovalNodeAction,
            ApprovalReminder, Notification, OperationLog, AssetLog,
            ApprovalChainNode, ApprovalChainNodeApprover,
            ApprovalChainCondition, ApprovalChainConditionRule,
        )
        for aid in asset_ids:
            db.query(AssetLog).filter(AssetLog.asset_id == aid).delete()
            approvals = db.query(Approval).filter(Approval.asset_id == aid).all()
            for ap in approvals:
                db.query(ApprovalReminder).filter(ApprovalReminder.approval_id == ap.id).delete()
                db.query(ApprovalNodeAction).filter(ApprovalNodeAction.approval_id == ap.id).delete()
                db.query(ApprovalNodeRecord).filter(ApprovalNodeRecord.approval_id == ap.id).delete()
                db.query(Notification).filter(Notification.related_id == ap.id, Notification.related_type == "approval").delete()
                db.query(OperationLog).filter(OperationLog.target_id == ap.id, OperationLog.target_type == "approval").delete()
                db.delete(ap)
            db.query(Asset).filter(Asset.id == aid).delete()
        for cid in chain_ids:
            nodes = db.query(ApprovalChainNode).filter(ApprovalChainNode.chain_id == cid).all()
            for n in nodes:
                db.query(ApprovalChainNodeApprover).filter(ApprovalChainNodeApprover.chain_node_id == n.id).delete()
                conds = db.query(ApprovalChainCondition).filter(ApprovalChainCondition.chain_node_id == n.id).all()
                for c in conds:
                    db.query(ApprovalChainConditionRule).filter(ApprovalChainConditionRule.condition_id == c.id).delete()
                    db.delete(c)
                db.delete(n)
            db.query(ApprovalChain).filter(ApprovalChain.id == cid).delete()
        for uid in user_ids:
            if uid > 5:
                db.query(UserRole).filter(UserRole.user_id == uid).delete()
                db.query(OperationLog).filter(OperationLog.operator_id == uid).delete()
                db.query(Notification).filter(Notification.user_id == uid).delete()
                db.query(User).filter(User.id == uid).delete()
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"清理失败: {e}")


def main():
    print("=" * 70)
    print("BUG复现：转审后会签无法全员通过")
    print("=" * 70)

    db = SessionLocal()
    uids, aids, cids = [], [], []

    try:
        print("\n【准备数据】")
        applicant = create_test_user(db, "bug_applicant", "申请人", ["employee"])
        approver_a = create_test_user(db, "bug_app_a", "经理A", ["dept_manager"])
        approver_b = create_test_user(db, "bug_app_b", "经理B", ["dept_manager"])
        transfer_target = create_test_user(db, "bug_transfer", "转审接收人C", ["dept_manager"])
        uids = [applicant.id, approver_a.id, approver_b.id, transfer_target.id]
        print(f"  申请人: {get_user_display_name(applicant)}")
        print(f"  会签人A: {get_user_display_name(approver_a)}")
        print(f"  会签人B: {get_user_display_name(approver_b)}")
        print(f"  转审接收: {get_user_display_name(transfer_target)}")

        asset = create_test_asset(db, applicant)
        aids.append(asset.id)
        chain = create_countersign_chain(db)
        cids.append(chain.id)
        print(f"  资产: {asset.name}, 审批链: {chain.name}")

        print("\n【步骤1】提交审批")
        approval_data = ApprovalCreate(
            approval_type=ApprovalType.ALLOCATE,
            applicant=get_user_display_name(applicant),
            assignee=get_user_display_name(applicant),
            reason="BUG复现：转审后会签",
        )
        approval = crud.create_approval(db, asset.id, approval_data, applicant)
        print(f"  审批单#{approval.id}创建，状态: {approval.status.value}")
        node_records = crud.get_approval_node_records(db, approval.id)
        for r in node_records:
            print(f"    - L{r.level}: {r.approver_name} ({r.approver_role}) - {r.status.value}")

        print("\n【步骤2】经理A审批通过")
        approval = crud.approve_approval(db, approval.id, ApprovalAction(opinion="A同意"), approver_a)
        print(f"  状态: {approval.status.value}, 当前级别: {approval.current_level}")
        node_records = crud.get_approval_node_records(db, approval.id)
        for r in node_records:
            print(f"    - #{r.id} {r.approver_name}: {r.status.value} (transfer={r.transfer_status}, src={r.source_record_id})")

        print("\n【步骤3】经理B将审批转审给接收人C")
        pending_b = [r for r in node_records if r.approver_name == get_user_display_name(approver_b) and r.status == ApprovalStatus.PENDING][0]
        print(f"  转审记录ID: #{pending_b.id}")
        approval = crud.transfer_approval(
            db, approval.id, pending_b.id, transfer_target.id, "B出差，转C处理", approver_b
        )
        node_records = crud.get_approval_node_records(db, approval.id)
        print(f"  转审后节点记录:")
        for r in node_records:
            src_info = f", source_record_id={r.source_record_id}" if r.source_record_id else ""
            trans_info = f", transfer_status={r.transfer_status.value}" if r.transfer_status else ""
            added_info = f", is_added_signer={r.is_added_signer}" if r.is_added_signer else ""
            print(f"    - #{r.id} {r.approver_name}: {r.status.value}{trans_info}{src_info}{added_info}")

        print("\n【步骤4】验证 _filter_active_records 结果")
        from app.crud import _filter_active_records
        current_level_records = [r for r in node_records if r.level == approval.current_level]
        active = _filter_active_records(current_level_records)
        print(f"  当前级别记录数: {len(current_level_records)}")
        print(f"  _filter_active_records后: {len(active)} 条")
        for r in active:
            print(f"    - #{r.id} {r.approver_name}: {r.status.value}")

        print("\n【步骤5】转审接收人C审批通过（关键：验证会签能否全员通过）")
        print(f"  以 {get_user_display_name(transfer_target)} 身份执行 approve_approval...")
        try:
            approval = crud.approve_approval(db, approval.id, ApprovalAction(opinion="C同意"), transfer_target)
            print(f"  ✅ 审批调用成功!")
            print(f"     审批单状态: {approval.status.value}")
            print(f"     当前级别: {approval.current_level}/{approval.total_levels}")
            node_records = crud.get_approval_node_records(db, approval.id)
            print(f"     节点状态:")
            for r in node_records:
                src_info = f", source_record_id={r.source_record_id}" if r.source_record_id else ""
                trans_info = f", transfer_status={r.transfer_status.value}" if r.transfer_status else ""
                print(f"       - #{r.id} {r.approver_name}: {r.status.value}{trans_info}{src_info}")

            if approval.status == ApprovalStatus.APPROVED:
                print(f"\n  ✅✅✅ BUG已修复！会签全员通过，审批完成！")
            else:
                print(f"\n  ❌❌❌ BUG存在：审批状态是 {approval.status.value}，应该是 approved！")
                # 打印详细信息辅助分析
                print(f"  分析active records:")
                current_level_records = [r for r in node_records if r.level == approval.current_level]
                active = _filter_active_records(current_level_records)
                for r in active:
                    print(f"    - #{r.id} {r.approver_name}: status={r.status.value}, is APPROVED? {r.status == ApprovalStatus.APPROVED}")
        except Exception as e:
            print(f"  ❌ 审批调用失败: {e}")
            import traceback
            traceback.print_exc()

        print("\n【步骤6】查看审批时间线")
        timeline = crud.build_approval_timeline(db, approval.id)
        for event in timeline:
            target = f"→{event.target_user}" if event.target_user else ""
            lvl = f"L{event.level}" if event.level else ""
            status = f"[{event.status}]" if event.status else ""
            reason = f" - {event.reason}" if event.reason else ""
            opinion = f" - {event.opinion}" if event.opinion else ""
            print(f"  {event.created_at.strftime('%H:%M:%S')} | {event.event_type_cn:10s} | {event.operator}{target}{lvl}{status}{reason}{opinion}")

    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        print("\n清理数据...")
        cleanup(db, uids, aids, cids)
        db.close()


if __name__ == "__main__":
    main()
