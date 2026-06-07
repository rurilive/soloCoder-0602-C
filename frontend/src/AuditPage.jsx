import React, { useState, useEffect } from 'react'
import { api } from './api'
import { useNavigate } from 'react-router-dom'

function formatDate(iso) {
  const d = new Date(iso)
  return d.toLocaleDateString('zh-CN') + ' ' + d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

const ACTION_NAMES = {
  upload: '上传文件',
  delete: '删除文件',
  rename: '重命名',
  move: '移动文件',
  copy: '复制文件',
  share: '创建分享',
  create_folder: '创建文件夹',
  restore_trash: '恢复文件',
  permanent_delete: '永久删除',
  empty_trash: '清空回收站',
}

const ACTION_TYPES = [
  { value: '', label: '全部操作' },
  { value: 'upload', label: '上传文件' },
  { value: 'delete', label: '删除文件' },
  { value: 'rename', label: '重命名' },
  { value: 'move', label: '移动文件' },
  { value: 'copy', label: '复制文件' },
  { value: 'share', label: '创建分享' },
  { value: 'create_folder', label: '创建文件夹' },
  { value: 'restore_trash', label: '恢复文件' },
  { value: 'permanent_delete', label: '永久删除' },
  { value: 'empty_trash', label: '清空回收站' },
]

function AuditPage() {
  const navigate = useNavigate()
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [perPage] = useState(20)
  const [actionType, setActionType] = useState('')

  const loadAuditLogs = async (currentPage = 1, currentActionType = '') => {
    setLoading(true)
    try {
      const res = await api.getAuditLogs(currentPage, perPage, currentActionType)
      setItems(res.data.items || [])
      setTotal(res.data.total || 0)
      setPage(currentPage)
    } catch (e) {
      setItems([])
      setTotal(0)
    }
    setLoading(false)
  }

  useEffect(() => {
    loadAuditLogs(1, actionType)
  }, [actionType])

  const totalPages = Math.ceil(total / perPage)

  const handlePageChange = (newPage) => {
    if (newPage < 1 || newPage > totalPages) return
    loadAuditLogs(newPage, actionType)
  }

  const renderPagination = () => {
    if (totalPages <= 1) return null
    const pages = []
    const maxVisible = 5
    let start = Math.max(1, page - Math.floor(maxVisible / 2))
    let end = Math.min(totalPages, start + maxVisible - 1)
    if (end - start + 1 < maxVisible) {
      start = Math.max(1, end - maxVisible + 1)
    }

    return (
      <div className="pagination">
        <button
          className="btn btn-secondary btn-small"
          onClick={() => handlePageChange(page - 1)}
          disabled={page <= 1}
        >
          上一页
        </button>
        {start > 1 && (
          <>
            <button className="btn btn-secondary btn-small" onClick={() => handlePageChange(1)}>1</button>
            {start > 2 && <span className="pagination-ellipsis">...</span>}
          </>
        )}
        {Array.from({ length: end - start + 1 }, (_, i) => start + i).map(p => (
          <button
            key={p}
            className={`btn btn-small ${p === page ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => handlePageChange(p)}
          >
            {p}
          </button>
        ))}
        {end < totalPages && (
          <>
            {end < totalPages - 1 && <span className="pagination-ellipsis">...</span>}
            <button className="btn btn-secondary btn-small" onClick={() => handlePageChange(totalPages)}>{totalPages}</button>
          </>
        )}
        <button
          className="btn btn-secondary btn-small"
          onClick={() => handlePageChange(page + 1)}
          disabled={page >= totalPages}
        >
          下一页
        </button>
      </div>
    )
  }

  return (
    <div className="app">
      <header className="header">
        <h1>📋 审计日志</h1>
        <div className="actions">
          <button className="btn btn-secondary" onClick={() => navigate('/')}>📂 返回文件管理</button>
        </div>
      </header>

      <main className="main">
        <div className="breadcrumb">
          <span>查看您的所有文件操作历史记录</span>
        </div>

        <div className="toolbar">
          <div className="filter-bar">
            <label>操作类型：</label>
            <select
              className="search-ext-select"
              value={actionType}
              onChange={(e) => setActionType(e.target.value)}
            >
              {ACTION_TYPES.map(t => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
            <span style={{ marginLeft: 'auto', color: '#999', fontSize: '13px' }}>
              共 {total} 条记录
            </span>
          </div>
        </div>

        <div className="audit-list">
          {loading && <div className="empty-state"><div className="icon">⏳</div>加载中...</div>}
          {!loading && items.length === 0 && (
            <div className="empty-state">
              <div className="icon">📋</div>
              <div>暂无操作记录</div>
            </div>
          )}
          {items.map((item, index) => (
            <div key={`${item.timestamp}-${index}`} className="audit-item">
              <div className="audit-icon">
                {item.action === 'upload' && '📤'}
                {item.action === 'delete' && '🗑️'}
                {item.action === 'rename' && '✏️'}
                {item.action === 'move' && '📋'}
                {item.action === 'copy' && '📄'}
                {item.action === 'share' && '🔗'}
                {item.action === 'create_folder' && '📁'}
                {item.action === 'restore_trash' && '↩️'}
                {item.action === 'permanent_delete' && '💀'}
                {item.action === 'empty_trash' && '🧹'}
                {!Object.keys(ACTION_NAMES).includes(item.action) && '📝'}
              </div>
              <div className="audit-content">
                <div className="audit-action">
                  {ACTION_NAMES[item.action] || item.action}
                </div>
                <div className="audit-path">
                  {item.path || '（无路径）'}
                </div>
                {item.newName && (
                  <div className="audit-extra">
                    新名称: {item.newName}
                  </div>
                )}
                {item.newPath && item.newPath !== item.path && (
                  <div className="audit-extra">
                    新路径: {item.newPath}
                  </div>
                )}
                {item.dst && (
                  <div className="audit-extra">
                    目标: {item.dst}
                  </div>
                )}
                {item.shareId && (
                  <div className="audit-extra">
                    分享ID: {item.shareId}
                    {item.expireHours && ` · 有效期: ${item.expireHours}小时`}
                    {item.hasPassword && ' · 🔒 有密码'}
                  </div>
                )}
              </div>
              <div className="audit-time">
                {formatDate(item.timestamp)}
              </div>
            </div>
          ))}
        </div>

        {renderPagination()}
      </main>
    </div>
  )
}

export default AuditPage
