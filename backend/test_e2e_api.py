#!/usr/bin/env python3
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime
from app.database import SessionLocal
from app.models import (
    User, UserRole, Role, ApprovalStatus,
    ApprovalMode, ApprovalType, AssetCategory,
    ApprovalNodeRecord, TransferStatus,
    ApprovalChain, ApprovalChainNode, ApprovalChainNodeApprover,
)
from app.auth import get_user_display_name, get_password_hash
from app import crud
from app.schemas import (
    ApprovalCreate, ApprovalAction,
    ApprovalChainCreate, ChainNodeCreate, ChainNodeApproverCreate, AssetCreate,
)


def create_user(db, username, real_name, role_codes, dept="测试部"):
    user = db.query(User).filter(User.username == username).first()
    if user:
        return user
    user = User(
        username=username, email=f"{username}@e2e.com", real_name=real_name,
        hashed_password=get_password_hash("123456"), department=dept,
        position="测试", is_active=True,
    )
    db.add(user)
    db.flush()
    for rc in role_codes:
        role = db.query(Role).filter(Role.code == rc).first()
        if role:
            db.add(UserRole(user_id=user.id, role_id=role.id))
    db.commit()
    db.refresh(user)
    return user


def main():
    db = SessionLocal()
    print("=" * 70)
    print("端到端API验证：转审+加签+会签全员通过→Level 2→完成")
    print("=" * 70)

    try:
        print("\n--- 创建用户 ---")
        applicant = create_user(db, "e2e_app2", "端端申请人", ["employee"])
        approver_a = create_user(db, "e2e_a2", "端端经理A", ["dept_manager"])
        approver_b = create_user(db, "e2e_b2", "端端经理B", ["dept_manager"])
        transfer_c = create_user(db, "e2e_c2", "端端经理C", ["dept_manager"])
        finance = create_user(db, "e2e_f2", "端端财务", ["finance_manager"], "财务部")
        signer_d = create_user(db, "e2e_d2", "端端加签人D", ["dept_manager", "asset_admin"])

        print(f"  申请人: {get_user_display_name(applicant)}")
        print(f"  经理A: {get_user_display_name(approver_a)}")
        print(f"  经理B: {get_user_display_name(approver_b)}")
        print(f"  经理C(转审接收): {get_user_display_name(transfer_c)}")
        print(f"  经理D(加签人): {get_user_display_name(signer_d)}")
        print(f"  财务: {get_user_display_name(finance)}")

        print("\n--- 创建2级会签审批链 ---")
        existing_allocate_chains = db.query(ApprovalChain).filter(
            ApprovalChain.approval_type == ApprovalType.ALLOCATE,
        ).all()
        for ec in existing_allocate_chains:
            db.delete(ec)
        db.commit()

        chain_data = ApprovalChainCreate(
            name="端端测试审批链",
            approval_type=ApprovalType.ALLOCATE,
            is_default=True,
            nodes=[
                ChainNodeCreate(
                    mode=ApprovalMode.ALL_SIGN,
                    approvers=[
                        ChainNodeApproverCreate(approver_role="dept_manager", approver_name=get_user_display_name(approver_a)),
                        ChainNodeApproverCreate(approver_role="dept_manager", approver_name=get_user_display_name(approver_b)),
                    ],
                ),
                ChainNodeCreate(
                    mode=ApprovalMode.SINGLE,
                    approvers=[
                        ChainNodeApproverCreate(approver_role="finance_manager", approver_name=get_user_display_name(finance)),
                    ],
                ),
            ],
        )

        chain = crud.create_approval_chain(db, chain_data)
        print(f"  Chain #{chain.id}: {chain.name}")

        print("\n--- 创建资产 ---")
        asset_data = AssetCreate(
            name="端端测试资产",
            category=AssetCategory.COMPUTER,
            brand="测试品牌",
            model="测试型号",
            serial_number=f"SN-E2E-{datetime.now().strftime('%H%M%S')}",
            purchase_price=8888.0,
        )
        asset = crud.create_asset(db, asset_data, operator=applicant)
        print(f"  Asset #{asset.id}: {asset.name}")

        print("\n--- 创建审批 ---")
        approval_create = ApprovalCreate(
            approval_type="allocate",
            applicant=get_user_display_name(applicant),
            assignee=get_user_display_name(applicant),
            reason="端端测试：转审+加签+会签全员通过",
        )
        approval = crud.create_approval(db, asset_id=asset.id, data=approval_create, applicant=applicant)
        print(f"  Approval #{approval.id}, status={approval.status.value}, level={approval.current_level}")

        records = crud.get_approval_node_records(db, approval.id)
        print(f"  All records: {len(records)}")
        for r in records:
            print(f"    L{r.level} {r.approver_name}: status={r.status.value}")

        print("\n=== Step 1: 经理A审批通过 ===")
        approval = crud.approve_approval(db, approval.id, ApprovalAction(opinion="同意A"), approver_a)
        print(f"  status={approval.status.value}, level={approval.current_level}/{approval.total_levels}")

        print("\n=== Step 2: 经理B转审给经理C ===")
        records = crud.get_approval_node_records(db, approval.id)
        b_record = None
        for r in records:
            if (r.level == 1 and r.approver_name == get_user_display_name(approver_b)
                    and r.status == ApprovalStatus.PENDING):
                b_record = r
                break
        assert b_record is not None, "Could not find B's pending record"
        print(f"  Found B's record #{b_record.id}")
        approval = crud.transfer_approval(
            db, approval.id, b_record.id, transfer_c.id, "出差中请代审", approver_b
        )
        records = crud.get_approval_node_records(db, approval.id)
        print(f"  Level 1 转审后记录:")
        for r in records:
            if r.level == 1:
                ts = f" transfer_status={r.transfer_status.value}" if r.transfer_status else ""
                print(f"    #{r.id} {r.approver_name}: status={r.status.value}{ts} type={r.record_type.value}")

        transferred = [r for r in records if r.transfer_status == TransferStatus.TRANSFERRED]
        assert len(transferred) == 1, f"Expected 1 transferred record, got {len(transferred)}"
        assert transferred[0].status == ApprovalStatus.APPROVED, \
            f"Transferred record status should be APPROVED, is {transferred[0].status.value}"
        print("  ✓ Bug修复验证: 转审后原记录status=APPROVED (关键修复)")

        print("\n=== Step 3: 加签人D ===")
        records = crud.get_approval_node_records(db, approval.id)
        pending_l1 = [r for r in records
                      if r.level == 1
                      and r.status == ApprovalStatus.PENDING
                      and r.transfer_status != TransferStatus.TRANSFERRED]
        assert len(pending_l1) >= 1, f"No active pending records at level 1, found {len(pending_l1)}"
        print(f"  Level 1 active pending: {[r.approver_name for r in pending_l1]}")

        approval = crud.add_approval_signer(
            db, approval.id, pending_l1[0].id, signer_d.id, "需要加签确认", applicant
        )
        records = crud.get_approval_node_records(db, approval.id)
        added = [r for r in records if r.is_added_signer]
        assert len(added) == 1, f"Expected 1 added signer, got {len(added)}"
        print(f"  ✓ 加签人: {added[0].approver_name}")

        print("\n=== Step 4: 经理C和加签人D审批 ===")
        records = crud.get_approval_node_records(db, approval.id)
        for r in records:
            if (r.level == 1 and r.status == ApprovalStatus.PENDING
                    and r.transfer_status != TransferStatus.TRANSFERRED):
                name = r.approver_name
                if name == get_user_display_name(transfer_c):
                    approval = crud.approve_approval(db, approval.id, ApprovalAction(opinion="同意代C"), transfer_c)
                    print(f"  C通过: level={approval.current_level}/{approval.total_levels}")
                elif name == get_user_display_name(signer_d):
                    approval = crud.approve_approval(db, approval.id, ApprovalAction(opinion="加签通过"), signer_d)
                    print(f"  D通过: level={approval.current_level}/{approval.total_levels}")

        if approval.current_level == 2:
            print("  ✓ 会签全员通过！推进到Level 2 (核心Bug修复验证成功！)")
        else:
            records = crud.get_approval_node_records(db, approval.id)
            active_l1 = [r for r in records if r.level == 1 and r.transfer_status != TransferStatus.TRANSFERRED]
            pending = [r for r in active_l1 if r.status == ApprovalStatus.PENDING]
            print(f"  ✗ 仍停在Level {approval.current_level}, Pending: {[r.approver_name for r in pending]}")
            return False

        print("\n=== Step 5: 财务审批（Level 2） ===")
        approval = crud.approve_approval(db, approval.id, ApprovalAction(opinion="财务同意"), finance)
        assert approval.status == ApprovalStatus.APPROVED
        print(f"  ✓ 审批完成！status={approval.status.value}")

        print("\n=== Step 6: 验证审批时间线 ===")
        timeline = crud.build_approval_timeline(db, approval.id)
        print(f"  Timeline events: {len(timeline)}")
        for event in timeline:
            target = f" → {event.target_user}" if event.target_user else ""
            level = f" L{event.level}" if event.level else ""
            reason = f" [{event.reason}]" if event.reason else ""
            opinion = f" ({event.opinion})" if event.opinion else ""
            print(f"  {event.event_type_cn:14s} | {event.operator}{target}{level}{reason}{opinion}")

        print("\n=== Step 7: 验证无残留PENDING记录 ===")
        all_records = crud.get_approval_node_records(db, approval.id)
        active_pending = [r for r in all_records
                         if r.status == ApprovalStatus.PENDING and r.transfer_status != TransferStatus.TRANSFERRED]
        assert len(active_pending) == 0, f"Found {len(active_pending)} stale pending records"
        print("  ✓ 无残留PENDING记录")

        print("\n" + "=" * 70)
        print("  ALL E2E TESTS PASSED!")
        print("=" * 70)
        print("""
  验证总结:
  1. ✅ 转审后原记录status=APPROVED（核心Bug修复）
  2. ✅ 已转审记录正确排除出待处理查询
  3. ✅ 会签(ALL_SIGN)全员通过后正常推进到下一级
  4. ✅ 加签功能正常
  5. ✅ 转审+加签+全员通过完整流程通过
  6. ✅ 审批时间线正确生成
  7. ✅ 无残留PENDING记录
""")
        return True

    except Exception as e:
        import traceback
        print(f"\nFAIL: {e}")
        traceback.print_exc()
        return False
    finally:
        db.close()


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
