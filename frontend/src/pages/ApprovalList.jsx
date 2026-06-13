import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { getApprovals, approveApproval, rejectApproval } from '../api/assets'

const STATUS_MAP = {
  pending: '待审批',
  approved: '已通过',
  rejected: '已驳回',
}

const TYPE_MAP = {
  allocate: '领用审批',
  scrap: '报废审批',
}

export default function ApprovalList() {
  const navigate = useNavigate()
  const [approvals, setApprovals] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [keyword, setKeyword] = useState('')
  const [status, setStatus] = useState('')
  const [approvalType, setApprovalType] = useState('')
  const [showActionModal, setShowActionModal] = useState(null)
  const [actionType, setActionType] = useState('')
  const [opinion, setOpinion] = useState('')
  const pageSize = 20

  const fetchApprovals = async () => {
    const params = { page, page_size: pageSize }
    if (keyword) params.keyword = keyword
    if (status) params.status = status
    if (approvalType) params.approval_type = approvalType
    const res = await getApprovals(params)
    setApprovals(res.data.items)
    setTotal(res.data.total)
  }

  useEffect(() => { fetchApprovals() }, [page, status, approvalType])

  const handleSearch = (e) => {
    e.preventDefault()
    setPage(1)
    fetchApprovals()
  }

  const handleAction = (approval, type) => {
    setShowActionModal(approval)
    setActionType(type)
    setOpinion('')
  }

  const handleConfirmAction = async () => {
    if (!showActionModal) return
    try {
      if (actionType === 'approve') {
        await approveApproval(showActionModal.id, { opinion })
        alert('审批通过成功')
      } else {
        await rejectApproval(showActionModal.id, { opinion })
        alert('审批驳回成功')
      }
      setShowActionModal(null)
      setOpinion('')
      fetchApprovals()
    } catch (err) {
      alert(err.response?.data?.detail || '操作失败')
    }
  }

  const totalPages = Math.ceil(total / pageSize)

  return (
    <div>
      <div className="toolbar">
        <form onSubmit={handleSearch} style={{ display: 'flex', gap: 12, flex: 1 }}>
          <input
            type="text"
            placeholder="搜索资产名称、编号、序列号..."
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
          />
          <button type="submit" className="btn btn-primary">搜索</button>
        </form>
        <select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1) }}>
          <option value="">全部状态</option>
          {Object.entries(STATUS_MAP).map(([k, v]) => (
            <option key={k} value={k}>{v}</option>
          ))}
        </select>
        <select value={approvalType} onChange={(e) => { setApprovalType(e.target.value); setPage(1) }}>
          <option value="">全部类型</option>
          {Object.entries(TYPE_MAP).map(([k, v]) => (
            <option key={k} value={k}>{v}</option>
          ))}
        </select>
      </div>

      <div className="card">
        {approvals.length === 0 ? (
          <div className="empty-state">
            <p>暂无审批单</p>
          </div>
        ) : (
          <>
            <table>
              <thead>
                <tr>
                  <th>审批单ID</th>
                  <th>资产编号</th>
                  <th>资产名称</th>
                  <th>类型</th>
                  <th>申请人</th>
                  <th>领用人</th>
                  <th>审批级别</th>
                  <th>状态</th>
                  <th>申请时间</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {approvals.map((a) => (
                  <tr key={a.id}>
                    <td style={{ fontFamily: 'monospace', fontSize: 13 }}>#{a.id}</td>
                    <td style={{ fontFamily: 'monospace', fontSize: 13 }}>{a.asset_tag}</td>
                    <td>{a.asset_name}</td>
                    <td>{TYPE_MAP[a.approval_type] || a.approval_type}</td>
                    <td>{a.applicant}</td>
                    <td>{a.assignee || '-'}</td>
                    <td>
                      {a.total_levels > 1
                        ? `${a.current_level}/${a.total_levels}`
                        : '-'}
                    </td>
                    <td>
                      <span className={`status-badge status-${a.status}`}>
                        {STATUS_MAP[a.status]}
                      </span>
                    </td>
                    <td style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                      {new Date(a.created_at).toLocaleString('zh-CN')}
                    </td>
                    <td>
                      <div className="actions-cell">
                        <button
                          className="btn btn-outline btn-sm"
                          onClick={() => navigate(`/approvals/${a.id}`)}
                        >
                          详情
                        </button>
                        {a.status === 'pending' && (
                          <>
                            <button
                              className="btn btn-success btn-sm"
                              onClick={() => handleAction(a, 'approve')}
                            >
                              通过
                            </button>
                            <button
                              className="btn btn-danger btn-sm"
                              onClick={() => handleAction(a, 'reject')}
                            >
                              驳回
                            </button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {totalPages > 1 && (
              <div className="pagination">
                <button disabled={page <= 1} onClick={() => setPage(page - 1)}>上一页</button>
                <span>第 {page} / {totalPages} 页 (共 {total} 条)</span>
                <button disabled={page >= totalPages} onClick={() => setPage(page + 1)}>下一页</button>
              </div>
            )}
          </>
        )}
      </div>

      {showActionModal && (
        <div className="modal-overlay" onClick={() => setShowActionModal(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>{actionType === 'approve' ? '通过审批' : '驳回审批'}</h3>
            <p style={{ marginBottom: 16, fontSize: 14, color: 'var(--text-secondary)' }}>
              审批单 #{showActionModal.id} - {TYPE_MAP[showActionModal.approval_type]}
              {showActionModal.total_levels > 1 && (
                <span> (第{showActionModal.current_level}/{showActionModal.total_levels}级)</span>
              )}
            </p>
            <div className="form-group" style={{ marginBottom: 16 }}>
              <label>审批意见</label>
              <textarea
                value={opinion}
                onChange={(e) => setOpinion(e.target.value)}
                placeholder="请输入审批意见（可选）"
                rows={4}
              />
            </div>
            <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end' }}>
              <button className="btn btn-outline" onClick={() => setShowActionModal(null)}>取消</button>
              <button
                className={actionType === 'approve' ? 'btn btn-success' : 'btn btn-danger'}
                onClick={handleConfirmAction}
              >
                {actionType === 'approve' ? '确认通过' : '确认驳回'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
