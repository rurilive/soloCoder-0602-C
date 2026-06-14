import logging
from typing import Any
from app.models import (
    ApprovalChainNode,
    ApprovalChainCondition,
    ApprovalChainConditionRule,
    ConditionOperator,
    ConditionField,
    ConditionLogic,
    AssetCategory,
)

logger = logging.getLogger(__name__)


class ConditionEvaluationContext:
    def __init__(
        self,
        price: float | None = None,
        category: AssetCategory | str | None = None,
        applicant_department: str | None = None,
    ) -> None:
        self.price = price
        self.category = category.value if isinstance(category, AssetCategory) else category
        self.applicant_department = applicant_department

    def get_field_value(self, field: ConditionField) -> Any:
        if field == ConditionField.PRICE:
            return self.price
        if field == ConditionField.CATEGORY:
            return self.category
        if field == ConditionField.APPLICANT_DEPARTMENT:
            return self.applicant_department
        return None


def _evaluate_single_rule(rule: ApprovalChainConditionRule, ctx: ConditionEvaluationContext) -> bool | None:
    try:
        field_value = ctx.get_field_value(rule.field)
        operator = rule.operator
        rule_value = rule.value

        if field_value is None and operator not in (ConditionOperator.EQ, ConditionOperator.NE):
            return None

        if operator == ConditionOperator.EQ:
            if isinstance(rule_value, list):
                return field_value in rule_value
            return field_value == rule_value

        if operator == ConditionOperator.NE:
            if isinstance(rule_value, list):
                return field_value not in rule_value
            return field_value != rule_value

        if operator == ConditionOperator.GT:
            if field_value is None or rule_value is None:
                return None
            return float(field_value) > float(rule_value)

        if operator == ConditionOperator.GTE:
            if field_value is None or rule_value is None:
                return None
            return float(field_value) >= float(rule_value)

        if operator == ConditionOperator.LT:
            if field_value is None or rule_value is None:
                return None
            return float(field_value) < float(rule_value)

        if operator == ConditionOperator.LTE:
            if field_value is None or rule_value is None:
                return None
            return float(field_value) <= float(rule_value)

        if operator == ConditionOperator.IN:
            if not isinstance(rule_value, list):
                return None
            return field_value in rule_value

        if operator == ConditionOperator.NOT_IN:
            if not isinstance(rule_value, list):
                return None
            return field_value not in rule_value

        if operator == ConditionOperator.BETWEEN:
            if not isinstance(rule_value, list) or len(rule_value) < 2:
                return None
            low, high = float(rule_value[0]), float(rule_value[1])
            return low <= float(field_value) <= high

        if operator == ConditionOperator.CONTAINS:
            if field_value is None or rule_value is None:
                return None
            return str(rule_value).lower() in str(field_value).lower()

        return None
    except Exception as e:
        logger.warning("条件规则计算异常，跳过该规则: rule_id=%s, error=%s", rule.id, e)
        return None


def _evaluate_condition(condition: ApprovalChainCondition, ctx: ConditionEvaluationContext) -> bool:
    if not condition.rules:
        return False

    results: list[bool] = []
    for rule in condition.rules:
        r = _evaluate_single_rule(rule, ctx)
        if r is not None:
            results.append(r)

    if not results:
        return False

    if condition.logic == ConditionLogic.AND:
        return all(results)
    if condition.logic == ConditionLogic.OR:
        return any(results)
    return False


def resolve_next_level(
    node: ApprovalChainNode,
    ctx: ConditionEvaluationContext,
    all_levels: set[int],
) -> int | None:
    sorted_conditions = sorted(
        node.conditions,
        key=lambda c: (c.priority, c.id),
    )

    for condition in sorted_conditions:
        if condition.target_level not in all_levels:
            logger.warning(
                "条件目标级号 %d 不存在，跳过该条件 (condition_id=%s)",
                condition.target_level, condition.id,
            )
            continue
        try:
            if _evaluate_condition(condition, ctx):
                return condition.target_level
        except Exception as e:
            logger.warning("条件解析异常，跳过该条件: condition_id=%s, error=%s", condition.id, e)
            continue

    if node.default_next_level is not None and node.default_next_level in all_levels:
        return node.default_next_level

    linear_next = node.level + 1
    if linear_next in all_levels:
        return linear_next

    return None


def detect_cycle(nodes: list[ApprovalChainNode]) -> list[int] | None:
    level_map: dict[int, ApprovalChainNode] = {n.level: n for n in nodes}
    all_levels = set(level_map.keys())

    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[int, int] = {level: WHITE for level in all_levels}
    parent: dict[int, int | None] = {level: None for level in all_levels}

    def dfs(start_level: int) -> list[int] | None:
        stack: list[tuple[int, bool]] = [(start_level, False)]
        cycle_path: list[int] = []
        while stack:
            level, processed = stack.pop()
            if processed:
                color[level] = BLACK
                if cycle_path and cycle_path[-1] == level:
                    cycle_path.pop()
                continue
            if color[level] == BLACK:
                continue
            if color[level] == GRAY:
                cycle = [level]
                cur = parent[level]
                while cur is not None and cur != level:
                    cycle.append(cur)
                    cur = parent[cur]
                cycle.append(level)
                cycle.reverse()
                return cycle
            color[level] = GRAY
            cycle_path.append(level)
            stack.append((level, True))

            node = level_map.get(level)
            if not node:
                continue

            targets: list[int] = []
            for cond in node.conditions:
                if cond.target_level in all_levels:
                    targets.append(cond.target_level)
            if node.default_next_level is not None and node.default_next_level in all_levels:
                targets.append(node.default_next_level)
            linear_next = level + 1
            if linear_next in all_levels:
                targets.append(linear_next)

            seen_targets = set()
            for t in reversed(targets):
                if t in seen_targets:
                    continue
                seen_targets.add(t)
                if color[t] == WHITE:
                    parent[t] = level
                stack.append((t, False))
        return None

    for level in sorted(all_levels):
        if color[level] == WHITE:
            cycle = dfs(level)
            if cycle:
                return cycle
    return None
