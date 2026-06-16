import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getApproval, approveApproval, rejectApproval, addSigner, transferApproval, getAvailableApprovalUsers } from '../api/assets'

const STATUS_MAP = {
  pending: '待审批',
  approved: '已通过',
  rejected: '已驳回',
  withdrawn: '已撤回',
  escalated: '已升级',
  transferred: '已转审',
}

const TYPE_MAP = {
  allocate: '领用审批',
  scrap: '报废审批',
}

const EVENT_ICON_MAP = {
  submit: '📝',
  approve: '✅',
  reject: '❌',
  add_signer: '➕',
  transfer: '🔄',
  remind: '⏰',
  complete: '🎉',
  withdraw: '↩️',
  escalate: '⬆️',
}

function formatTime(t) {
  if (!t) return '-'
  return new Date(t).toLocaleString('zh-CN')
}

function getLevelState(levelRecords, approval) {
  const hasRejected = levelRecords.some((r) => r.status === 'rejected')
  if (hasRejected) return 'rejected'
  const allApproved = levelRecords.length > 0 && levelRecords.every((r) => {
    if (r.transfer_status === 'transferred') return true
    return r.status === 'approved'
  })
  if (allApproved) return 'approved'
  const isCurrentLevel = levelRecords[0]?.level === approval.current_level
  if (approval.status === 'pending' && isCurrentLevel) return 'current'
  return 'pending'
}

function getApproverState(record) {
  if (record.transfer_status === 'transferred') return 'transferred'
  if (record.status === 'approved') return 'approved'
  if (record.status === 'rejected') return 'rejected'
  if (record.status === 'escalated') return 'current'
  if (record.status === 'withdrawn') return 'rejected'
  return 'pending'
}

function NodeIcon({ state }) {
  if (state === 'approved') {
    return (
      <span className="chain-node-icon chain-node-approved" style={{ color: 'var(--success)' }}>
        ✓
      </span>
    )
  }
  if (state === 'rejected') {
    return (
      <span className="chain-node-icon chain-node-rejected" style={{ color: 'var(--danger)' }}>
        ✗
      </span>
    )
  }
  if (state === 'current') {
    return (
      <span className="chain-node-icon chain-node-current" style={{ color: 'var(--primary)' }}>
        ●
      </span>
    )
  }
  if (state === 'transferred') {
    return (
      <span className="chain-node-icon chain-node-pending" style={{ color: 'var(--warning)' }}>
        🔄
      </span>
    )
  }
  return (
    <span className="chain-node-icon chain-node-pending" style={{ color: 'var(--border)' }}>
      ○
    </span>
  )
}

function getApproverBadgeColor(state) {
  if (state === 'approved') return 'var(--success)'
  if (state === 'rejected') return 'var(--danger)'
  if (state === 'current') return 'var(--primary)'
  if (state === 'transferred') return 'var(--warning)'
  return 'var(--border)'
}

function ChainTimeline({ approval, onAddSigner, onTransfer, currentUser }) {
  const nodes = approval.node_records || []
  const hasChain = nodes.length > 0

  if (!hasChain) {
    return (
      <div className="card">
        <h3 style={{ marginBottom: 16 }}>审批状态</h3>
        <div className="approval-chain-timeline">
          <div className={`approval-chain-node chain-node-${approval.status}`}>
            <NodeIcon state={approval.status === 'pending' ? 'current' : approval.status} />
            <div className="chain-node-content">
              <div className="chain-node-title">
                审批人: {approval.approver || '-'}
              </div>
              <div className="chain-node-meta">
                <span className={`status-badge status-${approval.status}`}>
                  {STATUS_MAP[approval.status]}
                </span>
              </div>
              {approval.approval_opinion && (
                <div className="chain-node-opinion">意见: {approval.approval_opinion}</div>
              )}
            </div>
          </div>
        </div>
      </div>
    )
  }

  const levelGroups = {}
  for (const node of nodes) {
    if (!levelGroups[node.level]) levelGroups[node.level] = []
    levelGroups[node.level].push(node)
  }
  const levels = Object.keys(levelGroups)
    .map(Number)
    .sort((a, b) => a - b)

  const getChainNodeLevel = (level) => {
    const recs = levelGroups[level]
    if (!recs || recs.length === 0) return 0
    return recs[0].chain_node_level || 0
  }

  const hasConditionalJump = (levelIdx) => {
    if (levelIdx === 0) return false
    const prevLevel = levels[levelIdx - 1]
    const currLevel = levels[levelIdx]
    const prevChainLevel = getChainNodeLevel(prevLevel)
    const currChainLevel = getChainNodeLevel(currLevel)
    if (prevChainLevel === 0 || currChainLevel === 0) return false
    return currChainLevel !== prevChainLevel + 1
  }

  const isCountersignPartialApproved = (records, level) => {
    if (approval.status !== 'pending' || level !== approval.current_level) return false
    const activeRecords = records.filter((r) => r.transfer_status !== 'transferred')
    const hasApproved = activeRecords.some((r) => r.status === 'approved')
    const hasPending = activeRecords.some((r) => r.status === 'pending')
    return hasApproved && hasPending
  }

  return (
    <div className="card">
      <h3 style={{ marginBottom: 16 }}>
        审批流程
        <span style={{ fontSize: 13, fontWeight: 400, color: 'var(--text-secondary)', marginLeft: 8 }}>
          共 {approval.total_levels} 级审批
        </span>
      </h3>
      <div className="approval-chain-timeline">
        {levels.map((level, levelIdx) => {
          const records = levelGroups[level]
          const state = getLevelState(records, approval)
          const isMulti = records.length > 1
          const role = records[0]?.approver_role
          const chainNodeLevel = getChainNodeLevel(level)
          const isJump = hasConditionalJump(levelIdx)
          const prevChainLevel = levelIdx > 0 ? getChainNodeLevel(levels[levelIdx - 1]) : 0
          const partialApproved = isCountersignPartialApproved(records, level)
          const canAddSigner = partialApproved && (
            approval.applicant === currentUser?.real_name ||
            approval.applicant === currentUser?.username ||
            currentUser?.roles?.includes('super_admin') ||
            currentUser?.roles?.includes('asset_admin')
          )
          return (
            <div key={level} className={`approval-chain-node chain-node-${state}`}>
              {isJump && (
                <div
                  className="chain-jump-indicator"
                  style={{
                    position: 'absolute',
                    left: 14,
                    top: -2,
                    transform: 'translateY(-100%)',
                    fontSize: 11,
                    color: 'var(--warning)',
                    fontWeight: 500,
                    background: 'rgba(255, 193, 7, 0.12)',
                    padding: '3px 10px',
                    borderRadius: 4,
                    whiteSpace: 'nowrap',
                  }}
                >
                  ↷ 条件跳转：L{prevChainLevel} → L{chainNodeLevel}
                </div>
              )}
              {levelIdx < levels.length - 1 && <div className="chain-connector" />}
              <NodeIcon state={state} />
              <div className="chain-node-content">
                <div className="chain-node-title" style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 6 }}>
                  <span>第 {level} 级 - {role}</span>
                  {chainNodeLevel > 0 && chainNodeLevel !== level && (
                    <span
                      className="status-badge"
                      style={{
                        fontSize: 11,
                        background: 'var(--bg-secondary)',
                        color: 'var(--text-secondary)',
                      }}
                    >
                      原节点 L{chainNodeLevel}
                    </span>
                  )}
                  {isMulti && (
                    <span className="status-badge status-pending" style={{ fontSize: 11 }}>
                      {records.length} 人并行
                    </span>
                  )}
                  {partialApproved && (
                    <span
                      className="status-badge"
                      style={{
                        fontSize: 11,
                        background: 'rgba(255, 193, 7, 0.15)',
                        color: 'var(--warning)',
                      }}
                    >
                      部分通过
                    </span>
                  )}
                  {canAddSigner && (
                    <button
                      className="btn btn-sm btn-outline"
                      style={{
                        marginLeft: 8,
                        fontSize: 12,
                        padding: '2px 10px',
                        borderColor: 'var(--primary)',
                        color: 'var(--primary)',
                      }}
                      onClick={() => onAddSigner && onAddSigner(level, records)}
                    >
                      ➕ 加签
                    </button>
                  )}
                </div>
                <div className="chain-level-approvers">
                  {records.map((rec) => {
                    const approverState = getApproverState(rec)
                    const isCurrentUserApprover =
                      (rec.approver_name === currentUser?.real_name ||
                       rec.approver_name === currentUser?.username) &&
                      rec.status === 'pending' &&
                      rec.transfer_status !== 'transferred'
                    return (
                      <div
                        key={rec.id}
                        className={`chain-approver-row chain-approver-${approverState}`}
                        style={{
                          border: isCurrentUserApprover ? '1px solid var(--primary)' : 'none',
                          borderRadius: 6,
                          padding: isCurrentUserApprover ? 6 : 0,
                          background: isCurrentUserApprover ? 'rgba(13, 110, 253, 0.05)' : 'transparent',
                        }}
                      >
                        <span
                          className="chain-approver-icon"
                          style={{
                            width: 6,
                            height: 6,
                            borderRadius: '50%',
                            marginRight: 8,
                            background: getApproverBadgeColor(approverState),
                            display: 'inline-block',
                          }}
                        />
                        <div style={{ flex: 1 }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                            <span style={{ fontWeight: 500 }}>{rec.approver_name}</span>
                            <span className={`status-badge status-${rec.transfer_status === 'transferred' ? 'transferred' : rec.status}`} style={{ fontSize: 11 }}>
                              {rec.transfer_status === 'transferred' ? '已转审' : STATUS_MAP[rec.status]}
                            </span>
                            {rec.is_added_signer && (
                              <span
                                className="status-badge"
                                style={{
                                  fontSize: 11,
                                  background: 'rgba(13, 110, 253, 0.12)',
                                  color: 'var(--primary)',
                                }}
                              >
                                加签人
                              </span>
                            )}
                            {rec.proxy_source && (
                              <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
                                ({rec.proxy_source} 代理)
                              </span>
                            )}
                            {rec.added_signer_by && (
                              <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
                                (由 {rec.added_signer_by} 追加)
                              </span>
                            )}
                            {isCurrentUserApprover && (
                              <>
                                <span
                                  className="status-badge"
                                  style={{
                                    fontSize: 11,
                                    background: 'rgba(13, 110, 253, 0.15)',
                                    color: 'var(--primary)',
                                  }}
                                >
                                  您的待办
                                </span>
                                <button
                                  className="btn btn-sm btn-outline"
                                  style={{
                                    marginLeft: 4,
                                    fontSize: 12,
                                    padding: '2px 10px',
                                    borderColor: 'var(--warning)',
                                    color: 'var(--warning)',
                                  }}
                                  onClick={() => onTransfer && onTransfer(rec)}
                                >
                                  🔄 转审
                                </button>
                              </>
                            )}
                          </div>
                          {(rec.opinion || rec.acted_at || rec.transferred_to || rec.added_signer_reason || rec.transfer_reason) && (
                            <div style={{ marginTop: 4 }}>
                              {rec.opinion && (
                                <div className="chain-node-opinion" style={{ marginTop: 0 }}>
                                  意见: {rec.opinion}
                                </div>
                              )}
                              {rec.transferred_to && (
                                <div style={{ fontSize: 12, color: 'var(--warning)', marginTop: rec.opinion ? 2 : 0 }}>
                                  转审给: {rec.transferred_to}
                                  {rec.transfer_reason && ` (原因: ${rec.transfer_reason})`}
                                </div>
                              )}
                              {rec.transferred_from && rec.status === 'pending' && !rec.transfer_status && (
                                <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 2 }}>
                                  转审来自: {rec.transferred_from}
                                  {rec.transfer_reason && ` (原因: ${rec.transfer_reason})`}
                                </div>
                              )}
                              {rec.added_signer_reason && (
                                <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 2 }}>
                                  加签原因: {rec.added_signer_reason}
                                </div>
                              )}
                              {rec.acted_at && (
                                <div className="chain-node-meta" style={{ fontSize: 12, marginTop: 2 }}>
                                  处理时间: {formatTime(rec.acted_at)}
                                </div>
                              )}
                            </div>
                          )}
                          {approverState === 'current' && !rec.acted_at && (
                            <div className="chain-node-meta" style={{ color: 'var(--primary)', fontSize: 12, fontWeight: 500 }}>
                              等待审批中...
                            </div>
                          )}
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function ApprovalTimeline({ timeline }) {
  if (!timeline || timeline.length === 0) return null

  return (
    <div className="card">
      <h3 style={{ marginBottom: 16 }}>
        审批时间线
        <span style={{ fontSize: 13, fontWeight: 400, color: 'var(--text-secondary)', marginLeft: 8 }}>
          共 {timeline.length} 条记录
        </span>
      </h3>
      <div
        style={{
          position: 'relative',
          paddingLeft: 28,
        }}
      >
        <div
          style={{
            position: 'absolute',
            left: 9,
            top: 4,
            bottom: 4,
            width: 2,
            background: 'var(--border)',
          }}
        />
        {timeline.map((event, idx) => (
          <div
            key={event.id}
            style={{
              position: 'relative',
              paddingBottom: idx < timeline.length - 1 ? 18 : 0,
            }}
          >
            <div
              style={{
                position: 'absolute',
                left: -28,
                top: 2,
                width: 20,
                height: 20,
                borderRadius: '50%',
                background: 'var(--bg-secondary)',
                border: '2px solid var(--border)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: 11,
              }}
            >
              {EVENT_ICON_MAP[event.event_type] || '📌'}
            </div>
            <div
              style={{
                background: 'var(--bg-secondary)',
                borderRadius: 8,
                padding: '10px 14px',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 4 }}>
                <span style={{ fontWeight: 600, fontSize: 14 }}>{event.event_type_cn}</span>
                {event.level && (
                  <span
                    className="status-badge"
                    style={{
                      fontSize: 11,
                      background: 'var(--bg-primary)',
                      color: 'var(--text-secondary)',
                    }}
                  >
                    Level {event.level}
                  </span>
                )}
                {event.status && (
                  <span className={`status-badge status-${event.status}`} style={{ fontSize: 11 }}>
                    {STATUS_MAP[event.status] || event.status}
                  </span>
                )}
                <span style={{ fontSize: 12, color: 'var(--text-secondary)', marginLeft: 'auto' }}>
                  {formatTime(event.created_at)}
                </span>
              </div>
              <div style={{ fontSize: 13, color: 'var(--text-primary)' }}>
                <span style={{ fontWeight: 500 }}>{event.operator}</span>
                {event.target_user && (
                  <span style={{ color: 'var(--text-secondary)' }}>
                    {' → '}
                    <span style={{ color: 'var(--primary)', fontWeight: 500 }}>{event.target_user}</span>
                    {event.target_role && (
                      <span style={{ color: 'var(--text-secondary)', fontSize: 12 }}>
                        {' '}({event.target_role})
                      </span>
                    )}
                  </span>
                )}
                {event.operator_id && (
                  <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
                    {' '}ID:{event.operator_id}
                  </span>
                )}
              </div>
              {(event.reason || event.opinion) && (
                <div
                  style={{
                    marginTop: 6,
                    fontSize: 13,
                    padding: '6px 10px',
                    background: 'var(--bg-primary)',
                    borderRadius: 4,
                    color: 'var(--text-secondary)',
                    borderLeft: '3px solid var(--primary)',
                  }}
                >
                  {event.reason && (
                    <div>
                      <span style={{ fontWeight: 500 }}>原因：</span>
                      {event.reason}
                    </div>
                  )}
                  {event.opinion && (
                    <div>
                      <span style={{ fontWeight: 500 }}>意见：</span>
                      {event.opinion}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function UserSelectModal({ title, users, onClose, onConfirm, reasonLabel = '原因', showNodeRecordSelect = false, pendingRecords = [] }) {
  const [selectedUserId, setSelectedUserId] = useState('')
  const [reason, setReason] = useState('')
  const [selectedNodeRecordId, setSelectedNodeRecordId] = useState('')

  const handleConfirm = () => {
    if (!selectedUserId) {
      alert('请选择目标用户')
      return
    }
    if (showNodeRecordSelect && !selectedNodeRecordId) {
      alert('请选择要加签的节点')
      return
    }
    onConfirm({
      userId: Number(selectedUserId),
      nodeRecordId: showNodeRecordSelect ? Number(selectedNodeRecordId) : null,
      reason: reason || undefined,
    })
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 480 }}>
        <h3>{title}</h3>
        <div className="form-group" style={{ marginBottom: 14 }}>
          <label>选择目标用户</label>
          <select
            value={selectedUserId}
            onChange={(e) => setSelectedUserId(e.target.value)}
            style={{ width: '100%' }}
          >
            <option value="">-- 请选择 --</option>
            {users.map((u) => (
              <option key={u.id} value={u.id}>
                {u.real_name || u.username} ({u.department || '-'}
                {u.roles && u.roles.length > 0 && ` - ${u.roles.join(', ')}`})
              </option>
            ))}
          </select>
        </div>
        {showNodeRecordSelect && pendingRecords.length > 0 && (
          <div className="form-group" style={{ marginBottom: 14 }}>
            <label>选择加签节点</label>
            <select
              value={selectedNodeRecordId}
              onChange={(e) => setSelectedNodeRecordId(e.target.value)}
              style={{ width: '100%' }}
            >
              <option value="">-- 请选择待审批的节点 --</option>
              {pendingRecords.map((r) => (
                <option key={r.id} value={r.id}>
                  #{r.id} - {r.approver_name} ({r.approver_role})
                </option>
              ))}
            </select>
          </div>
        )}
        <div className="form-group" style={{ marginBottom: 16 }}>
          <label>{reasonLabel}（可选）</label>
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder={`请输入${reasonLabel}（最多500字）`}
            rows={3}
            maxLength={500}
          />
        </div>
        <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end' }}>
          <button className="btn btn-outline" onClick={onClose}>取消</button>
          <button className="btn btn-primary" onClick={handleConfirm}>确认</button>
        </div>
      </div>
    </div>
  )
}

export default function ApprovalDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [approval, setApproval] = useState(null)
  const [loading, setLoading] = useState(true)
  const [opinion, setOpinion] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const [showAddSignerModal, setShowAddSignerModal] = useState(false)
  const [showTransferModal, setShowTransferModal] = useState(false)
  const [modalLoading, setModalLoading] = useState(false)
  const [availableUsers, setAvailableUsers] = useState([])
  const [pendingRecordsForAddSigner, setPendingRecordsForAddSigner] = useState([])
  const [transferTargetRecord, setTransferTargetRecord] = useState(null)
  const [currentUser, setCurrentUser] = useState(null)

  const fetchApproval = async () => {
    try {
      const res = await getApproval(id)
      setApproval(res.data)
    } catch {
      setApproval(null)
    } finally {
      setLoading(false)
    }
  }

  const fetchCurrentUser = async () => {
    try {
      const token = localStorage.getItem('token')
      if (token) {
        try {
          const res = await fetch('/api/auth/me', {
            headers: { 'Authorization': `Bearer ${token}` },
          })
          if (res.ok) {
            const profile = await res.json()
            const roleCodes = Array.isArray(profile.roles)
              ? profile.roles.map(r => (typeof r === 'string' ? r : r.code)).filter(Boolean)
              : []
            setCurrentUser({
              id: profile.id,
              username: profile.username,
              real_name: profile.real_name || profile.username,
              roles: roleCodes,
            })
            return
          }
        } catch (apiErr) {
          console.warn('API /me failed, falling back to token parse:', apiErr)
        }
        const payload = JSON.parse(atob(token.split('.')[1]))
        setCurrentUser({
          id: payload.user_id || payload.sub,
          username: payload.username || payload.sub,
          real_name: payload.real_name || payload.username || payload.sub,
          roles: payload.roles || [],
        })
      }
    } catch (e) {
      console.error('Failed to parse user from token:', e)
    }
  }

  useEffect(() => {
    fetchApproval()
    fetchCurrentUser()
  }, [id])

  if (loading) return <div className="empty-state"><p>加载中...</p></div>
  if (!approval) return <div className="empty-state"><p>审批单不存在</p></div>

  const handleApprove = async () => {
    setSubmitting(true)
    try {
      await approveApproval(id, { opinion: opinion || undefined })
      alert('审批通过成功')
      setOpinion('')
      fetchApproval()
    } catch (err) {
      alert(err.response?.data?.detail || '操作失败')
    } finally {
      setSubmitting(false)
    }
  }

  const handleReject = async () => {
    setSubmitting(true)
    try {
      await rejectApproval(id, { opinion: opinion || undefined })
      alert('审批驳回成功')
      setOpinion('')
      fetchApproval()
    } catch (err) {
      alert(err.response?.data?.detail || '操作失败')
    } finally {
      setSubmitting(false)
    }
  }

  const handleAddSigner = async (level, records) => {
    try {
      setModalLoading(true)
      const pendingRecords = records.filter(
        (r) => r.status === 'pending' && r.transfer_status !== 'transferred'
      )
      setPendingRecordsForAddSigner(pendingRecords)
      const res = await getAvailableApprovalUsers()
      setAvailableUsers(res.data.items || res.data || [])
      setShowAddSignerModal(true)
    } finally {
      setModalLoading(false)
    }
  }

  const handleConfirmAddSigner = async ({ userId, nodeRecordId, reason }) => {
    setModalLoading(true)
    try {
      await addSigner(id, {
        node_record_id: nodeRecordId,
        target_user_id: userId,
        reason,
      })
      alert('加签成功')
      setShowAddSignerModal(false)
      fetchApproval()
    } catch (err) {
      alert(err.response?.data?.detail || '加签失败')
    } finally {
      setModalLoading(false)
    }
  }

  const handleTransfer = async (record) => {
    try {
      setModalLoading(true)
      setTransferTargetRecord(record)
      const res = await getAvailableApprovalUsers()
      setAvailableUsers(res.data.items || res.data || [])
      setShowTransferModal(true)
    } finally {
      setModalLoading(false)
    }
  }

  const handleConfirmTransfer = async ({ userId, reason }) => {
    setModalLoading(true)
    try {
      await transferApproval(id, {
        node_record_id: transferTargetRecord.id,
        target_user_id: userId,
        reason,
      })
      alert('转审成功')
      setShowTransferModal(false)
      setTransferTargetRecord(null)
      fetchApproval()
    } catch (err) {
      alert(err.response?.data?.detail || '转审失败')
    } finally {
      setModalLoading(false)
    }
  }

  return (
    <div className="approval-detail">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <h2>审批详情</h2>
        <button className="btn btn-outline" onClick={() => navigate(-1)}>返回</button>
      </div>

      <div className="card approval-header">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 20 }}>
          <div>
            <h3 style={{ marginBottom: 8 }}>
              审批单 #{approval.id}
            </h3>
            <span style={{ fontSize: 14, color: 'var(--text-secondary)' }}>
              {TYPE_MAP[approval.approval_type] || approval.approval_type}
            </span>
          </div>
          <span className={`status-badge status-${approval.status}`}>
            {STATUS_MAP[approval.status]}
          </span>
        </div>
        <div className="detail-grid">
          <div className="detail-item">
            <span className="label">资产名称</span>
            <span className="value">{approval.asset_name || '-'}</span>
          </div>
          <div className="detail-item">
            <span className="label">资产编号</span>
            <span className="value" style={{ fontFamily: 'monospace' }}>{approval.asset_tag || '-'}</span>
          </div>
          <div className="detail-item">
            <span className="label">申请人</span>
            <span className="value">{approval.applicant}</span>
          </div>
          <div className="detail-item">
            <span className="label">领用人</span>
            <span className="value">{approval.assignee || '-'}</span>
          </div>
          <div className="detail-item">
            <span className="label">申请原因</span>
            <span className="value">{approval.reason || '-'}</span>
          </div>
          <div className="detail-item">
            <span className="label">购入价格</span>
            <span className="value">{approval.purchase_price != null ? `¥${approval.purchase_price}` : '-'}</span>
          </div>
          <div className="detail-item">
            <span className="label">申请时间</span>
            <span className="value">{formatTime(approval.created_at)}</span>
          </div>
          <div className="detail-item">
            <span className="label">更新时间</span>
            <span className="value">{formatTime(approval.updated_at)}</span>
          </div>
        </div>
      </div>

      <ChainTimeline
        approval={approval}
        currentUser={currentUser}
        onAddSigner={handleAddSigner}
        onTransfer={handleTransfer}
      />

      <ApprovalTimeline timeline={approval.timeline} />

      {approval.status === 'pending' && (
        <div className="card approval-actions">
          <h3 style={{ marginBottom: 16 }}>审批操作</h3>
          <div className="form-group" style={{ marginBottom: 16 }}>
            <label>审批意见</label>
            <textarea
              value={opinion}
              onChange={(e) => setOpinion(e.target.value)}
              placeholder="请输入审批意见（可选）"
              rows={3}
            />
          </div>
          <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end' }}>
            <button
              className="btn btn-danger"
              onClick={handleReject}
              disabled={submitting}
            >
              {submitting ? '处理中...' : '驳回'}
            </button>
            <button
              className="btn btn-success"
              onClick={handleApprove}
              disabled={submitting}
            >
              {submitting ? '处理中...' : '通过'}
            </button>
          </div>
        </div>
      )}

      {showAddSignerModal && (
        <UserSelectModal
          title="会签加签"
          users={availableUsers}
          reasonLabel="加签原因"
          showNodeRecordSelect={pendingRecordsForAddSigner.length > 1}
          pendingRecords={pendingRecordsForAddSigner}
          onClose={() => setShowAddSignerModal(false)}
          onConfirm={handleConfirmAddSigner}
        />
      )}

      {showTransferModal && transferTargetRecord && (
        <UserSelectModal
          title={`转审 - 将 ${transferTargetRecord.approver_name} 的待办转审给他人`}
          users={availableUsers.filter((u) => u.id !== currentUser?.id)}
          reasonLabel="转审原因"
          onClose={() => {
            setShowTransferModal(false)
            setTransferTargetRecord(null)
          }}
          onConfirm={handleConfirmTransfer}
        />
      )}
    </div>
  )
}
