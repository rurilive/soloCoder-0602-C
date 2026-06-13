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

const EMPTY_NODE = { approver_role: '', approver_name: '' }

const EMPTY_FORM = {
  name: '',
  approval_type: 'allocate',
  min_price: '',
  max_price: '',
  is_default: false,
  nodes: [{ ...EMPTY_NODE }],
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
    setForm({ ...EMPTY_FORM, nodes: [{ ...EMPTY_NODE }] })
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
      nodes: chain.nodes.length > 0
        ? chain.nodes.map((n) => ({ approver_role: n.approver_role, approver_name: n.approver_name }))
        : [{ ...EMPTY_NODE }],
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
      return { ...prev, nodes }
    })
  }

  const addNode = () => {
    setForm((prev) => ({ ...prev, nodes: [...prev.nodes, { ...EMPTY_NODE }] }))
  }

  const removeNode = (index) => {
    setForm((prev) => ({
      ...prev,
      nodes: prev.nodes.filter((_, i) => i !== index),
    }))
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!form.name.trim()) {
      alert('请输入审批链名称')
      return
    }
    const validNodes = form.nodes.filter((n) => n.approver_role.trim() && n.approver_name.trim())
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
          <div className="modal" style={{ maxWidth: 560 }} onClick={(e) => e.stopPropagation()}>
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
                  {form.nodes.map((node, i) => (
                    <div key={i} className="chain-form-node-row">
                      <span style={{ color: 'var(--text-secondary)', fontWeight: 600, minWidth: 20 }}>
                        {i + 1}.
                      </span>
                      <div className="form-group" style={{ flex: 1 }}>
                        <input
                          type="text"
                          value={node.approver_role}
                          onChange={(e) => handleNodeChange(i, 'approver_role', e.target.value)}
                          placeholder="审批角色"
                        />
                      </div>
                      <div className="form-group" style={{ flex: 1 }}>
                        <input
                          type="text"
                          value={node.approver_name}
                          onChange={(e) => handleNodeChange(i, 'approver_name', e.target.value)}
                          placeholder="审批人"
                        />
                      </div>
                      <button
                        type="button"
                        className="btn btn-danger btn-sm"
                        onClick={() => removeNode(i)}
                        disabled={form.nodes.length <= 1}
                      >
                        删除
                      </button>
                    </div>
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

        {localNodes.length > 0 && (
          <div className="chain-nodes">
            {localNodes.map((node, i) => (
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
                <span style={{ fontWeight: 500, minWidth: 24 }}>L{node.level}</span>
                <span style={{ color: 'var(--text-secondary)' }}>{node.approver_role}</span>
                <span>— {node.approver_name}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
