import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getApproval, approveApproval, rejectApproval } from '../api/assets'

const STATUS_MAP = {
  pending: '待审批',
  approved: '已通过',
  rejected: '已驳回',
}

const TYPE_MAP = {
  allocate: '领用审批',
  scrap: '报废审批',
}

function formatTime(t) {
  if (!t) return '-'
  return new Date(t).toLocaleString('zh-CN')
}

function getNodeState(node, approval) {
  if (node.status === 'approved') return 'approved'
  if (node.status === 'rejected') return 'rejected'
  if (approval.status === 'pending' && node.level === approval.current_level) return 'current'
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
  return (
    <span className="chain-node-icon chain-node-pending" style={{ color: 'var(--border)' }}>
      ○
    </span>
  )
}

function ChainTimeline({ approval }) {
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

  const sortedNodes = [...nodes].sort((a, b) => a.level - b.level)

  return (
    <div className="card">
      <h3 style={{ marginBottom: 16 }}>
        审批流程
        <span style={{ fontSize: 13, fontWeight: 400, color: 'var(--text-secondary)', marginLeft: 8 }}>
          共 {approval.total_levels} 级审批
        </span>
      </h3>
      <div className="approval-chain-timeline">
        {sortedNodes.map((node, idx) => {
          const state = getNodeState(node, approval)
          return (
            <div key={node.id} className={`approval-chain-node chain-node-${state}`}>
              {idx < sortedNodes.length - 1 && <div className="chain-connector" />}
              <NodeIcon state={state} />
              <div className="chain-node-content">
                <div className="chain-node-title">
                  <span>第 {node.level} 级 - {node.approver_role}</span>
                  <span className={`status-badge status-${node.status}`} style={{ marginLeft: 8 }}>
                    {STATUS_MAP[node.status]}
                  </span>
                </div>
                <div className="chain-node-meta">
                  审批人: {node.approver_name}
                </div>
                {(state === 'approved' || state === 'rejected') && (
                  <>
                    {node.opinion && (
                      <div className="chain-node-opinion">意见: {node.opinion}</div>
                    )}
                    {node.acted_at && (
                      <div className="chain-node-meta" style={{ fontSize: 12 }}>
                        处理时间: {formatTime(node.acted_at)}
                      </div>
                    )}
                  </>
                )}
                {state === 'current' && (
                  <div className="chain-node-meta" style={{ color: 'var(--primary)', fontWeight: 500 }}>
                    等待审批中...
                  </div>
                )}
              </div>
            </div>
          )
        })}
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

  useEffect(() => { fetchApproval() }, [id])

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

      <ChainTimeline approval={approval} />

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
    </div>
  )
}
