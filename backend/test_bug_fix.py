#!/usr/bin/env python3
"""验证转审后会签可正常全员通过"""
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


def create_user(db, username, real_name, role_codes, dept="研发部"):
    user = db.query(User).filter(User.username == username).first()
    if user:
        return user
    user = User(
        username=username, email=f"{username}@test2.com", real_name=real_name,
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
    print("Bug修复验证：转审后会签可正常全员通过")
    print("=" * 70)

    try:
        print("\n--- 创建用户 ---")
        applicant = create_user(db, "v2_app", "验证申请人", ["employee"])
        approver_a = create_user(db, "v2_aa", "验证经理A", ["dept_manager"])
        approver_b = create_user(db, "v2_ab", "验证经理B", ["dept_manager"])
        transfer_c = create_user(db, "v2_tc", "验证经理C", ["dept_manager"])
        finance = create_user(db, "v2_fm", "验证财务", ["finance_manager"], "财务部")
        signer_d = create_user(db, "v2_sd", "验证加签人D", ["dept_manager", "asset_admin"])

        print(f"  A: {get_user_display_name(approver_a)}")
        print(f"  B: {get_user_display_name(approver_b)}")
        print(f"  C(转审接收): {get_user_display_name(transfer_c)}")
        print(f"  D(加签人): {get_user_display_name(signer_d)}")

        print("\n--- 创建2级会签审批链 ---")
        chain_data = ApprovalChainCreate(
            name="验证会签转审链",
            approval_type=ApprovalType.ALLOCATE,
            is_default=False,
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

        old_chains = db.query(ApprovalChain).filter(
            ApprovalChain.approval_type == ApprovalType.ALLOCATE,
            ApprovalChain.id != chain.id,
        ).all()
        for oc in old_chains:
            nodes = db.query(ApprovalChainNode).filter(ApprovalChainNode.chain_id == oc.id).all()
            for n in nodes:
                db.query(ApprovalChainNodeApprover).filter(ApprovalChainNodeApprover.chain_node_id == n.id).delete()
                db.delete(n)
            db.delete(oc)
        db.commit()

        asset_data = AssetCreate(
            name="验证资产", category=AssetCategory.COMPUTER, brand="Brand",
            model="Model", serial_number=f"V2-{datetime.now().timestamp()}",
            purchase_price=5000.0, purchase_department="研发部",
        )
        asset = crud.create_asset(db, asset_data, applicant)

        approval_data = ApprovalCreate(
            approval_type=ApprovalType.ALLOCATE,
            applicant=get_user_display_name(applicant),
            assignee=get_user_display_name(applicant),
            reason="验证转审bug修复",
        )
        approval = crud.create_approval(db, asset.id, approval_data, applicant)
        print(f"  审批单#{approval.id}, level={approval.current_level}/{approval.total_levels}")

        records = crud.get_approval_node_records(db, approval.id)
        for r in records:
            print(f"    L{r.level}: {r.approver_name} ({r.approver_role}) status={r.status.value}")

        if approval.total_levels < 2:
            print("  ✗ 审批链只有1级，无法验证转审后会签推进到2级")
            return

        print("\n--- A通过 ---")
        approval = crud.approve_approval(db, approval.id, ApprovalAction(opinion="同意"), approver_a)
        print(f"  level={approval.current_level}/{approval.total_levels}, status={approval.status.value}")

        print("\n--- B转审给C ---")
        records = crud.get_approval_node_records(db, approval.id)
        b_record = None
        for r in records:
            if r.level == 1 and r.approver_name == get_user_display_name(approver_b) and r.status == ApprovalStatus.PENDING:
                b_record = r
                break
        if not b_record:
            for r in records:
                if r.level == 1 and r.status == ApprovalStatus.PENDING and r.transfer_status != TransferStatus.TRANSFERRED:
                    b_record = r
                    break

        approval = crud.transfer_approval(
            db, approval.id, b_record.id, transfer_c.id, "出差中", approver_b
        )
        records = crud.get_approval_node_records(db, approval.id)
        print(f"  转审后Level 1记录:")
        for r in records:
            if r.level == 1:
                print(f"    #{r.id} {r.approver_name}: status={r.status.value} transfer_status={r.transfer_status}")

        print("\n--- 加签人D ---")
        pending_l1 = [r for r in records if r.level == 1 and r.status == ApprovalStatus.PENDING and r.transfer_status != TransferStatus.TRANSFERRED]
        if pending_l1:
            approval = crud.add_approval_signer(
                db, approval.id, pending_l1[0].id, signer_d.id, "需要加签确认", applicant
            )
            records = crud.get_approval_node_records(db, approval.id)
            print(f"  加签后Level 1记录:")
            for r in records:
                if r.level == 1:
                    is_added = "(加签)" if r.is_added_signer else ""
                    print(f"    #{r.id} {r.approver_name}: status={r.status.value} {is_added}")

        print("\n--- C和D审批 ---")
        records = crud.get_approval_node_records(db, approval.id)
        for r in records:
            if r.level == 1 and r.status == ApprovalStatus.PENDING and r.transfer_status != TransferStatus.TRANSFERRED:
                name = r.approver_name
                if name == get_user_display_name(transfer_c):
                    approval = crud.approve_approval(db, approval.id, ApprovalAction(opinion="同意"), transfer_c)
                    print(f"  C通过: level={approval.current_level}/{approval.total_levels}, status={approval.status.value}")
                elif name == get_user_display_name(signer_d):
                    approval = crud.approve_approval(db, approval.id, ApprovalAction(opinion="同意"), signer_d)
                    print(f"  D通过: level={approval.current_level}/{approval.total_levels}, status={approval.status.value}")

        if approval.current_level == 2:
            print("\n  ✓ BUG修复成功！会签全员通过后推进到Level 2")
        elif approval.current_level == 1:
            active_l1 = [r for r in crud.get_approval_node_records(db, approval.id) if r.level == 1 and r.transfer_status != TransferStatus.TRANSFERRED]
            all_done = all(r.status == ApprovalStatus.APPROVED for r in active_l1)
            if all_done and approval.status == ApprovalStatus.PENDING:
                print("\n  ✗ BUG仍存在：全员通过但仍停留在Level 1")
            else:
                pending = [r for r in active_l1 if r.status == ApprovalStatus.PENDING]
                print(f"\n  Level 1仍有未通过记录: {[f'{r.approver_name}={r.status.value}' for r in pending]}")
        else:
            print(f"\n  当前级别: {approval.current_level}")

        print("\n--- 财务审批 ---")
        if approval.current_level == 2 and approval.status == ApprovalStatus.PENDING:
            approval = crud.approve_approval(db, approval.id, ApprovalAction(opinion="同意"), finance)
            if approval.status == ApprovalStatus.APPROVED:
                print("\n✓ 完整流程验证通过！转审+加签+会签全员通过 → Level 2审批 → 完成")
            else:
                print(f"\n  财务审批后: status={approval.status.value}")

        print("\n--- 时间线验证 ---")
        timeline = crud.build_approval_timeline(db, approval.id)
        for event in timeline:
            target = f" → {event.target_user}" if event.target_user else ""
            level = f" L{event.level}" if event.level else ""
            reason = f" [{event.reason}]" if event.reason else ""
            opinion = f" ({event.opinion})" if event.opinion else ""
            print(f"  {event.event_type_cn:14s} | {event.operator}{target}{level}{reason}{opinion}")

    except Exception as e:
        print(f"\n✗ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        print("\n清理...")
        try:
            for uname in ["v2_app", "v2_aa", "v2_ab", "v2_tc", "v2_fm", "v2_sd"]:
                u = db.query(User).filter(User.username == uname).first()
                if u:
                    db.query(UserRole).filter(UserRole.user_id == u.id).delete()
                    db.delete(u)
            db.commit()
        except:
            db.rollback()
        db.close()


if __name__ == "__main__":
    main()
