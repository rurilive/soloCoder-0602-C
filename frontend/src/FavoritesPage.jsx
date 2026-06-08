import React, { useState, useEffect, useRef } from 'react'
import { api, createSocket } from './api'
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

function getIconClass(item) {
  if (item.isDir) return 'icon-folder'
  const ext = item.extension
  if (['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg'].includes(ext)) return 'icon-image'
  return 'icon-file'
}

function FavoritesPage() {
  const navigate = useNavigate()
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [showPreview, setShowPreview] = useState(false)
  const [previewData, setPreviewData] = useState(null)
  const [previewItem, setPreviewItem] = useState(null)
  const socketRef = useRef(null)

  const loadFavorites = async () => {
    setLoading(true)
    try {
      const res = await api.listFavorites()
      setItems(res.data.items || [])
    } catch (e) {
      setItems([])
    }
    setLoading(false)
  }

  useEffect(() => {
    loadFavorites()

    const socket = createSocket()
    if (socket) {
      socketRef.current = socket

      socket.on('file_event', (event) => {
        const { type } = event
        if (type === 'favorite_change') {
          loadFavorites()
        }
      })
    }

    return () => {
      if (socketRef.current) {
        socketRef.current.disconnect()
        socketRef.current = null
      }
    }
  }, [])

  const handleRemoveFavorite = async (item) => {
    if (!confirm(`确定要取消收藏 "${item.name}" 吗？`)) return
    try {
      await api.removeFavorite(item.path)
      loadFavorites()
    } catch (e) {
      alert('取消收藏失败: ' + (e.response?.data?.error || e.message))
    }
  }

  const handlePreview = async (item) => {
    if (item.isDir) {
      navigate('/')
      return
    }
    setPreviewItem(item)
    const ext = item.extension
    if (['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg'].includes(ext)) {
      api.previewFile(item.path).then(res => {
        const url = URL.createObjectURL(res.data)
        setPreviewData({ type: 'image', url, name: item.name })
        setShowPreview(true)
      })
    } else if (['.txt', '.md', '.json', '.xml', '.html', '.css', '.js', '.py', '.csv', '.log'].includes(ext)) {
      api.previewText(item.path).then(data => {
        setPreviewData({ type: 'text', content: data.content, name: item.name })
        setShowPreview(true)
      })
    } else if (ext === '.pdf') {
      const url = api.downloadFile(item.path)
      setPreviewData({ type: 'pdf', url, name: item.name })
      setShowPreview(true)
    } else {
      alert('该文件类型不支持预览')
    }
  }

  return (
    <div className="app">
      <header className="header">
        <h1>⭐ 收藏夹</h1>
        <div className="actions">
          <button className="btn btn-secondary" onClick={() => navigate('/')}>📂 返回文件管理</button>
        </div>
      </header>

      <main className="main">
        <div className="breadcrumb">
          <span>已收藏 {items.length} 个文件/文件夹</span>
        </div>

        <div className="file-list">
          {loading && <div className="empty-state"><div className="icon">⏳</div>加载中...</div>}
          {!loading && items.length === 0 && (
            <div className="empty-state">
              <div className="icon">⭐</div>
              <div>收藏夹为空，在文件列表中点击星标按钮即可添加收藏</div>
            </div>
          )}
          {items.map(item => (
            <div
              key={item.path}
              className="file-item"
              onDoubleClick={() => handlePreview(item)}
            >
              <div className={`icon ${getIconClass(item)}`}>{getIconEmoji(item)}</div>
              <div className="name">{item.name}</div>
              <div className="size">{item.isDir ? '-' : formatSize(item.size)}</div>
              <div className="date">收藏: {formatDate(item.favoritedAt)}</div>
              <div className="item-actions">
                <button
                  className="btn btn-small fav-btn fav-active"
                  onClick={(e) => { e.stopPropagation(); handleRemoveFavorite(item) }}
                  title="取消收藏"
                >★</button>
                <button className="btn btn-secondary btn-small" onClick={(e) => { e.stopPropagation(); handlePreview(item) }}>预览</button>
                <button className="btn btn-secondary btn-small" onClick={(e) => { e.stopPropagation(); window.open(api.downloadFile(item.path), '_blank') }}>下载</button>
              </div>
            </div>
          ))}
        </div>
      </main>

      {showPreview && previewData && (
        <div className="modal-overlay preview-modal" onClick={() => { setShowPreview(false); setPreviewData(null) }}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <h3>{previewData.name}</h3>
            <div className="preview-content">
              {previewData.type === 'image' && <img src={previewData.url} alt="" />}
              {previewData.type === 'text' && <pre>{previewData.content}</pre>}
              {previewData.type === 'pdf' && <iframe className="preview-pdf" src={previewData.url} />}
            </div>
            <div className="modal-actions">
              <button className="btn btn-secondary" onClick={() => { setShowPreview(false); setPreviewData(null) }}>关闭</button>
              <button className="btn btn-primary" onClick={() => window.open(api.downloadFile(previewItem?.path), '_blank')}>下载</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default FavoritesPage
