import logging
import uuid
from typing import Any
from app.models import (
    ApprovalChainNode,
    ChainNodeType,
    ApprovalStatus,
    ApprovalMode,
)

logger = logging.getLogger(__name__)


class ParallelBranch:
    def __init__(self, branch_id: str, branch_index: int, nodes: list[ApprovalChainNode]):
        self.branch_id = branch_id
        self.branch_index = branch_index
        self.nodes = nodes

    def get_start_level(self) -> int | None:
        if not self.nodes:
            return None
        return self.nodes[0].level

    def get_end_level(self) -> int | None:
        if not self.nodes:
            return None
        return self.nodes[-1].level


class ParallelGroup:
    def __init__(self, group_id: str, start_node: ApprovalChainNode, end_node: ApprovalChainNode, branches: list[ParallelBranch]):
        self.group_id = group_id
        self.start_node = start_node
        self.end_node = end_node
        self.branches = branches

    def get_branch_count(self) -> int:
        return len(self.branches)

    def get_branch_by_index(self, index: int) -> ParallelBranch | None:
        for b in self.branches:
            if b.branch_index == index:
                return b
        return None


def parse_parallel_groups(nodes: list[ApprovalChainNode]) -> dict[str, ParallelGroup]:
    level_map: dict[int, ApprovalChainNode] = {n.level: n for n in nodes}
    groups: dict[str, ParallelGroup] = {}

    parallel_start_nodes = [n for n in nodes if n.node_type == ChainNodeType.PARALLEL_START]

    for start_node in parallel_start_nodes:
        group_id = start_node.parallel_group_id
        if not group_id:
            continue

        end_node = None
        for n in nodes:
            if n.node_type == ChainNodeType.PARALLEL_END and n.parallel_group_id == group_id:
                end_node = n
                break

        if not end_node:
            logger.warning("并行组 %s 未找到对应的并行结束节点", group_id)
            continue

        if end_node.level <= start_node.level:
            logger.warning("并行组 %s 配置错误：结束节点级别必须大于开始节点", group_id)
            continue

        branch_nodes_map: dict[str, list[ApprovalChainNode]] = {}
        branch_index_map: dict[str, int] = {}

        for n in nodes:
            if n.level <= start_node.level or n.level >= end_node.level:
                continue
            if n.parallel_group_id != group_id:
                continue
            if not n.branch_id:
                continue

            if n.branch_id not in branch_nodes_map:
                branch_nodes_map[n.branch_id] = []
                branch_index_map[n.branch_id] = n.branch_index or 0
            branch_nodes_map[n.branch_id].append(n)

        branches: list[ParallelBranch] = []
        for branch_id, branch_nodes in branch_nodes_map.items():
            sorted_nodes = sorted(branch_nodes, key=lambda x: x.level)
            branch = ParallelBranch(
                branch_id=branch_id,
                branch_index=branch_index_map.get(branch_id, 0),
                nodes=sorted_nodes,
            )
            branches.append(branch)

        branches.sort(key=lambda b: b.branch_index)

        groups[group_id] = ParallelGroup(
            group_id=group_id,
            start_node=start_node,
            end_node=end_node,
            branches=branches,
        )

    return groups


def detect_parallel_deadlock(nodes: list[ApprovalChainNode]) -> list[str] | None:
    errors: list[str] = []

    level_map: dict[int, ApprovalChainNode] = {n.level: n for n in nodes}
    parallel_start_nodes = [n for n in nodes if n.node_type == ChainNodeType.PARALLEL_START]
    parallel_end_nodes = [n for n in nodes if n.node_type == ChainNodeType.PARALLEL_END]

    group_ids_start: dict[str, ApprovalChainNode] = {}
    for n in parallel_start_nodes:
        if not n.parallel_group_id:
            errors.append(f"并行开始节点 L{n.level} 缺少 parallel_group_id")
            continue
        if n.parallel_group_id in group_ids_start:
            errors.append(f"并行组 {n.parallel_group_id} 存在多个开始节点")
        group_ids_start[n.parallel_group_id] = n

    group_ids_end: dict[str, ApprovalChainNode] = {}
    for n in parallel_end_nodes:
        if not n.parallel_group_id:
            errors.append(f"并行结束节点 L{n.level} 缺少 parallel_group_id")
            continue
        if n.parallel_group_id in group_ids_end:
            errors.append(f"并行组 {n.parallel_group_id} 存在多个结束节点")
        group_ids_end[n.parallel_group_id] = n

    for gid, start_node in group_ids_start.items():
        if gid not in group_ids_end:
            errors.append(f"并行组 {gid} 缺少对应的结束节点")
            continue
        end_node = group_ids_end[gid]
        if end_node.level <= start_node.level:
            errors.append(f"并行组 {gid} 结束节点级别必须大于开始节点")

    for gid, end_node in group_ids_end.items():
        if gid not in group_ids_start:
            errors.append(f"并行组 {gid} 缺少对应的开始节点")

    groups = parse_parallel_groups(nodes)
    for gid, group in groups.items():
        if group.get_branch_count() < 2:
            errors.append(f"并行组 {gid} 至少需要 2 个分支")

        branch_count = group.get_branch_count()
        for i in range(branch_count):
            if group.get_branch_by_index(i) is None:
                errors.append(f"并行组 {gid} 缺少分支索引 {i}")

        start_level = group.start_node.level
        end_level = group.end_node.level
        for level in range(start_level + 1, end_level):
            node = level_map.get(level)
            if node and node.node_type == ChainNodeType.APPROVAL and not node.branch_id:
                errors.append(f"并行组 {gid} 内部节点 L{level} 缺少 branch_id")
            if node and node.parallel_group_id != gid and node.node_type != ChainNodeType.PARALLEL_START and node.node_type != ChainNodeType.PARALLEL_END:
                if start_level < level < end_level:
                    errors.append(f"节点 L{level} 位于并行组 {gid} 范围内但未正确配置分支归属")

    return errors if errors else None


def get_parallel_path_levels(
    nodes: list[ApprovalChainNode],
    ctx: Any,
) -> list[dict] | None:
    level_map: dict[int, ApprovalChainNode] = {n.level: n for n in nodes}
    all_levels = set(level_map.keys())
    groups = parse_parallel_groups(nodes)

    path_items: list[dict] = []
    visited: set[int] = set()
    current_level = 1
    max_iterations = len(all_levels) * 3 + 20
    iterations = 0

    from app.condition_engine import resolve_next_level

    while current_level is not None and current_level in all_levels and iterations < max_iterations:
        iterations += 1
        if current_level in visited:
            logger.warning("检测到路径环路，中断: level=%s", current_level)
            break
        visited.add(current_level)

        node = level_map[current_level]

        if node.node_type == ChainNodeType.PARALLEL_START:
            group = groups.get(node.parallel_group_id or "")
            if not group:
                current_level = resolve_next_level(node, ctx, all_levels)
                continue

            path_items.append({
                "type": "parallel_start",
                "level": current_level,
                "group_id": group.group_id,
            })

            visited.add(group.end_node.level)

            for branch in group.branches:
                branch_path: list[dict] = []
                branch_visited: set[int] = set()
                branch_level = branch.get_start_level()
                branch_iter = 0

                while branch_level is not None and branch_level < group.end_node.level and branch_iter < max_iterations:
                    branch_iter += 1
                    if branch_level in branch_visited:
                        break
                    branch_visited.add(branch_level)
                    visited.add(branch_level)

                    bn = level_map.get(branch_level)
                    if not bn:
                        break

                    branch_path.append({
                        "type": "approval",
                        "level": branch_level,
                        "branch_id": branch.branch_id,
                        "branch_index": branch.branch_index,
                        "group_id": group.group_id,
                        "node": bn,
                    })

                    branch_level = resolve_next_level(bn, ctx, all_levels)
                    if branch_level is not None and branch_level >= group.end_node.level:
                        break

                path_items.append({
                    "type": "branch",
                    "branch_id": branch.branch_id,
                    "branch_index": branch.branch_index,
                    "group_id": group.group_id,
                    "nodes": branch_path,
                })

            path_items.append({
                "type": "parallel_end",
                "level": group.end_node.level,
                "group_id": group.group_id,
            })

            current_level = resolve_next_level(group.end_node, ctx, all_levels)
            continue

        path_items.append({
            "type": "approval",
            "level": current_level,
            "node": node,
        })

        current_level = resolve_next_level(node, ctx, all_levels)

    return path_items


def check_branch_all_rejected(
    records: list,
    branch_id: str,
) -> bool:
    from app.models import TransferStatus

    branch_records = [r for r in records if r.branch_id == branch_id]
    if not branch_records:
        return False

    active_records = [
        r for r in branch_records
        if not (r.transfer_status and r.transfer_status == TransferStatus.TRANSFERRED)
    ]
    if not active_records:
        return False

    all_rejected = all(r.status == ApprovalStatus.REJECTED for r in active_records)
    return all_rejected


def _nodes_to_dict(chain_nodes: list | dict) -> dict[int, ApprovalChainNode]:
    if isinstance(chain_nodes, dict):
        return chain_nodes
    return {n.level: n for n in chain_nodes}


def check_branch_complete(
    records: list,
    branch_id: str,
    chain_nodes: list[ApprovalChainNode] | dict[int, ApprovalChainNode],
) -> bool:
    from app.models import TransferStatus

    node_map = _nodes_to_dict(chain_nodes)
    branch_records = [r for r in records if r.branch_id == branch_id]
    if not branch_records:
        return False

    active_records = [
        r for r in branch_records
        if not (r.transfer_status and r.transfer_status == TransferStatus.TRANSFERRED)
    ]

    if not active_records:
        return False

    level_set = sorted(set(r.level for r in active_records))
    for level in level_set:
        level_records = [r for r in active_records if r.level == level]
        node = node_map.get(level_records[0].chain_node_level) if level_records else None
        if not node:
            return False

        if node.mode == ApprovalMode.SINGLE:
            any_approved = any(r.status == ApprovalStatus.APPROVED for r in level_records)
            any_rejected = any(r.status == ApprovalStatus.REJECTED for r in level_records)
            if not any_approved and not any_rejected:
                return False
        elif node.mode == ApprovalMode.ALL_SIGN:
            all_approved = all(
                r.status in (ApprovalStatus.APPROVED, ApprovalStatus.ESCALATED)
                for r in level_records
            )
            any_rejected = any(r.status == ApprovalStatus.REJECTED for r in level_records)
            if not all_approved and not any_rejected:
                return False
        elif node.mode == ApprovalMode.OR_SIGN:
            any_approved = any(r.status == ApprovalStatus.APPROVED for r in level_records)
            any_rejected = any(r.status == ApprovalStatus.REJECTED for r in level_records)
            if not any_approved and not any_rejected:
                return False

    return True


def check_parallel_group_ready_to_merge(
    records: list,
    group_id: str,
    chain_nodes: list[ApprovalChainNode] | dict[int, ApprovalChainNode],
) -> bool:
    groups = parse_parallel_groups(
        list(chain_nodes.values()) if isinstance(chain_nodes, dict) else chain_nodes
    )
    group = groups.get(group_id)
    if not group:
        return False

    node_map = _nodes_to_dict(chain_nodes)
    for branch in group.branches:
        if not check_branch_complete(records, branch.branch_id, node_map):
            return False
    return True


def check_any_branch_rejected(
    records: list,
    group_id: str,
    chain_nodes: list[ApprovalChainNode] | dict[int, ApprovalChainNode] | None = None,
) -> bool:
    if chain_nodes is not None:
        groups = parse_parallel_groups(
            list(chain_nodes.values()) if isinstance(chain_nodes, dict) else chain_nodes
        )
        group = groups.get(group_id)
        if not group:
            return False
        for branch in group.branches:
            if check_branch_all_rejected(records, branch.branch_id):
                return True
        return False
    else:
        branch_records = [r for r in records if r.parallel_group_id == group_id]
        branch_ids = set(r.branch_id for r in branch_records if r.branch_id)
        for bid in branch_ids:
            if check_branch_all_rejected(records, bid):
                return True
        return False


def generate_branch_id() -> str:
    return f"branch_{uuid.uuid4().hex[:8]}"


def generate_parallel_group_id() -> str:
    return f"pg_{uuid.uuid4().hex[:8]}"
