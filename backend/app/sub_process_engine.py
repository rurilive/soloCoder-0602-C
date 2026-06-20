import logging
from typing import Any
from app.models import (
    ApprovalChainNode,
    ChainNodeType,
    ApprovalChain,
)
from sqlalchemy.orm import Session
from fastapi import HTTPException

logger = logging.getLogger(__name__)

MAX_NESTING_LEVEL = 3


def detect_sub_process_cycle(
    db: Session,
    chain_id: int,
    visited_chain_ids: set[int] | None = None,
    current_level: int = 0,
) -> tuple[bool, list[int]]:
    """
    检测子流程是否存在循环引用。

    Args:
        db: 数据库会话
        chain_id: 要检测的审批链ID
        visited_chain_ids: 已访问的审批链ID集合
        current_level: 当前嵌套层级

    Returns:
        (是否存在循环, 循环路径)
    """
    if visited_chain_ids is None:
        visited_chain_ids = set()

    if chain_id in visited_chain_ids:
        return True, list(visited_chain_ids) + [chain_id]

    if current_level >= MAX_NESTING_LEVEL:
        return False, []

    visited_chain_ids.add(chain_id)

    nodes = (
        db.query(ApprovalChainNode)
        .filter(ApprovalChainNode.chain_id == chain_id)
        .filter(ApprovalChainNode.node_type == ChainNodeType.SUB_PROCESS)
        .all()
    )

    for node in nodes:
        if node.sub_process_chain_id:
            has_cycle, path = detect_sub_process_cycle(
                db,
                node.sub_process_chain_id,
                visited_chain_ids.copy(),
                current_level + 1,
            )
            if has_cycle:
                return True, path

    return False, []


def get_max_nesting_level(
    db: Session,
    chain_id: int,
    current_level: int = 0,
    visited: set[int] | None = None,
) -> int:
    """
    计算审批链的最大嵌套深度。

    Args:
        db: 数据库会话
        chain_id: 审批链ID
        current_level: 当前层级
        visited: 已访问的审批链ID集合

    Returns:
        最大嵌套深度
    """
    if visited is None:
        visited = set()

    if chain_id in visited:
        return current_level

    visited.add(chain_id)

    nodes = (
        db.query(ApprovalChainNode)
        .filter(ApprovalChainNode.chain_id == chain_id)
        .filter(ApprovalChainNode.node_type == ChainNodeType.SUB_PROCESS)
        .all()
    )

    max_depth = current_level

    for node in nodes:
        if node.sub_process_chain_id:
            depth = get_max_nesting_level(
                db,
                node.sub_process_chain_id,
                current_level + 1,
                visited.copy(),
            )
            max_depth = max(max_depth, depth)

    return max_depth


def validate_sub_process_chain(
    db: Session,
    node: ApprovalChainNode,
    parent_chain_id: int,
    current_nesting_level: int = 0,
) -> None:
    """
    验证子流程节点配置是否合法。

    Args:
        db: 数据库会话
        node: 子流程节点
        parent_chain_id: 父审批链ID
        current_nesting_level: 当前嵌套层级

    Raises:
        HTTPException: 如果配置不合法
    """
    if node.node_type != ChainNodeType.SUB_PROCESS:
        return

    if not node.sub_process_chain_id:
        raise HTTPException(
            status_code=400,
            detail=f"子流程节点（level={node.level}）缺少引用的审批链ID",
        )

    if node.sub_process_chain_id == parent_chain_id:
        raise HTTPException(
            status_code=400,
            detail=f"子流程节点（level={node.level}）不能引用自身所在的审批链",
        )

    sub_chain = db.query(ApprovalChain).filter(
        ApprovalChain.id == node.sub_process_chain_id
    ).first()

    if not sub_chain:
        raise HTTPException(
            status_code=404,
            detail=f"子流程节点（level={node.level}）引用的审批链不存在",
        )

    has_cycle, cycle_path = detect_sub_process_cycle(
        db,
        node.sub_process_chain_id,
        {parent_chain_id},
        current_nesting_level,
    )

    if has_cycle:
        path_str = " -> ".join([f"Chain({cid})" for cid in cycle_path])
        raise HTTPException(
            status_code=400,
            detail=f"子流程节点（level={node.level}）存在循环引用: {path_str}",
        )

    max_depth = get_max_nesting_level(
        db,
        node.sub_process_chain_id,
        current_nesting_level + 1,
    )

    if max_depth >= MAX_NESTING_LEVEL:
        raise HTTPException(
            status_code=400,
            detail=(
                f"子流程节点（level={node.level}）嵌套层数超过限制，"
                f"当前最大嵌套深度为 {max_depth}，最多允许 {MAX_NESTING_LEVEL} 层"
            ),
        )


def get_sub_process_path_items(
    db: Session,
    node: ApprovalChainNode,
    ctx: Any,
    current_nesting_level: int,
    parent_path_items_getter,
) -> list[dict] | None:
    """
    获取子流程的路径项。

    Args:
        db: 数据库会话
        node: 子流程节点
        ctx: 条件评估上下文
        current_nesting_level: 当前嵌套层级
        parent_path_items_getter: 父路径项获取函数

    Returns:
        子流程的路径项列表
    """
    if node.node_type != ChainNodeType.SUB_PROCESS or not node.sub_process_chain_id:
        return None

    from app.condition_engine import resolve_next_level
    from app.parallel_engine import get_parallel_path_levels, parse_parallel_groups

    sub_chain_id = node.sub_process_chain_id

    all_nodes = (
        db.query(ApprovalChainNode)
        .options(
            joinedload(ApprovalChainNode.approvers),
            joinedload(ApprovalChainNode.conditions).joinedload(
                ApprovalChainCondition.rules
            ),
        )
        .filter(ApprovalChainNode.chain_id == sub_chain_id)
        .order_by(ApprovalChainNode.level.asc())
        .all()
    )

    if not all_nodes:
        return None

    chain_nodes_by_level = {n.level: n for n in all_nodes}

    has_parallel = any(n.node_type != ChainNodeType.APPROVAL for n in all_nodes)

    if has_parallel:
        return get_parallel_path_levels(all_nodes, ctx) or []
    else:
        all_levels = set(chain_nodes_by_level.keys())
        visited: set[int] = set()
        current_level = 1
        max_iterations = len(all_levels) * 2 + 10
        iterations = 0
        resolved_path_levels: list[int] = []

        while current_level is not None and current_level in all_levels and iterations < max_iterations:
            iterations += 1
            if current_level in visited:
                logger.warning(
                    "子流程路径检测到环路: chain_id=%s, level=%s",
                    sub_chain_id,
                    current_level,
                )
                break
            visited.add(current_level)
            resolved_path_levels.append(current_level)
            sub_node = chain_nodes_by_level[current_level]
            if sub_node.node_type == ChainNodeType.SUB_PROCESS:
                sub_items = get_sub_process_path_items(
                    db,
                    sub_node,
                    ctx,
                    current_nesting_level + 1,
                    parent_path_items_getter,
                )
                if sub_items:
                    for item in sub_items:
                        item["nesting_level"] = current_nesting_level + 1
                        item["parent_node_id"] = node.id
            current_level = resolve_next_level(sub_node, ctx, all_levels)

        path_items: list[dict] = []
        for lv in resolved_path_levels:
            path_items.append({
                "type": "approval",
                "level": lv,
                "node": chain_nodes_by_level.get(lv),
                "nesting_level": current_nesting_level,
                "parent_node_id": node.id,
            })
        return path_items


def flatten_sub_process_records(
    records: list,
    nesting_level: int = 0,
) -> list:
    """
    展平嵌套的子流程记录，用于前端时间线展示。

    Args:
        records: 记录列表
        nesting_level: 当前嵌套层级

    Returns:
        展平后的记录列表
    """
    result = []
    for rec in records:
        rec_dict = rec if isinstance(rec, dict) else {
            **{k: getattr(rec, k, None) for k in [
                "id", "approval_id", "chain_node_id", "level",
                "chain_node_level", "parallel_group_id",
                "branch_id", "branch_index",
                "approver_role", "approver_name",
                "status", "opinion", "acted_at",
                "sub_process_id", "sub_process_nesting_level",
                "parent_record_id", "node_type",
                "sub_process_chain_id", "created_at",
            ]},
            "sub_process_records": getattr(rec, "sub_process_records", []),
        }
        rec_dict["nesting_level"] = nesting_level
        rec_dict["is_sub_process"] = rec_dict.get("node_type") == ChainNodeType.SUB_PROCESS
        rec_dict["collapsed"] = False
        result.append(rec_dict)

        if rec_dict.get("sub_process_records"):
            sub_records = flatten_sub_process_records(
                rec_dict["sub_process_records"],
                nesting_level + 1,
            )
            for sub_rec in sub_records:
                sub_rec["parent_record_id"] = rec_dict["id"]
                result.append(sub_rec)

    return result


def build_nested_sub_process_records(
    all_records: list,
    parent_id: int | None = None,
) -> list:
    """
    从扁平化的记录列表构建嵌套结构。

    Args:
        all_records: 所有记录
        parent_id: 父记录ID

    Returns:
        嵌套结构的记录列表
    """
    result = []
    for rec in all_records:
        if rec.parent_record_id == parent_id:
            rec.sub_process_records = build_nested_sub_process_records(
                all_records,
                rec.id,
            )
            result.append(rec)
    return result
