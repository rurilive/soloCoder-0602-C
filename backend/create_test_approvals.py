#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["ASSET_JWT_SECRET"] = "test-secret-key-for-development"

from app.database import SessionLocal
from app.models import (
    User, Asset, Approval, ApprovalChain, ApprovalChainNode, ApprovalNodeRecord,
    ApprovalType, ApprovalStatus, AssetStatus,
)

db = SessionLocal()

try:
    print("=" * 60)
    print("创建审批单测试数据")
    print("=" * 60)

    emp1 = db.query(User).filter(User.username == "emp1").first()
    emp2 = db.query(User).filter(User.username == "emp2").first()
    dept_mgr = db.query(User).filter(User.username == "dept_mgr").first()
    asset_admin = db.query(User).filter(User.username == "asset_admin").first()

    emp1_asset = db.query(Asset).filter(Asset.assignee == "李员工").first()
    emp2_asset = db.query(Asset).filter(Asset.assignee == "王员工").first()
    unassigned_asset = db.query(Asset).filter(Asset.assignee == None).first()

    print("\n1. 查找或创建审批链...")
    chain = db.query(ApprovalChain).filter(ApprovalChain.approval_type == "scrap").first()
    if not chain:
        chain = ApprovalChain(
            name="资产报废审批",
            approval_type=ApprovalType.SCRAP,
            is_default=True,
        )
        db.add(chain)
        db.flush()

        nodes = [
            ApprovalChainNode(chain_id=chain.id, level=1, approver_role="dept_manager", approver_name="部门经理"),
            ApprovalChainNode(chain_id=chain.id, level=2, approver_role="asset_admin", approver_name="资产管理员"),
        ]
        for node in nodes:
            db.add(node)
        db.flush()
        print(f"  ✓ 创建审批链: {chain.name}")
    else:
        print(f"  ✓ 审批链已存在: {chain.name}")

    chain_nodes = db.query(ApprovalChainNode).filter(
        ApprovalChainNode.chain_id == chain.id
    ).order_by(ApprovalChainNode.level).all()
    print(f"  审批节点: {[f'Level{n.level}:{n.approver_role}({n.approver_name})' for n in chain_nodes]}")

    def create_approval(applicant_user, asset_obj, reason):
        existing = db.query(Approval).filter(
            Approval.applicant == applicant_user.real_name,
            Approval.asset_id == asset_obj.id,
        ).first()
        if existing:
            print(f"  ✓ 审批单已存在: #{existing.id}")
            return existing

        approval = Approval(
            asset_id=asset_obj.id,
            approval_type=ApprovalType.SCRAP,
            applicant=applicant_user.real_name,
            status=ApprovalStatus.PENDING,
            current_level=1,
            total_levels=len(chain_nodes),
            chain_id=chain.id,
            reason=reason,
            previous_status=asset_obj.status,
        )
        db.add(approval)
        db.flush()
        print(f"  ✓ 创建审批单: #{approval.id} - {approval.approval_type} - 申请人: {approval.applicant}")

        for node in chain_nodes:
            record = ApprovalNodeRecord(
                approval_id=approval.id,
                chain_node_id=node.id,
                level=node.level,
                approver_role=node.approver_role,
                approver_name=node.approver_name,
                status=ApprovalStatus.PENDING,
            )
            db.add(record)
        db.flush()
        print(f"    ✓ 创建 {len(chain_nodes)} 个审批节点记录，所有节点状态都为 PENDING")

        return approval

    print("\n2. 创建测试审批单1 - emp1(李员工) 申请报废资产")
    approval1 = create_approval(emp1, emp1_asset, "设备老旧需要报废")

    print("\n3. 创建测试审批单2 - emp2(王员工) 申请报废资产")
    approval2 = create_approval(emp2, emp2_asset, "设备损坏需要报废")

    db.commit()

    print("\n4. 验证审批单节点状态...")
    for approval in [approval1, approval2]:
        records = db.query(ApprovalNodeRecord).filter(
            ApprovalNodeRecord.approval_id == approval.id
        ).all()
        print(f"\n  审批单 #{approval.id}:")
        print(f"    申请人: {approval.applicant}")
        print(f"    状态: {approval.status}")
        print(f"    当前审批层级: {approval.current_level}")
        print(f"    审批节点:")
        for r in sorted(records, key=lambda x: x.level):
            print(f"      Level {r.level}: {r.approver_role}({r.approver_name}) - {r.status}")

    print("\n" + "=" * 60)
    print("重点说明:")
    print("所有审批单的所有节点状态都是 PENDING")
    print("按照旧逻辑(只匹配current_level):")
    print("  - dept_manager 能看到审批单(level 1节点是dept_manager, current_level=1)")
    print("  - asset_admin 不能看到审批单(当前只匹配到level 1节点)")
    print("按照新逻辑(匹配所有PENDING节点):")
    print("  - dept_manager 能看到审批单")
    print("  - asset_admin 也能看到审批单(level 2节点也是PENDING)")
    print("=" * 60)

finally:
    db.close()
