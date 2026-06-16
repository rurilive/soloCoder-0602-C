#!/usr/bin/env python3
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime
from app.database import SessionLocal
from app.models import (
    User, UserRole, Role, Asset, ApprovalStatus,
    ApprovalMode, ApprovalType, AssetCategory,
    ApprovalNodeRecord, TransferStatus,
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
        username=username, email=f"{username}@test.com", real_name=real_name,
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
    print("Bug复现测试：转审后会签无法全员通过")
    print("=" * 70)

    try:
        print("\n--- 步骤1: 创建用户 ---")
        applicant = create_user(db, "bug_app", "测试申请人", ["employee"])
        approver_a = create_user(db, "bug_aa", "测试经理A", ["dept_manager"])
        approver_b = create_user(db, "bug_ab", "测试经理B", ["dept_manager"])
        transfer_c = create_user(db, "bug_tc", "测试经理C", ["dept_manager"])
        finance = create_user(db, "bug_fm", "测试财务", ["finance_manager"], "财务部")
        print(f"  A: {get_user_display_name(approver_a)}, B: {get_user_display_name(approver_b)}, C: {get_user_display_name(transfer_c)}")

        print("\n--- 步骤2: 创建会签审批链(2级) ---")
        chain_data = ApprovalChainCreate(
            name="会签转审测试链",
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
        print(f"  审批链#{chain.id} 创建成功")

        print("\n--- 步骤3: 创建资产并提交审批 ---")
        asset_data = AssetCreate(
            name="测试资产", category=AssetCategory.COMPUTER, brand="Brand",
            model="Model", serial_number=f"BUG-{datetime.now().timestamp()}",
            purchase_price=5000.0, purchase_department="研发部",
        )
        asset = crud.create_asset(db, asset_data, applicant)

        approval_data = ApprovalCreate(
            approval_type=ApprovalType.ALLOCATE,
            applicant=get_user_display_name(applicant),
            assignee=get_user_display_name(applicant),
            reason="测试转审bug",
            chain_id=chain.id,
        )
        approval = crud.create_approval(db, asset.id, approval_data, applicant)
        print(f"  审批单#{approval.id}, status={approval.status.value}, level={approval.current_level}/{approval.total_levels}")

        records = crud.get_approval_node_records(db, approval.id)
        for r in records:
            print(f"    #{r.id} L{r.level}: {r.approver_name} ({r.approver_role}) status={r.status.value}")

        print("\n--- 步骤4: 审批人A通过 ---")
        approval = crud.approve_approval(db, approval.id, ApprovalAction(opinion="同意"), approver_a)
        print(f"  审批后: status={approval.status.value}, level={approval.current_level}/{approval.total_levels}")
        records = crud.get_approval_node_records(db, approval.id)
        for r in records:
            if r.level == 1:
                print(f"    #{r.id} {r.approver_name}: status={r.status.value} transfer_status={r.transfer_status}")

        print("\n--- 步骤5: 审批人B转审给C ---")
        b_record = None
        for r in records:
            if r.level == 1 and r.approver_name == get_user_display_name(approver_b) and r.status == ApprovalStatus.PENDING:
                b_record = r
                break

        if not b_record:
            print("  ✗ 找不到B的待处理记录！尝试用角色匹配...")
            for r in records:
                if r.level == 1 and r.status == ApprovalStatus.PENDING and r.transfer_status != TransferStatus.TRANSFERRED:
                    b_record = r
                    break

        if not b_record:
            print("  ✗ 仍然找不到，跳过转审测试")
        else:
            print(f"  找到B的记录: #{b_record.id}, {b_record.approver_name}")
            approval = crud.transfer_approval(
                db, approval.id, b_record.id, transfer_c.id, "出差中，请帮忙审批", approver_b
            )

            records = crud.get_approval_node_records(db, approval.id)
            print(f"  转审后所有Level 1记录:")
            for r in records:
                if r.level == 1:
                    print(f"    #{r.id} {r.approver_name}: status={r.status.value} "
                          f"transfer_status={r.transfer_status} record_type={r.record_type} "
                          f"source_record_id={r.source_record_id}")

        print("\n--- 步骤6: 转审接收人C审批 ---")
        try:
            approval = crud.approve_approval(db, approval.id, ApprovalAction(opinion="同意"), transfer_c)
            print(f"  C审批后: status={approval.status.value}, level={approval.current_level}/{approval.total_levels}")
        except Exception as e:
            print(f"  ✗ C审批失败: {e}")

        records = crud.get_approval_node_records(db, approval.id)
        print(f"  所有Level 1记录:")
        for r in records:
            if r.level == 1:
                print(f"    #{r.id} {r.approver_name}: status={r.status.value} transfer_status={r.transfer_status}")

        active_l1 = [r for r in records if r.level == 1 and r.transfer_status != TransferStatus.TRANSFERRED]
        all_approved = all(r.status == ApprovalStatus.APPROVED for r in active_l1)
        print(f"\n  Level 1 活跃记录: {len(active_l1)} 条, 全员通过: {all_approved}")
        print(f"  审批单: level={approval.current_level}/{approval.total_levels}, status={approval.status.value}")

        if approval.current_level == 2 and approval.status == ApprovalStatus.PENDING:
            print("\n  ✓ 会签已全员通过，已进入Level 2")
        elif approval.current_level == 1:
            print("\n  ✗ BUG确认：会签应该已全员通过但仍停留在Level 1")

        print("\n--- 步骤7: 财务经理审批 ---")
        try:
            approval = crud.approve_approval(db, approval.id, ApprovalAction(opinion="同意"), finance)
            print(f"  财务审批后: status={approval.status.value}")
        except Exception as e:
            print(f"  ✗ 财务审批失败: {e}")

        if approval.status == ApprovalStatus.APPROVED:
            print("\n✓ 完整流程验证通过")
        else:
            print(f"\n✗ 流程未完成，当前状态: {approval.status.value}")

    except Exception as e:
        print(f"\n✗ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        print("\n清理...")
        try:
            for uname in ["bug_app", "bug_aa", "bug_ab", "bug_tc", "bug_fm"]:
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
