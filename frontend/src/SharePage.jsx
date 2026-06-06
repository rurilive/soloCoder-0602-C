import React, { useState, useEffect } from 'react'
import { useParams } from 'react-router-dom'
import { api } from './api'

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

export default function SharePage() {
  const { shareId } = useParams()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [shareData, setShareData] = useState(null)
  const [password, setPassword] = useState('')
  const [needPassword, setNeedPassword] = useState(false)

  const loadShare = (pwd = '') => {
    setLoading(true)
    setError(null)
    api.getShare(shareId, pwd || undefined).then(res => {
      setShareData(res.data)
      setLoading(false)
    }).catch(err => {
      const msg = err.response?.data?.error
      if (msg === 'Password required') {
        setNeedPassword(true)
        setLoading(false)
      } else {
        setError(msg || '加载失败')
        setLoading(false)
      }
    })
  }

  useEffect(() => {
    loadShare()
  }, [shareId])

  const handleSubmit = (e) => {
    e.preventDefault()
    loadShare(password)
  }

  const handleDownload = (subpath = '') => {
    const url = api.shareDownload(shareId, password, subpath)
    window.open(url, '_blank')
  }

  if (loading) {
    return (
      <div className="share-page">
        <div className="share-container">
          <div style={{ textAlign: 'center', padding: '40px 0' }}>⏳ 加载中...</div>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="share-page">
        <div className="share-container">
          <h2>❌ 无法访问</h2>
          <p style={{ textAlign: 'center', color: '#666' }}>{error}</p>
        </div>
      </div>
    )
  }

  if (needPassword && !shareData) {
    return (
      <div className="share-page">
        <div className="share-container">
          <h2>🔒 分享文件</h2>
          <p style={{ textAlign: 'center', color: '#666', marginBottom: '20px' }}>此分享需要密码访问</p>
          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label>访问密码</label>
              <input type="password" value={password} onChange={e => setPassword(e.target.value)} autoFocus />
            </div>
            <button type="submit" className="btn btn-primary" style={{ width: '100%' }}>提交</button>
          </form>
        </div>
      </div>
    )
  }

  return (
    <div className="share-page">
      <div className="share-container">
        <h2>📎 分享文件</h2>
        {shareData?.type === 'file' && (
          <div>
            <div style={{ background: '#f8f9fa', padding: '20px', borderRadius: '8px', marginBottom: '20px' }}>
              <div style={{ fontSize: '32px', marginBottom: '10px' }}>
                {['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg'].includes(shareData.item.extension) ? '🖼️' : '📄'}
              </div>
              <div style={{ fontWeight: '600', marginBottom: '8px' }}>{shareData.item.name}</div>
              <div style={{ color: '#888', fontSize: '13px' }}>
                {formatSize(shareData.item.size)} · {formatDate(shareData.item.modified)}
              </div>
            </div>
            <button className="btn btn-primary" style={{ width: '100%' }} onClick={() => handleDownload(shareData.item.path)}>
              ⬇️ 下载文件
            </button>
          </div>
        )}
        {shareData?.type === 'dir' && (
          <div>
            <p style={{ color: '#666', marginBottom: '12px' }}>包含 {shareData.items?.length || 0} 个文件/文件夹</p>
            <div style={{ maxHeight: '400px', overflow: 'auto', border: '1px solid #eee', borderRadius: '8px' }}>
              {shareData.items?.map(item => {
                const relPath = item.path.startsWith(shareData.path + '/')
                  ? item.path.slice(shareData.path.length + 1)
                  : item.path
                return (
                  <div key={item.path} style={{ padding: '10px 12px', borderBottom: '1px solid #f0f0f0', display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <span>{item.isDir ? '📁' : '📄'}</span>
                    <span style={{ flex: 1 }}>{item.name}</span>
                    <span style={{ color: '#888', fontSize: '12px', marginRight: '8px' }}>{item.isDir ? '-' : formatSize(item.size)}</span>
                    {!item.isDir && (
                      <button
                        className="btn btn-secondary btn-small"
                        onClick={(e) => { e.stopPropagation(); handleDownload(relPath); }}
                        style={{ padding: '4px 10px', fontSize: '12px' }}
                      >
                        ⬇️ 下载
                      </button>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
