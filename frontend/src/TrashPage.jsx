import React, { useState, useEffect } from 'react'
import { api } from './api'
import { useNavigate } from 'react-router-dom'

function formatSize(bytes) {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
}

function formatDate(iso) {
  const d = new Date(iso)
  return d.toLocaleDateString('zh-CN') + ' ' + d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

function getIconEmoji(item) {
  if (item.isDir) return '📁'
  const ext = item.extension
  if (['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg'].includes(ext)) return '🖼️'
  if (ext === '.pdf') return '📄'
  if (['.txt', '.md', '.json', '.xml', '.html', '.css', '.js', '.py', '.csv', '.log'].includes(ext)) return '📝'
  return '📄'
}

function TrashPage() {
  const navigate = useNavigate()
  const [items, setItems] = useState([])
  const [selected, setSelected] = useState(null)
  const [loading, setLoading] = useState(true)

  const loadTrash = async () => {
    setLoading(true)
    try {
      const res = await api.listTrash()
      setItems(res.data.items || [])
    } catch (e) {
      setItems([])
    }
    setLoading(false)
  }

  useEffect(() => {
    loadTrash()
  }, [])

  const handleRestore = async (item) => {
    if (!confirm(`确定要恢复 "${item.name}" 吗？`)) return
    try {
      await api.restoreTrashItem(item.path)
      alert('恢复成功')
      loadTrash()
      setSelected(null)
    } catch (e) {
      alert('恢复失败: ' + (e.response?.data?.error || e.message))
    }
  }

  const handlePermanentDelete = async (item) => {
    if (!confirm(`确定要永久删除 "${item.name}" 吗？此操作不可撤销！`)) return
    try {
      await api.permanentlyDeleteTrashItem(item.path)
      alert('已永久删除')
      loadTrash()
      setSelected(null)
    } catch (e) {
      alert('删除失败: ' + (e.response?.data?.error || e.message))
    }
  }

  const handleEmptyTrash = async () => {
    if (!confirm('确定要清空回收站吗？所有文件将被永久删除，此操作不可撤销！')) return
    try {
      await api.emptyTrash()
      alert('回收站已清空')
      loadTrash()
      setSelected(null)
    } catch (e) {
      alert('清空失败: ' + (e.response?.data?.error || e.message))
    }
  }

  return (
    <div className="app">
      <header className="header">
        <h1>🗑️ 回收站</h1>
        <div className="actions">
          <button className="btn btn-secondary" onClick={() => navigate('/')}>📂 返回文件管理</button>
          {items.length > 0 && (
            <button className="btn btn-danger" onClick={handleEmptyTrash}>🗑️ 清空回收站</button>
          )}
        </div>
      </header>

      <main className="main">
        <div className="breadcrumb">
          <span>回收站中的文件将在 30 天后自动清理</span>
        </div>

        <div className="toolbar">
          {selected && (
            <>
              <button className="btn btn-secondary btn-small" onClick={() => handleRestore(selected)}>↩️ 恢复</button>
              <button className="btn btn-danger btn-small" onClick={() => handlePermanentDelete(selected)}>🗑️ 永久删除</button>
            </>
          )}
          {!selected && items.length > 0 && <span style={{ color: '#999', fontSize: '13px' }}>选择文件进行操作</span>}
        </div>

        <div className="file-list">
          {loading && <div className="empty-state"><div className="icon">⏳</div>加载中...</div>}
          {!loading && items.length === 0 && (
            <div className="empty-state">
              <div className="icon">🗑️</div>
              <div>回收站为空</div>
            </div>
          )}
          {items.map(item => (
            <div
              key={item.path}
              className={`file-item ${selected?.path === item.path ? 'selected' : ''}`}
              onClick={() => setSelected(item)}
            >
              <div className="icon">{getIconEmoji(item)}</div>
              <div className="name">{item.name}</div>
              <div className="size">{item.isDir ? '-' : formatSize(item.size)}</div>
              <div className="date">删除时间: {formatDate(item.deletedAt)}</div>
              <div className="item-actions">
                <button className="btn btn-secondary btn-small" onClick={(e) => { e.stopPropagation(); handleRestore(item) }}>恢复</button>
                <button className="btn btn-danger btn-small" onClick={(e) => { e.stopPropagation(); handlePermanentDelete(item) }}>删除</button>
              </div>
            </div>
          ))}
        </div>
      </main>
    </div>
  )
}

export default TrashPage
