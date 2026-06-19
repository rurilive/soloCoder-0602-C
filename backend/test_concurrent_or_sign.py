#!/usr/bin/env python3
"""并发测试：或签节点双线程同时approve，验证行级锁和409冲突"""
import sys, os
os.environ["ASSET_JWT_SECRET"] = "test-secret-key-for-concurrent-test"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import threading
import time
from datetime import datetime
from app.database import SessionLocal
from app.models import (
    User, UserRole, Role, ApprovalStatus,
    ApprovalMode, ApprovalType, AssetCategory,
    ApprovalNodeRecord, TransferStatus,
    ApprovalChain, ApprovalChainNode, ApprovalChainNodeApprover,
    AssetLog,
)
from app.auth import get_user_display_name, get_password_hash
from app import crud
from app.schemas import (
    ApprovalCreate, ApprovalAction,
    ApprovalChainCreate, ChainNodeCreate, ChainNodeApproverCreate, AssetCreate,
)
from fastapi import HTTPException


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


class ConcurrentTestResult:
    def __init__(self):
        self.success_count = 0
        self.conflict_count = 0
        self.other_error_count = 0
        self.errors = []
        self.lock = threading.Lock()

    def add_success(self):
        with self.lock:
            self.success_count += 1

    def add_conflict(self, msg):
        with self.lock:
            self.conflict_count += 1
            self.errors.append(msg)

    def add_other_error(self, msg):
        with self.lock:
            self.other_error_count += 1
            self.errors.append(msg)


def worker_thread(approval_id, approver_id, approver_name, opinion, result, start_event):
    db = SessionLocal()
    try:
        from app.models import User
        approver = db.query(User).filter(User.id == approver_id).first()
        start_event.wait()
        approval = crud.approve_approval(
            db, approval_id, ApprovalAction(opinion=opinion), approver
        )
        result.add_success()
    except HTTPException as e:
        if e.status_code == 409:
            result.add_conflict(f"{approver_name}: HTTP 409 - {e.detail}")
        else:
            result.add_other_error(f"{approver_name}: HTTP {e.status_code} - {e.detail}")
    except Exception as e:
        result.add_other_error(f"{approver_name}: {type(e).__name__}: {e}")
    finally:
        db.close()


def test_concurrent_or_sign_approve():
    """测试或签节点双线程同时approve，验证只有一个成功，另一个返回409"""
    db = SessionLocal()
    print("=" * 70)
    print("并发测试：或签节点双线程同时approve")
    print("=" * 70)

    approval_id = None
    asset_id = None

    try:
        print("\n--- 步骤1: 创建用户 ---")
        applicant = create_user(db, "conc_app", "并发申请人", ["employee"])
        approver_a = create_user(db, "conc_aa", "并发经理A", ["dept_manager"])
        approver_b = create_user(db, "conc_ab", "并发经理B", ["dept_manager"])
        finance = create_user(db, "conc_fm", "并发财务", ["finance_manager"], "财务部")
        print(f"  申请人: {get_user_display_name(applicant)}")
        print(f"  审批人A: {get_user_display_name(approver_a)}")
        print(f"  审批人B: {get_user_display_name(approver_b)}")
        print(f"  财务: {get_user_display_name(finance)}")

        print("\n--- 步骤2: 创建2级审批链（第一级或签） ---")
        chain_data = ApprovalChainCreate(
            name="并发测试或签链",
            approval_type=ApprovalType.ALLOCATE,
            is_default=False,
            nodes=[
                ChainNodeCreate(
                    mode=ApprovalMode.OR_SIGN,
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

        print("\n--- 步骤3: 创建资产并提交审批 ---")
        asset_data = AssetCreate(
            name="并发测试资产", category=AssetCategory.COMPUTER, brand="Brand",
            model="Model", serial_number=f"CONC-{datetime.now().timestamp()}",
            purchase_price=5000.0, purchase_department="研发部",
        )
        asset = crud.create_asset(db, asset_data, applicant)
        asset_id = asset.id

        approval_data = ApprovalCreate(
            approval_type=ApprovalType.ALLOCATE,
            applicant=get_user_display_name(applicant),
            assignee=get_user_display_name(applicant),
            reason="并发测试或签",
        )
        approval = crud.create_approval(db, asset.id, approval_data, applicant)
        approval_id = approval.id
        print(f"  审批单#{approval.id}, status={approval.status.value}, level={approval.current_level}/{approval.total_levels}")

        records = crud.get_approval_node_records(db, approval.id)
        for r in records:
            print(f"    #{r.id} L{r.level}: {r.approver_name} ({r.approver_role}) status={r.status.value}")

        initial_log_count = db.query(AssetLog).filter(AssetLog.asset_id == asset.id).count()
        print(f"  初始日志数: {initial_log_count}")

        approver_a_id = approver_a.id
        approver_a_name = get_user_display_name(approver_a)
        approver_b_id = approver_b.id
        approver_b_name = get_user_display_name(approver_b)

        db.close()

        print("\n--- 步骤4: 双线程同时approve ---")
        result = ConcurrentTestResult()
        start_event = threading.Event()

        t1 = threading.Thread(
            target=worker_thread,
            args=(approval_id, approver_a_id, approver_a_name, "A同意", result, start_event)
        )
        t2 = threading.Thread(
            target=worker_thread,
            args=(approval_id, approver_b_id, approver_b_name, "B同意", result, start_event)
        )

        t1.start()
        t2.start()

        time.sleep(0.1)
        print("  启动两个线程，同时触发approve...")
        start_event.set()

        t1.join(timeout=30)
        t2.join(timeout=30)

        if t1.is_alive() or t2.is_alive():
            print("  ✗ 线程超时未完成")
            return False

        print(f"\n--- 步骤5: 验证结果 ---")
        print(f"  成功数: {result.success_count}")
        print(f"  409冲突数: {result.conflict_count}")
        print(f"  其他错误数: {result.other_error_count}")
        for err in result.errors:
            print(f"    - {err}")

        db_verify = SessionLocal()
        try:
            approval = crud.get_approval(db_verify, approval_id)
            records = crud.get_approval_node_records(db_verify, approval_id)
            print(f"\n  审批单最终状态: level={approval.current_level}/{approval.total_levels}, status={approval.status.value}")
            for r in records:
                print(f"    #{r.id} L{r.level}: {r.approver_name} status={r.status.value}, opinion={r.opinion}")

            final_log_count = db_verify.query(AssetLog).filter(AssetLog.asset_id == asset_id).count()
            new_logs = final_log_count - initial_log_count
            print(f"  新增日志数: {new_logs}")

            all_logs = db_verify.query(AssetLog).filter(AssetLog.asset_id == asset_id).order_by(AssetLog.id.desc()).all()
            for log in all_logs[:5]:
                print(f"    #{log.id} {log.action}: {log.detail[:50]}...")

            print("\n--- 验证检查 ---")
            passed = True

            if result.success_count != 1:
                print(f"  ✗ 期望1个成功，实际{result.success_count}个")
                passed = False
            else:
                print("  ✓ 成功数正确：1个线程成功推进")

            if result.conflict_count != 1:
                print(f"  ✗ 期望1个409冲突，实际{result.conflict_count}个")
                passed = False
            else:
                print("  ✓ 冲突数正确：1个线程收到409冲突")

            if result.other_error_count != 0:
                print(f"  ✗ 存在其他错误: {result.other_error_count}个")
                passed = False
            else:
                print("  ✓ 无其他错误")

            if approval.current_level != 2:
                print(f"  ✗ 期望推进到level=2，实际level={approval.current_level}")
                passed = False
            else:
                print("  ✓ 级别正确：从level=1推进到level=2")

            if approval.current_level > 2:
                print(f"  ✗ 检测到跳级！当前level={approval.current_level}，超过了期望的2")
                passed = False
            else:
                print("  ✓ 无跳级现象")

            l1_records = [r for r in records if r.level == 1]
            l1_approved = sum(1 for r in l1_records if r.status == ApprovalStatus.APPROVED)
            if l1_approved != len(l1_records):
                print(f"  ✗ Level 1记录状态异常: {len(l1_records)}条中{l1_approved}条已通过")
                passed = False
            else:
                print(f"  ✓ Level 1所有{len(l1_records)}条记录均已通过")

            if new_logs != 1:
                print(f"  ✗ 期望新增1条日志，实际新增{new_logs}条（可能重复写入）")
                passed = False
            else:
                print("  ✓ 日志正确：仅新增1条审批通过日志")

            if passed:
                print("\n" + "=" * 70)
                print("✓ 并发测试通过！或签节点并发竞态问题已修复")
                print("=" * 70)
            else:
                print("\n" + "=" * 70)
                print("✗ 并发测试失败！")
                print("=" * 70)

            return passed
        finally:
            db_verify.close()

    except Exception as e:
        print(f"\n✗ 测试异常: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_concurrent_reject():
    """测试或签节点双线程同时reject，验证只有一个成功，另一个返回409"""
    db = SessionLocal()
    print("\n" + "=" * 70)
    print("并发测试：或签节点双线程同时reject")
    print("=" * 70)

    approval_id = None
    asset_id = None

    try:
        print("\n--- 步骤1: 创建用户 ---")
        applicant = create_user(db, "conc_rej_app", "并发驳回申请人", ["employee"])
        approver_a = create_user(db, "conc_rej_aa", "并发驳回经理A", ["dept_manager"])
        approver_b = create_user(db, "conc_rej_ab", "并发驳回经理B", ["dept_manager"])
        finance = create_user(db, "conc_rej_fm", "并发驳回财务", ["finance_manager"], "财务部")

        print("\n--- 步骤2: 创建2级审批链（第一级或签） ---")
        chain_data = ApprovalChainCreate(
            name="并发测试驳回或签链",
            approval_type=ApprovalType.ALLOCATE,
            is_default=False,
            nodes=[
                ChainNodeCreate(
                    mode=ApprovalMode.OR_SIGN,
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

        print("\n--- 步骤3: 创建资产并提交审批 ---")
        asset_data = AssetCreate(
            name="并发驳回测试资产", category=AssetCategory.COMPUTER, brand="Brand",
            model="Model", serial_number=f"CONC-REJ-{datetime.now().timestamp()}",
            purchase_price=5000.0, purchase_department="研发部",
        )
        asset = crud.create_asset(db, asset_data, applicant)
        asset_id = asset.id

        approval_data = ApprovalCreate(
            approval_type=ApprovalType.ALLOCATE,
            applicant=get_user_display_name(applicant),
            assignee=get_user_display_name(applicant),
            reason="并发测试驳回或签",
        )
        approval = crud.create_approval(db, asset.id, approval_data, applicant)
        approval_id = approval.id
        print(f"  审批单#{approval.id}, status={approval.status.value}, level={approval.current_level}/{approval.total_levels}")

        initial_log_count = db.query(AssetLog).filter(AssetLog.asset_id == asset.id).count()

        approver_a_id = approver_a.id
        approver_a_name = get_user_display_name(approver_a)
        approver_b_id = approver_b.id
        approver_b_name = get_user_display_name(approver_b)

        db.close()

        print("\n--- 步骤4: 双线程同时reject ---")

        def reject_worker(approval_id, approver_id, approver_name, opinion, result, start_event):
            db = SessionLocal()
            try:
                from app.models import User
                approver = db.query(User).filter(User.id == approver_id).first()
                start_event.wait()
                approval = crud.reject_approval(
                    db, approval_id, ApprovalAction(opinion=opinion), approver
                )
                result.add_success()
            except HTTPException as e:
                if e.status_code == 409:
                    result.add_conflict(f"{approver_name}: HTTP 409 - {e.detail}")
                else:
                    result.add_other_error(f"{approver_name}: HTTP {e.status_code} - {e.detail}")
            except Exception as e:
                result.add_other_error(f"{approver_name}: {type(e).__name__}: {e}")
            finally:
                db.close()

        result = ConcurrentTestResult()
        start_event = threading.Event()

        t1 = threading.Thread(
            target=reject_worker,
            args=(approval_id, approver_a_id, approver_a_name, "A驳回", result, start_event)
        )
        t2 = threading.Thread(
            target=reject_worker,
            args=(approval_id, approver_b_id, approver_b_name, "B驳回", result, start_event)
        )

        t1.start()
        t2.start()

        time.sleep(0.1)
        print("  启动两个线程，同时触发reject...")
        start_event.set()

        t1.join(timeout=30)
        t2.join(timeout=30)

        print(f"\n--- 步骤5: 验证结果 ---")
        print(f"  成功数: {result.success_count}")
        print(f"  409冲突数: {result.conflict_count}")
        print(f"  其他错误数: {result.other_error_count}")
        for err in result.errors:
            print(f"    - {err}")

        db_verify = SessionLocal()
        try:
            approval = crud.get_approval(db_verify, approval_id)
            print(f"  审批单最终状态: status={approval.status.value}")

            final_log_count = db_verify.query(AssetLog).filter(AssetLog.asset_id == asset_id).count()
            new_logs = final_log_count - initial_log_count
            print(f"  新增日志数: {new_logs}")

            passed = True
            if result.success_count + result.conflict_count != 2:
                print(f"  ✗ 结果异常: 成功{result.success_count}, 冲突{result.conflict_count}")
                passed = False

            if result.success_count >= 1 and result.conflict_count >= 1:
                print("  ✓ 至少1个成功，至少1个冲突：并发锁生效")
            elif result.success_count == 2:
                print("  ✗ 两个都成功了！并发锁未生效")
                passed = False

            if approval.status != ApprovalStatus.REJECTED:
                print(f"  ✗ 审批单状态异常: {approval.status.value}")
                passed = False
            else:
                print("  ✓ 审批单已正确驳回")

            if new_logs > 1:
                print(f"  ✗ 日志重复写入: 新增{new_logs}条")
                passed = False
            else:
                print(f"  ✓ 日志正确：新增{new_logs}条")

            return passed
        finally:
            db_verify.close()

    except Exception as e:
        print(f"\n✗ 测试异常: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_concurrent_3thread_or_sign_approve():
    """测试或签节点3线程同时approve，验证只有一个成功，另两个返回409"""
    db = SessionLocal()
    print("\n" + "=" * 70)
    print("并发测试：或签节点3线程同时approve")
    print("=" * 70)

    approval_id = None
    asset_id = None

    try:
        print("\n--- 步骤1: 创建用户 ---")
        applicant = create_user(db, "conc_3t_app", "并发3线程申请人", ["employee"])
        approver_a = create_user(db, "conc_3t_a", "并发3t经理A", ["dept_manager"])
        approver_b = create_user(db, "conc_3t_b", "并发3t经理B", ["dept_manager"])
        approver_c = create_user(db, "conc_3t_c", "并发3t经理C", ["dept_manager"])
        finance = create_user(db, "conc_3t_fm", "并发3t财务", ["finance_manager"], "财务部")
        print(f"  申请人: {get_user_display_name(applicant)}")
        print(f"  审批人A: {get_user_display_name(approver_a)}")
        print(f"  审批人B: {get_user_display_name(approver_b)}")
        print(f"  审批人C: {get_user_display_name(approver_c)}")
        print(f"  财务: {get_user_display_name(finance)}")

        print("\n--- 步骤2: 创建2级审批链（第一级或签3人） ---")
        chain_data = ApprovalChainCreate(
            name="并发3t测试或签链",
            approval_type=ApprovalType.ALLOCATE,
            is_default=False,
            nodes=[
                ChainNodeCreate(
                    mode=ApprovalMode.OR_SIGN,
                    approvers=[
                        ChainNodeApproverCreate(approver_role="dept_manager", approver_name=get_user_display_name(approver_a)),
                        ChainNodeApproverCreate(approver_role="dept_manager", approver_name=get_user_display_name(approver_b)),
                        ChainNodeApproverCreate(approver_role="dept_manager", approver_name=get_user_display_name(approver_c)),
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

        print("\n--- 步骤3: 创建资产并提交审批 ---")
        asset_data = AssetCreate(
            name="并发3t测试资产", category=AssetCategory.COMPUTER, brand="Brand",
            model="Model", serial_number=f"CONC3T-{datetime.now().timestamp()}",
            purchase_price=5000.0, purchase_department="研发部",
        )
        asset = crud.create_asset(db, asset_data, applicant)

        approval_data = ApprovalCreate(
            asset_id=asset.id,
            approval_type=ApprovalType.ALLOCATE,
            applicant=get_user_display_name(applicant),
            assignee=get_user_display_name(applicant),
            reason="3线程并发测试或签",
            chain_id=chain.id,
        )
        approval = crud.create_approval(db, asset.id, approval_data, applicant)
        approval_id = approval.id
        asset_id = asset.id
        initial_level = approval.current_level
        print(f"  审批单#{approval.id}, status={approval.status.value}, level={approval.current_level}/{approval.total_levels}")
        records = crud.get_approval_node_records(db, approval.id)
        for r in records:
            print(f"    #{r.id} L{r.level}: {r.approver_name} ({r.approver_role}) status={r.status.value}")
        initial_log_count = db.query(AssetLog).filter(AssetLog.asset_id == asset.id).count()
        print(f"  初始日志数: {initial_log_count}")

        approver_a_id = approver_a.id
        approver_a_name = get_user_display_name(approver_a)
        approver_b_id = approver_b.id
        approver_b_name = get_user_display_name(approver_b)
        approver_c_id = approver_c.id
        approver_c_name = get_user_display_name(approver_c)

        db.close()

        print("\n--- 步骤4: 3线程同时approve ---")
        result = ConcurrentTestResult()
        start_event = threading.Event()

        t1 = threading.Thread(
            target=worker_thread,
            args=(approval_id, approver_a_id, approver_a_name, "A同意", result, start_event)
        )
        t2 = threading.Thread(
            target=worker_thread,
            args=(approval_id, approver_b_id, approver_b_name, "B同意", result, start_event)
        )
        t3 = threading.Thread(
            target=worker_thread,
            args=(approval_id, approver_c_id, approver_c_name, "C同意", result, start_event)
        )

        t1.start()
        t2.start()
        t3.start()

        time.sleep(0.15)
        print("  启动三个线程，同时触发approve...")
        start_event.set()

        t1.join()
        t2.join()
        t3.join()

        print("\n--- 步骤5: 验证结果 ---")
        print(f"  成功数: {result.success_count}")
        print(f"  409冲突数: {result.conflict_count}")
        print(f"  其他错误数: {result.other_error_count}")
        if result.errors:
            for err in result.errors:
                print(f"    - {err}")

        db_verify = SessionLocal()
        try:
            approval = crud.get_approval(db_verify, approval_id)
            records = crud.get_approval_node_records(db_verify, approval_id)
            print(f"\n  审批单最终状态: level={approval.current_level}/{approval.total_levels}, status={approval.status.value}")
            for r in records:
                print(f"    #{r.id} L{r.level}: {r.approver_name} status={r.status.value}, opinion={r.opinion}")

            final_log_count = db_verify.query(AssetLog).filter(AssetLog.asset_id == asset_id).count()
            new_logs = final_log_count - initial_log_count
            print(f"  新增日志数: {new_logs}")

            passed = True

            if result.success_count != 1:
                print(f"  ✗ 成功数错误：预期1个成功推进，实际{result.success_count}个")
                passed = False
            else:
                print("  ✓ 成功数正确：1个线程成功推进")

            if result.conflict_count != 2:
                print(f"  ✗ 冲突数错误：预期2个409冲突，实际{result.conflict_count}个")
                passed = False
            else:
                print("  ✓ 冲突数正确：2个线程收到409冲突")

            if result.other_error_count > 0:
                print(f"  ✗ 存在其他错误")
                passed = False
            else:
                print("  ✓ 无其他错误")

            initial_level = 1
            if approval.current_level != initial_level + 1:
                print(f"  ✗ 级别错误：预期推进到level={initial_level + 1}，实际level={approval.current_level}")
                passed = False
            else:
                print(f"  ✓ 级别正确：从level={initial_level}推进到level={initial_level + 1}")

            if approval.current_level - initial_level > 1:
                print(f"  ✗ 跳级现象：一次推进了{approval.current_level - initial_level}级，从level={initial_level}跳到level={approval.current_level}")
                passed = False

            l1_records = [r for r in records if r.level == 1]
            l1_approved = [r for r in l1_records if r.status == ApprovalStatus.APPROVED]
            if len(l1_approved) != 3:
                print(f"  ✗ Level 1通过记录异常：{len(l1_approved)}/3条通过")
                passed = False
            else:
                print("  ✓ Level 1所有3条记录均已通过")

            if new_logs > 1:
                print(f"  ✗ 日志重复写入: 新增{new_logs}条")
                passed = False
            else:
                print(f"  ✓ 日志正确：仅新增1条审批通过日志")

            return passed
        finally:
            db_verify.close()

    except Exception as e:
        print(f"\n✗ 测试异常: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("或签节点并发竞态修复验证测试")
    print("=" * 70)

    test1_passed = test_concurrent_or_sign_approve()
    test2_passed = test_concurrent_reject()
    test3_passed = test_concurrent_3thread_or_sign_approve()

    print("\n" + "=" * 70)
    print("测试汇总")
    print("=" * 70)
    print(f"  并发approve(2线程): {'✓ 通过' if test1_passed else '✗ 失败'}")
    print(f"  并发reject(2线程): {'✓ 通过' if test2_passed else '✗ 失败'}")
    print(f"  并发approve(3线程): {'✓ 通过' if test3_passed else '✗ 失败'}")

    if test1_passed and test2_passed and test3_passed:
        print("\n✓ 所有测试通过！并发竞态问题已修复")
        sys.exit(0)
    else:
        print("\n✗ 部分测试失败！")
        sys.exit(1)
