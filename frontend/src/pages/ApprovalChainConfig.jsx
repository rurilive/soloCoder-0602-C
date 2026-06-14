import { useState, useEffect, useRef } from 'react'
import {
  getApprovalChains,
  createApprovalChain,
  updateApprovalChain,
  deleteApprovalChain,
  reorderChainNodes,
} from '../api/assets'

const TYPE_MAP = {
  allocate: '领用审批',
  scrap: '报废审批',
}

const MODE_MAP = {
  single: '单人通过',
  all_sign: '会签',
  or_sign: '或签',
}

const FIELD_MAP = {
  price: '资产价格',
  category: '资产类别',
  applicant_department: '申请人部门',
}

const OPERATOR_MAP = {
  eq: '等于',
  ne: '不等于',
  gt: '大于',
  gte: '大于等于',
  lt: '小于',
  lte: '小于等于',
  in: '属于',
  not_in: '不属于',
  between: '区间',
  contains: '包含',
}

const LOGIC_MAP = {
  and: '全部满足 (AND)',
  or: '任一满足 (OR)',
}

const CATEGORY_OPTIONS = [
  { value: 'computer', label: '电脑' },
  { value: 'monitor', label: '显示器' },
  { value: 'printer', label: '打印机' },
  { value: 'network_device', label: '网络设备' },
  { value: 'peripheral', label: '外设' },
  { value: 'other', label: '其他' },
]

const NEEDS_LIST_OPERATORS = new Set(['in', 'not_in'])
const NEEDS_RANGE_OPERATORS = new Set(['between'])
const NEEDS_NUMERIC_OPERATORS = new Set(['gt', 'gte', 'lt', 'lte', 'between'])
const NEEDS_TEXT_OPERATORS = new Set(['contains'])

const EMPTY_APPROVER = { approver_role: '', approver_name: '' }

const makeEmptyRule = () => ({
  field: 'price',
  operator: 'eq',
  value: null,
})

const makeEmptyCondition = (targetLevel) => ({
  target_level: targetLevel,
  logic: 'and',
  priority: 0,
  rules: [makeEmptyRule()],
})

const makeEmptyNode = () => ({
  mode: 'single',
  timeout_minutes: '',
  default_next_level: '',
  approvers: [{ ...EMPTY_APPROVER }],
  conditions: [],
})

const EMPTY_FORM = {
  name: '',
  approval_type: 'allocate',
  min_price: '',
  max_price: '',
  is_default: false,
  nodes: [makeEmptyNode()],
}

function formatRuleValue(rule) {
  if (rule.value == null || rule.value === '') return '—'
  if (rule.operator === 'between' && Array.isArray(rule.value)) {
    return `[${rule.value[0] ?? '?'}, ${rule.value[1] ?? '?'}]`
  }
  if (Array.isArray(rule.value)) {
    return rule.value.join(', ')
  }
  return String(rule.value)
}

function formatConditionSummary(cond, nodeIdx, totalNodes) {
  const target = cond.target_level
  const targetLabel = target > totalNodes ? `L${target}(不存在)` : `L${target}`
  const logic = LOGIC_MAP[cond.logic] || cond.logic
  const ruleStr = (cond.rules || [])
    .map((r) => `${FIELD_MAP[r.field] || r.field} ${OPERATOR_MAP[r.operator] || r.operator} ${formatRuleValue(r)}`)
    .join(` ${cond.logic === 'and' ? ' ∧ ' : ' ∨ '} `)
  return `${targetLabel} ← [${logic}] ${ruleStr || '(无规则)'}`
}

export default function ApprovalChainConfig() {
  const [chains, setChains] = useState([])
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [form, setForm] = useState({ ...EMPTY_FORM })
  const [saving, setSaving] = useState(false)

  const fetchChains = async () => {
    setLoading(true)
    try {
      const res = await getApprovalChains()
      setChains(res.data.items || [])
    } catch {
      alert('获取审批链列表失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchChains() }, [])

  const openCreateModal = () => {
    setEditingId(null)
    setForm({
      ...EMPTY_FORM,
      nodes: [makeEmptyNode()],
    })
    setShowModal(true)
  }

  const openEditModal = (chain) => {
    setEditingId(chain.id)
    setForm({
      name: chain.name,
      approval_type: chain.approval_type,
      min_price: chain.min_price != null ? String(chain.min_price) : '',
      max_price: chain.max_price != null ? String(chain.max_price) : '',
      is_default: chain.is_default,
      nodes: chain.nodes && chain.nodes.length > 0
        ? chain.nodes.map((n) => ({
            mode: n.mode || 'single',
            timeout_minutes: n.timeout_minutes != null ? String(n.timeout_minutes) : '',
            default_next_level: n.default_next_level != null ? String(n.default_next_level) : '',
            approvers:
              n.approvers && n.approvers.length > 0
                ? n.approvers.map((a) => ({ approver_role: a.approver_role, approver_name: a.approver_name }))
                : [{ ...EMPTY_APPROVER }],
            conditions:
              n.conditions && n.conditions.length > 0
                ? n.conditions.map((c) => ({
                    target_level: c.target_level,
                    logic: c.logic || 'and',
                    priority: c.priority ?? 0,
                    rules: (c.rules || []).map((r) => ({
                      field: r.field,
                      operator: r.operator,
                      value: r.value,
                    })),
                  }))
                : [],
          }))
        : [makeEmptyNode()],
    })
    setShowModal(true)
  }

  const closeModal = () => {
    setShowModal(false)
    setEditingId(null)
  }

  const handleFormChange = (field, value) => {
    setForm((prev) => ({ ...prev, [field]: value }))
  }

  const handleNodeChange = (index, field, value) => {
    setForm((prev) => {
      const nodes = [...prev.nodes]
      nodes[index] = { ...nodes[index], [field]: value }
      if (field === 'mode' && value === 'single' && nodes[index].approvers.length > 1) {
        nodes[index].approvers = nodes[index].approvers.slice(0, 1)
      }
      return { ...prev, nodes }
    })
  }

  const handleApproverChange = (nodeIdx, approverIdx, field, value) => {
    setForm((prev) => {
      const nodes = [...prev.nodes]
      const approvers = [...nodes[nodeIdx].approvers]
      approvers[approverIdx] = { ...approvers[approverIdx], [field]: value }
      nodes[nodeIdx] = { ...nodes[nodeIdx], approvers }
      return { ...prev, nodes }
    })
  }

  const addNode = () => {
    setForm((prev) => ({
      ...prev,
      nodes: [...prev.nodes, makeEmptyNode()],
    }))
  }

  const removeNode = (index) => {
    setForm((prev) => ({
      ...prev,
      nodes: prev.nodes.filter((_, i) => i !== index),
    }))
  }

  const addApprover = (nodeIdx) => {
    setForm((prev) => {
      const nodes = [...prev.nodes]
      if (nodes[nodeIdx].mode === 'single') return prev
      nodes[nodeIdx] = {
        ...nodes[nodeIdx],
        approvers: [...nodes[nodeIdx].approvers, { ...EMPTY_APPROVER }],
      }
      return { ...prev, nodes }
    })
  }

  const removeApprover = (nodeIdx, approverIdx) => {
    setForm((prev) => {
      const nodes = [...prev.nodes]
      if (nodes[nodeIdx].approvers.length <= 1) return prev
      nodes[nodeIdx] = {
        ...nodes[nodeIdx],
        approvers: nodes[nodeIdx].approvers.filter((_, i) => i !== approverIdx),
      }
      return { ...prev, nodes }
    })
  }

  const addCondition = (nodeIdx) => {
    setForm((prev) => {
      const nodes = [...prev.nodes]
      const defaultTarget = nodeIdx + 2
      nodes[nodeIdx] = {
        ...nodes[nodeIdx],
        conditions: [...(nodes[nodeIdx].conditions || []), makeEmptyCondition(defaultTarget)],
      }
      return { ...prev, nodes }
    })
  }

  const removeCondition = (nodeIdx, condIdx) => {
    setForm((prev) => {
      const nodes = [...prev.nodes]
      nodes[nodeIdx] = {
        ...nodes[nodeIdx],
        conditions: (nodes[nodeIdx].conditions || []).filter((_, i) => i !== condIdx),
      }
      return { ...prev, nodes }
    })
  }

  const handleConditionChange = (nodeIdx, condIdx, field, value) => {
    setForm((prev) => {
      const nodes = [...prev.nodes]
      const conditions = [...(nodes[nodeIdx].conditions || [])]
      conditions[condIdx] = { ...conditions[condIdx], [field]: value }
      nodes[nodeIdx] = { ...nodes[nodeIdx], conditions }
      return { ...prev, nodes }
    })
  }

  const addRule = (nodeIdx, condIdx) => {
    setForm((prev) => {
      const nodes = [...prev.nodes]
      const conditions = [...(nodes[nodeIdx].conditions || [])]
      const rules = [...(conditions[condIdx].rules || [])]
      const firstField = rules[0]?.field || 'price'
      rules.push({ ...makeEmptyRule(), field: firstField })
      conditions[condIdx] = { ...conditions[condIdx], rules }
      nodes[nodeIdx] = { ...nodes[nodeIdx], conditions }
      return { ...prev, nodes }
    })
  }

  const removeRule = (nodeIdx, condIdx, ruleIdx) => {
    setForm((prev) => {
      const nodes = [...prev.nodes]
      const conditions = [...(nodes[nodeIdx].conditions || [])]
      const rules = (conditions[condIdx].rules || []).filter((_, i) => i !== ruleIdx)
      conditions[condIdx] = { ...conditions[condIdx], rules }
      nodes[nodeIdx] = { ...nodes[nodeIdx], conditions }
      return { ...prev, nodes }
    })
  }

  const handleRuleChange = (nodeIdx, condIdx, ruleIdx, field, value) => {
    setForm((prev) => {
      const nodes = [...prev.nodes]
      const conditions = [...(nodes[nodeIdx].conditions || [])]
      const rules = [...(conditions[condIdx].rules || [])]
      rules[ruleIdx] = { ...rules[ruleIdx], [field]: value }
      if (field === 'field') {
        rules[ruleIdx].value = null
      }
      if (field === 'operator') {
        if (NEEDS_LIST_OPERATORS.has(value)) {
          rules[ruleIdx].value = []
        } else if (NEEDS_RANGE_OPERATORS.has(value)) {
          rules[ruleIdx].value = ['', '']
        } else {
          rules[ruleIdx].value = ''
        }
      }
      conditions[condIdx] = { ...conditions[condIdx], rules }
      nodes[nodeIdx] = { ...nodes[nodeIdx], conditions }
      return { ...prev, nodes }
    })
  }

  const handleRuleValueChange = (nodeIdx, condIdx, ruleIdx, value, subIdx) => {
    setForm((prev) => {
      const nodes = [...prev.nodes]
      const conditions = [...(nodes[nodeIdx].conditions || [])]
      const rules = [...(conditions[condIdx].rules || [])]
      const rule = { ...rules[ruleIdx] }
      if (NEEDS_RANGE_OPERATORS.has(rule.operator)) {
        const arr = Array.isArray(rule.value) ? [...rule.value] : ['', '']
        arr[subIdx] = value
        rule.value = arr
      } else if (NEEDS_LIST_OPERATORS.has(rule.operator)) {
        rule.value = value
      } else {
        rule.value = value
      }
      rules[ruleIdx] = rule
      conditions[condIdx] = { ...conditions[condIdx], rules }
      nodes[nodeIdx] = { ...nodes[nodeIdx], conditions }
      return { ...prev, nodes }
    })
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!form.name.trim()) {
      alert('请输入审批链名称')
      return
    }
    const totalNodes = form.nodes.length
    const validNodes = []
    for (let nodeIdx = 0; nodeIdx < form.nodes.length; nodeIdx++) {
      const node = form.nodes[nodeIdx]
      const validApprovers = node.approvers.filter(
        (a) => a.approver_role.trim() && a.approver_name.trim()
      )
      if (validApprovers.length === 0) {
        alert(`请为第${nodeIdx + 1}级节点至少配置一个审批人`)
        return
      }
      if (node.mode === 'single' && validApprovers.length > 1) {
        alert(`单人通过模式（第${nodeIdx + 1}级）只能有一个审批人`)
        return
      }

      const validConditions = []
      for (const cond of (node.conditions || [])) {
        const target = Number(cond.target_level)
        if (!target || target < 1 || target > totalNodes) {
          alert(`第${nodeIdx + 1}级节点的条件目标级号必须在 1 ~ ${totalNodes} 之间`)
          return
        }
        const validRules = []
        for (const rule of (cond.rules || [])) {
          if (!rule.field || !rule.operator) continue
          let val = rule.value
          if (NEEDS_NUMERIC_OPERATORS.has(rule.operator)) {
            if (NEEDS_RANGE_OPERATORS.has(rule.operator)) {
              if (!Array.isArray(val) || val.length < 2) continue
              const parsed = [Number(val[0]), Number(val[1])]
              if (isNaN(parsed[0]) || isNaN(parsed[1])) continue
              val = parsed
            } else {
              const parsed = Number(val)
              if (isNaN(parsed)) continue
              val = parsed
            }
          } else if (NEEDS_LIST_OPERATORS.has(rule.operator)) {
            if (!Array.isArray(val) || val.length === 0) continue
          } else if (val === '' || val == null) {
            continue
          }
          validRules.push({ field: rule.field, operator: rule.operator, value: val })
        }
        validConditions.push({
          target_level: target,
          logic: cond.logic || 'and',
          priority: Number(cond.priority) || 0,
          rules: validRules,
        })
      }

      let defaultNextLevel = null
      if (node.default_next_level !== '' && node.default_next_level != null) {
        const dn = Number(node.default_next_level)
        if (!isNaN(dn) && dn >= 1 && dn <= totalNodes) {
          defaultNextLevel = dn
        }
      }

      validNodes.push({
        mode: node.mode,
        timeout_minutes: node.timeout_minutes !== '' ? parseInt(node.timeout_minutes, 10) : null,
        default_next_level: defaultNextLevel,
        approvers: validApprovers,
        conditions: validConditions,
      })
    }
    if (validNodes.length === 0) {
      alert('请至少添加一个审批节点')
      return
    }

    const payload = {
      name: form.name.trim(),
      approval_type: form.approval_type,
      min_price: form.min_price !== '' ? parseFloat(form.min_price) : null,
      max_price: form.max_price !== '' ? parseFloat(form.max_price) : null,
      is_default: form.is_default,
      nodes: validNodes,
    }

    setSaving(true)
    try {
      if (editingId) {
        await updateApprovalChain(editingId, payload)
        alert('审批链更新成功')
      } else {
        await createApprovalChain(payload)
        alert('审批链创建成功')
      }
      closeModal()
      fetchChains()
    } catch (err) {
      alert(err.response?.data?.detail || '操作失败')
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (chain) => {
    if (!confirm(`确定删除审批链「${chain.name}」？此操作不可恢复。`)) return
    try {
      await deleteApprovalChain(chain.id)
      alert('删除成功')
      fetchChains()
    } catch (err) {
      alert(err.response?.data?.detail || '删除失败')
    }
  }

  return (
    <div>
      <div className="toolbar">
        <h2 style={{ fontSize: 18, fontWeight: 600 }}>审批链配置</h2>
        <div style={{ flex: 1 }} />
        <button className="btn btn-primary" onClick={openCreateModal}>
          + 新建审批链
        </button>
      </div>

      {loading ? (
        <div className="empty-state"><p>加载中...</p></div>
      ) : chains.length === 0 ? (
        <div className="empty-state">
          <p>暂无审批链配置</p>
          <button className="btn btn-primary" onClick={openCreateModal}>新建审批链</button>
        </div>
      ) : (
        <div className="chain-list">
          {chains.map((chain) => (
            <ChainCard
              key={chain.id}
              chain={chain}
              onEdit={openEditModal}
              onDelete={handleDelete}
              onReorder={fetchChains}
            />
          ))}
        </div>
      )}

      {showModal && (
        <div className="modal-overlay" onClick={closeModal}>
          <div className="modal" style={{ maxWidth: 880 }} onClick={(e) => e.stopPropagation()}>
            <h3>{editingId ? '编辑审批链' : '新建审批链'}</h3>
            <form onSubmit={handleSubmit}>
              <div className="form-grid" style={{ marginBottom: 16 }}>
                <div className="form-group">
                  <label>审批链名称</label>
                  <input
                    type="text"
                    value={form.name}
                    onChange={(e) => handleFormChange('name', e.target.value)}
                    placeholder="请输入审批链名称"
                  />
                </div>
                <div className="form-group">
                  <label>审批类型</label>
                  <select
                    value={form.approval_type}
                    onChange={(e) => handleFormChange('approval_type', e.target.value)}
                    disabled={!!editingId}
                  >
                    {Object.entries(TYPE_MAP).map(([k, v]) => (
                      <option key={k} value={k}>{v}</option>
                    ))}
                  </select>
                </div>
                <div className="form-group">
                  <label>最低价格（元）</label>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    value={form.min_price}
                    onChange={(e) => handleFormChange('min_price', e.target.value)}
                    placeholder="不限"
                  />
                </div>
                <div className="form-group">
                  <label>最高价格（元）</label>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    value={form.max_price}
                    onChange={(e) => handleFormChange('max_price', e.target.value)}
                    placeholder="不限"
                  />
                </div>
              </div>

              <div className="form-group" style={{ marginBottom: 16 }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={form.is_default}
                    onChange={(e) => handleFormChange('is_default', e.target.checked)}
                  />
                  设为默认审批链
                </label>
              </div>

              <div style={{ marginBottom: 16 }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                  <label style={{ fontSize: 14, fontWeight: 500, color: 'var(--text-secondary)' }}>
                    审批节点
                  </label>
                  <button type="button" className="btn btn-outline btn-sm" onClick={addNode}>
                    + 添加节点
                  </button>
                </div>
                <div className="chain-form-nodes">
                  {form.nodes.map((node, nodeIdx) => (
                    <NodeEditor
                      key={nodeIdx}
                      node={node}
                      nodeIdx={nodeIdx}
                      totalNodes={form.nodes.length}
                      onNodeChange={handleNodeChange}
                      onApproverChange={handleApproverChange}
                      onAddApprover={addApprover}
                      onRemoveApprover={removeApprover}
                      onRemoveNode={removeNode}
                      onAddCondition={addCondition}
                      onRemoveCondition={removeCondition}
                      onConditionChange={handleConditionChange}
                      onAddRule={addRule}
                      onRemoveRule={removeRule}
                      onRuleChange={handleRuleChange}
                      onRuleValueChange={handleRuleValueChange}
                    />
                  ))}
                </div>
              </div>

              <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end' }}>
                <button type="button" className="btn btn-outline" onClick={closeModal}>取消</button>
                <button type="submit" className="btn btn-primary" disabled={saving}>
                  {saving ? '保存中...' : '保存'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}

function NodeEditor(props) {
  const {
    node, nodeIdx, totalNodes,
    onNodeChange, onApproverChange, onAddApprover, onRemoveApprover, onRemoveNode,
    onAddCondition, onRemoveCondition, onConditionChange,
    onAddRule, onRemoveRule, onRuleChange, onRuleValueChange,
  } = props
  const [showConditions, setShowConditions] = useState(true)
  const levelNum = nodeIdx + 1

  return (
    <div className="chain-form-node-block">
      <div className="chain-form-node-header">
        <span style={{ color: 'var(--text-secondary)', fontWeight: 600 }}>
          第 {levelNum} 级
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <div className="form-group" style={{ marginBottom: 0, minWidth: 140 }}>
            <select
              value={node.mode}
              onChange={(e) => onNodeChange(nodeIdx, 'mode', e.target.value)}
            >
              {Object.entries(MODE_MAP).map(([k, v]) => (
                <option key={k} value={k}>{v}</option>
              ))}
            </select>
          </div>
          <div className="form-group" style={{ marginBottom: 0, minWidth: 110 }}>
            <input
              type="number"
              min="1"
              placeholder="超时(min)"
              value={node.timeout_minutes}
              onChange={(e) => onNodeChange(nodeIdx, 'timeout_minutes', e.target.value)}
            />
          </div>
          <div className="form-group" style={{ marginBottom: 0, minWidth: 140 }}>
            <select
              value={node.default_next_level}
              onChange={(e) => onNodeChange(nodeIdx, 'default_next_level', e.target.value)}
            >
              <option value="">默认下一级（线性）</option>
              {Array.from({ length: totalNodes }, (_, i) => i + 1).map((lv) => (
                <option key={lv} value={String(lv)}>跳转到 L{lv}</option>
              ))}
            </select>
          </div>
          <button
            type="button"
            className="btn btn-outline btn-sm"
            onClick={() => setShowConditions((s) => !s)}
          >
            {showConditions ? '收起条件' : `展开条件 (${(node.conditions || []).length})`}
          </button>
          <button
            type="button"
            className="btn btn-danger btn-sm"
            onClick={() => onRemoveNode(nodeIdx)}
            disabled={totalNodes <= 1}
          >
            删除节点
          </button>
        </div>
      </div>

      <div className="chain-form-approvers">
        {node.approvers.map((approver, approverIdx) => (
          <div key={approverIdx} className="chain-form-approver-row">
            <span style={{ color: 'var(--text-secondary)', minWidth: 28, fontSize: 12 }}>
              {node.mode !== 'single' ? `#${approverIdx + 1}` : ''}
            </span>
            <div className="form-group" style={{ flex: 1, marginBottom: 0 }}>
              <input
                type="text"
                value={approver.approver_role}
                onChange={(e) => onApproverChange(nodeIdx, approverIdx, 'approver_role', e.target.value)}
                placeholder="审批角色"
              />
            </div>
            <div className="form-group" style={{ flex: 1, marginBottom: 0 }}>
              <input
                type="text"
                value={approver.approver_name}
                onChange={(e) => onApproverChange(nodeIdx, approverIdx, 'approver_name', e.target.value)}
                placeholder="审批人"
              />
            </div>
            {node.mode !== 'single' && (
              <button
                type="button"
                className="btn btn-outline btn-sm"
                onClick={() => onRemoveApprover(nodeIdx, approverIdx)}
                disabled={node.approvers.length <= 1}
              >
                移除
              </button>
            )}
          </div>
        ))}
        {node.mode !== 'single' && (
          <div style={{ padding: '4px 0 4px 28px' }}>
            <button
              type="button"
              className="btn btn-outline btn-sm"
              onClick={() => onAddApprover(nodeIdx)}
            >
              + 添加审批人
            </button>
          </div>
        )}
      </div>

      {showConditions && (
        <div className="chain-form-conditions" style={{ padding: '12px 16px', background: 'var(--bg-secondary)', borderRadius: 6, marginTop: 8 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
            <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-secondary)' }}>
              条件分支（按优先级匹配，命中后跳转到目标级）
            </span>
            <button
              type="button"
              className="btn btn-outline btn-sm"
              onClick={() => onAddCondition(nodeIdx)}
            >
              + 添加条件分支
            </button>
          </div>
          {(node.conditions || []).length === 0 ? (
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', padding: '8px 0' }}>
              未配置条件分支，将使用默认下一级路径
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {(node.conditions || []).map((cond, condIdx) => (
                <ConditionEditor
                  key={condIdx}
                  cond={cond}
                  nodeIdx={nodeIdx}
                  condIdx={condIdx}
                  totalNodes={totalNodes}
                  onConditionChange={onConditionChange}
                  onAddRule={onAddRule}
                  onRemoveRule={onRemoveRule}
                  onRuleChange={onRuleChange}
                  onRuleValueChange={onRuleValueChange}
                  onRemove={onRemoveCondition}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function ConditionEditor(props) {
  const {
    cond, nodeIdx, condIdx, totalNodes,
    onConditionChange, onAddRule, onRemoveRule, onRuleChange, onRuleValueChange, onRemove,
  } = props

  return (
    <div style={{ background: 'var(--bg-primary)', border: '1px solid var(--border)', borderRadius: 6, padding: 10 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 8 }}>
        <span className="status-badge status-pending" style={{ fontSize: 11 }}>
          #{condIdx + 1}
        </span>
        <div className="form-group" style={{ marginBottom: 0, minWidth: 140 }}>
          <label style={{ fontSize: 11, color: 'var(--text-secondary)', display: 'block', marginBottom: 2 }}>
            跳转到级号
          </label>
          <select
            value={String(cond.target_level)}
            onChange={(e) => onConditionChange(nodeIdx, condIdx, 'target_level', Number(e.target.value))}
          >
            {Array.from({ length: totalNodes }, (_, i) => i + 1).map((lv) => (
              <option key={lv} value={String(lv)}>L{lv}</option>
            ))}
          </select>
        </div>
        <div className="form-group" style={{ marginBottom: 0, minWidth: 160 }}>
          <label style={{ fontSize: 11, color: 'var(--text-secondary)', display: 'block', marginBottom: 2 }}>
            规则组合逻辑
          </label>
          <select
            value={cond.logic}
            onChange={(e) => onConditionChange(nodeIdx, condIdx, 'logic', e.target.value)}
          >
            {Object.entries(LOGIC_MAP).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
        </div>
        <div className="form-group" style={{ marginBottom: 0, minWidth: 90 }}>
          <label style={{ fontSize: 11, color: 'var(--text-secondary)', display: 'block', marginBottom: 2 }}>
            优先级
          </label>
          <input
            type="number"
            value={cond.priority ?? 0}
            onChange={(e) => onConditionChange(nodeIdx, condIdx, 'priority', e.target.value)}
          />
        </div>
        <div style={{ flex: 1 }} />
        <button
          type="button"
          className="btn btn-outline btn-sm"
          onClick={() => onAddRule(nodeIdx, condIdx)}
        >
          + 规则
        </button>
        <button
          type="button"
          className="btn btn-danger btn-sm"
          onClick={() => onRemove(nodeIdx, condIdx)}
        >
          删除
        </button>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {(cond.rules || []).map((rule, ruleIdx) => (
          <RuleEditor
            key={ruleIdx}
            rule={rule}
            nodeIdx={nodeIdx}
            condIdx={condIdx}
            ruleIdx={ruleIdx}
            onRuleChange={onRuleChange}
            onRuleValueChange={onRuleValueChange}
            onRemove={() => onRemoveRule(nodeIdx, condIdx, ruleIdx)}
            canRemove={(cond.rules || []).length > 1}
          />
        ))}
      </div>
    </div>
  )
}

function RuleEditor(props) {
  const { rule, nodeIdx, condIdx, ruleIdx, onRuleChange, onRuleValueChange, onRemove, canRemove } = props
  const isNumericField = rule.field === 'price'
  const isCategoryField = rule.field === 'category'
  const needsList = NEEDS_LIST_OPERATORS.has(rule.operator)
  const needsRange = NEEDS_RANGE_OPERATORS.has(rule.operator)
  const needsNumeric = NEEDS_NUMERIC_OPERATORS.has(rule.operator) && !needsList

  const availableOperators = [
    { value: 'eq', label: OPERATOR_MAP.eq },
    { value: 'ne', label: OPERATOR_MAP.ne },
    ...(isNumericField ? [
      { value: 'gt', label: OPERATOR_MAP.gt },
      { value: 'gte', label: OPERATOR_MAP.gte },
      { value: 'lt', label: OPERATOR_MAP.lt },
      { value: 'lte', label: OPERATOR_MAP.lte },
      { value: 'between', label: OPERATOR_MAP.between },
      { value: 'in', label: OPERATOR_MAP.in },
      { value: 'not_in', label: OPERATOR_MAP.not_in },
    ] : []),
    ...(!isNumericField ? [
      { value: 'contains', label: OPERATOR_MAP.contains },
      { value: 'in', label: OPERATOR_MAP.in },
      { value: 'not_in', label: OPERATOR_MAP.not_in },
    ] : []),
  ]

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
      <div className="form-group" style={{ marginBottom: 0, minWidth: 140 }}>
        <select
          value={rule.field}
          onChange={(e) => onRuleChange(nodeIdx, condIdx, ruleIdx, 'field', e.target.value)}
        >
          {Object.entries(FIELD_MAP).map(([k, v]) => (
            <option key={k} value={k}>{v}</option>
          ))}
        </select>
      </div>
      <div className="form-group" style={{ marginBottom: 0, minWidth: 120 }}>
        <select
          value={rule.operator}
          onChange={(e) => onRuleChange(nodeIdx, condIdx, ruleIdx, 'operator', e.target.value)}
        >
          {availableOperators.map((op) => (
            <option key={op.value} value={op.value}>{op.label}</option>
          ))}
        </select>
      </div>
      {needsRange ? (
        <>
          <div className="form-group" style={{ marginBottom: 0, minWidth: 110 }}>
            <input
              type={needsNumeric ? 'number' : 'text'}
              step={needsNumeric ? '0.01' : undefined}
              placeholder="最小值"
              value={Array.isArray(rule.value) ? (rule.value[0] ?? '') : ''}
              onChange={(e) => onRuleValueChange(nodeIdx, condIdx, ruleIdx, e.target.value, 0)}
            />
          </div>
          <span style={{ color: 'var(--text-secondary)' }}>~</span>
          <div className="form-group" style={{ marginBottom: 0, minWidth: 110 }}>
            <input
              type={needsNumeric ? 'number' : 'text'}
              step={needsNumeric ? '0.01' : undefined}
              placeholder="最大值"
              value={Array.isArray(rule.value) ? (rule.value[1] ?? '') : ''}
              onChange={(e) => onRuleValueChange(nodeIdx, condIdx, ruleIdx, e.target.value, 1)}
            />
          </div>
        </>
      ) : needsList && isCategoryField ? (
        <div className="form-group" style={{ marginBottom: 0, minWidth: 200 }}>
          <select
            multiple
            style={{ minHeight: 60 }}
            value={Array.isArray(rule.value) ? rule.value.map(String) : []}
            onChange={(e) => {
              const selected = Array.from(e.target.selectedOptions, (opt) => opt.value)
              onRuleValueChange(nodeIdx, condIdx, ruleIdx, selected)
            }}
          >
            {CATEGORY_OPTIONS.map((c) => (
              <option key={c.value} value={c.value}>{c.label}</option>
            ))}
          </select>
        </div>
      ) : needsList ? (
        <div className="form-group" style={{ marginBottom: 0, minWidth: 200 }}>
          <input
            type="text"
            placeholder="多个值用英文逗号分隔"
            value={Array.isArray(rule.value) ? rule.value.join(',') : ''}
            onChange={(e) => {
              const arr = e.target.value.split(',').map((s) => s.trim()).filter(Boolean)
              onRuleValueChange(nodeIdx, condIdx, ruleIdx, arr)
            }}
          />
        </div>
      ) : isCategoryField ? (
        <div className="form-group" style={{ marginBottom: 0, minWidth: 160 }}>
          <select
            value={rule.value ?? ''}
            onChange={(e) => onRuleValueChange(nodeIdx, condIdx, ruleIdx, e.target.value || null)}
          >
            <option value="">请选择</option>
            {CATEGORY_OPTIONS.map((c) => (
              <option key={c.value} value={c.value}>{c.label}</option>
            ))}
          </select>
        </div>
      ) : (
        <div className="form-group" style={{ marginBottom: 0, minWidth: 160 }}>
          <input
            type={needsNumeric ? 'number' : 'text'}
            step={needsNumeric ? '0.01' : undefined}
            placeholder="请输入值"
            value={rule.value ?? ''}
            onChange={(e) => onRuleValueChange(nodeIdx, condIdx, ruleIdx, e.target.value)}
          />
        </div>
      )}
      <button
        type="button"
        className="btn btn-outline btn-sm"
        onClick={onRemove}
        disabled={!canRemove}
      >
        移除
      </button>
    </div>
  )
}

function ChainCard({ chain, onEdit, onDelete, onReorder }) {
  const dragItem = useRef(null)
  const dragOverItem = useRef(null)
  const [localNodes, setLocalNodes] = useState(chain.nodes)
  const [draggingIdx, setDraggingIdx] = useState(null)
  const [dropTargetIdx, setDropTargetIdx] = useState(null)

  useEffect(() => {
    setLocalNodes(chain.nodes)
  }, [chain.nodes])

  const handleDragStart = (e, index) => {
    dragItem.current = index
    setDraggingIdx(index)
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', String(index))
  }

  const handleDragEnter = (e, index) => {
    e.preventDefault()
    dragOverItem.current = index
    setDropTargetIdx(index)
  }

  const handleDragOver = (e) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
  }

  const handleDragLeave = () => {
    setDropTargetIdx(null)
  }

  const handleDrop = async (e, dropIndex) => {
    e.preventDefault()
    const dragIndex = dragItem.current
    setDraggingIdx(null)
    setDropTargetIdx(null)

    if (dragIndex === null || dragIndex === dropIndex) return

    const reordered = [...localNodes]
    const [moved] = reordered.splice(dragIndex, 1)
    reordered.splice(dropIndex, 0, moved)
    setLocalNodes(reordered)

    try {
      await reorderChainNodes(chain.id, reordered.map((n) => n.id))
      onReorder()
    } catch {
      alert('排序更新失败，已恢复原顺序')
      setLocalNodes(chain.nodes)
    }
  }

  const handleDragEnd = () => {
    setDraggingIdx(null)
    setDropTargetIdx(null)
    dragItem.current = null
    dragOverItem.current = null
  }

  const priceLabel = () => {
    const min = chain.min_price != null ? `¥${chain.min_price.toLocaleString()}` : null
    const max = chain.max_price != null ? `¥${chain.max_price.toLocaleString()}` : null
    if (!min && !max) return '不限价格'
    if (min && max) return `${min} ~ ${max}`
    if (min) return `${min} 以上`
    return `${max} 以下`
  }

  return (
    <div className="card chain-card">
      <div className="chain-card-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <strong style={{ fontSize: 16 }}>{chain.name}</strong>
          <span className={`status-badge status-${chain.approval_type === 'allocate' ? 'allocated' : 'scrapped'}`}>
            {TYPE_MAP[chain.approval_type]}
          </span>
          {chain.is_default && (
            <span className="status-badge status-approved">默认</span>
          )}
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          <button className="btn btn-outline btn-sm" onClick={() => onEdit(chain)}>编辑</button>
          <button className="btn btn-danger btn-sm" onClick={() => onDelete(chain)}>删除</button>
        </div>
      </div>

      <div className="chain-card-body">
        <div style={{ display: 'flex', gap: 24, fontSize: 14, color: 'var(--text-secondary)', marginBottom: 12 }}>
          <span>价格范围：{priceLabel()}</span>
          <span>审批节点：{localNodes.length} 个</span>
        </div>

        {localNodes && localNodes.length > 0 && (
          <div className="chain-nodes">
            {localNodes.map((node, i) => {
              const approvers = node.approvers && node.approvers.length > 0
                ? node.approvers
                : [{ approver_role: node.approver_role, approver_name: node.approver_name }]
              const modeLabel = MODE_MAP[node.mode] || '单人通过'
              const isSingle = !node.mode || node.mode === 'single'
              const hasConditions = node.conditions && node.conditions.length > 0
              return (
                <div
                  key={node.id}
                  className={[
                    'chain-node-item',
                    draggingIdx === i ? 'chain-node-dragging' : '',
                    dropTargetIdx === i ? 'chain-node-drop-target' : '',
                  ].filter(Boolean).join(' ')}
                  draggable
                  onDragStart={(e) => handleDragStart(e, i)}
                  onDragEnter={(e) => handleDragEnter(e, i)}
                  onDragOver={handleDragOver}
                  onDragLeave={handleDragLeave}
                  onDrop={(e) => handleDrop(e, i)}
                  onDragEnd={handleDragEnd}
                >
                  <span className="chain-node-drag-handle" title="拖拽排序">≡</span>
                  <div style={{ flex: 1 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: isSingle ? 4 : 6, flexWrap: 'wrap' }}>
                      <span style={{ fontWeight: 600, minWidth: 28 }}>L{node.level}</span>
                      {!isSingle && (
                        <span className="status-badge status-pending" style={{ fontSize: 11 }}>
                          {modeLabel}
                        </span>
                      )}
                      <span style={{ color: 'var(--text-secondary)' }}>
                        {isSingle && approvers[0]?.approver_role
                          ? `${approvers[0].approver_role} — ${approvers[0].approver_name}`
                          : ''}
                      </span>
                      {node.default_next_level && (
                        <span className="status-badge" style={{ fontSize: 11, background: 'var(--bg-secondary)' }}>
                          默认→L{node.default_next_level}
                        </span>
                      )}
                      {hasConditions && (
                        <span className="status-badge status-approved" style={{ fontSize: 11 }}>
                          {node.conditions.length} 个条件分支
                        </span>
                      )}
                    </div>
                    {!isSingle && approvers.length > 0 && (
                      <div className="chain-node-approvers">
                        {approvers.map((a, idx) => (
                          <div key={idx} className="chain-node-approver-item">
                            <span style={{ color: 'var(--text-secondary)', marginRight: 4 }}>#{idx + 1}</span>
                            <span style={{ color: 'var(--text-secondary)' }}>{a.approver_role || '-'}</span>
                            <span>— {a.approver_name || '-'}</span>
                          </div>
                        ))}
                      </div>
                    )}
                    {hasConditions && (
                      <div style={{ marginTop: 6, padding: 8, background: 'var(--bg-secondary)', borderRadius: 4, fontSize: 12 }}>
                        <div style={{ fontWeight: 500, color: 'var(--text-secondary)', marginBottom: 4 }}>条件分支：</div>
                        {node.conditions
                          .slice()
                          .sort((a, b) => (a.priority ?? 0) - (b.priority ?? 0))
                          .map((c, ci) => (
                            <div key={ci} style={{ color: 'var(--text-primary)' }}>
                              • {formatConditionSummary(c, i, localNodes.length)}
                            </div>
                          ))}
                      </div>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
