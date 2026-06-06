import React, { useState, useEffect, useRef } from 'react'
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

function getIconClass(item) {
  if (item.isDir) return 'icon-folder'
  const ext = item.extension
  if (['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg'].includes(ext)) return 'icon-image'
  return 'icon-file'
}

function getIconEmoji(item) {
  if (item.isDir) return '📁'
  const ext = item.extension
  if (['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg'].includes(ext)) return '🖼️'
  if (ext === '.pdf') return '📄'
  if (['.txt', '.md', '.json', '.xml', '.html', '.css', '.js', '.py', '.csv', '.log'].includes(ext)) return '📝'
  return '📄'
}

function App() {
  const [currentPath, setCurrentPath] = useState('')
  const [files, setFiles] = useState([])
  const [selected, setSelected] = useState(null)
  const [loading, setLoading] = useState(true)
  const [showUploadModal, setShowUploadModal] = useState(false)
  const [showNewFolderModal, setShowNewFolderModal] = useState(false)
  const [showRenameModal, setShowRenameModal] = useState(false)
  const [showMoveModal, setShowMoveModal] = useState(false)
  const [showShareModal, setShowShareModal] = useState(false)
  const [showPreview, setShowPreview] = useState(false)
  const [previewData, setPreviewData] = useState(null)
  const [newFolderName, setNewFolderName] = useState('')
  const [renameValue, setRenameValue] = useState('')
  const [moveTarget, setMoveTarget] = useState('')
  const [shareExpire, setShareExpire] = useState('')
  const [sharePassword, setSharePassword] = useState('')
  const [shareResult, setShareResult] = useState(null)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [contextMenu, setContextMenu] = useState(null)
  const fileInputRef = useRef(null)

  const loadFiles = async (path = currentPath) => {
    setLoading(true)
    api.listFiles(path).then(res => {
      setFiles(res.data.items || [])
      setCurrentPath(path)
      setLoading(false)
    }).catch(() => setLoading(false))
  }

  useEffect(() => {
    loadFiles('')
  }, [])

  const navigateTo = (path) => {
    loadFiles(path)
    setSelected(null)
  }

  const handleUpload = (e) => {
    const file = e.target.files[0]
    if (!file) return
    setUploadProgress(0)
    api.uploadFile(currentPath, file, (p) => setUploadProgress(p)).then(() => {
      setShowUploadModal(false)
      loadFiles()
      setUploadProgress(0)
      if (fileInputRef.current) fileInputRef.current.value = ''
    })
  }

  const handleCreateFolder = () => {
    if (!newFolderName.trim()) return
    api.createFolder(currentPath, newFolderName.trim()).then(() => {
      setShowNewFolderModal(false)
      setNewFolderName('')
      loadFiles()
    })
  }

  const handleRename = () => {
    if (!renameValue.trim() || !selected) return
    api.renameItem(selected.path, renameValue.trim()).then(() => {
      setShowRenameModal(false)
      setRenameValue('')
      setSelected(null)
      loadFiles()
    })
  }

  const handleDelete = () => {
    if (!selected) return
    if (!confirm(`确定要删除 "${selected.name}" 吗？`)) return
    api.deleteItem(selected.path).then(() => {
      setSelected(null)
      loadFiles()
    })
  }

  const handleMove = () => {
    if (!selected || !moveTarget) return
    api.moveItem(selected.path, moveTarget).then(() => {
      setShowMoveModal(false)
      setMoveTarget('')
      setSelected(null)
      loadFiles()
    })
  }

  const handleCopy = () => {
    if (!selected) return
    const target = prompt('请输入目标路径（留空为当前目录）：') || currentPath
    api.copyItem(selected.path, target).then(() => {
      setSelected(null)
      loadFiles()
      alert('复制完成')
    })
  }

  const handlePreview = async (item) => {
    if (item.isDir) {
      navigateTo(item.path)
      return
    }
    setSelected(item)
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

  const handleShare = () => {
    if (!selected) return
    setShareResult(null)
    setShareExpire('')
    setSharePassword('')
    setShowShareModal(true)
  }

  const createShare = () => {
    if (!selected) return
    const expireHours = shareExpire ? parseInt(shareExpire) : null
    api.createShare(selected.path, expireHours, sharePassword || null).then(res => {
      setShareResult(res.data.share)
    })
  }

  const copyShareLink = () => {
    if (!shareResult) return
    const url = `${window.location.origin}/share/${shareResult.id}`
    navigator.clipboard.writeText(url)
    alert('链接已复制到剪贴板')
  }

  const handleContextMenu = (e, item) => {
    e.preventDefault()
    setSelected(item)
    setContextMenu({ x: e.clientX, y: e.clientY })
  }

  useEffect(() => {
    const close = () => setContextMenu(null)
    window.addEventListener('click', close)
    return () => window.removeEventListener('click', close)
  }, [])

  const pathParts = currentPath ? currentPath.split('/').filter(Boolean) : []
  const image_exts = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg']

  return (
    <div className="app">
      <header className="header">
        <h1>☁️ 私有云文件管理</h1>
        <div className="actions">
          <button className="btn btn-primary" onClick={() => setShowUploadModal(true)}>📤 上传文件</button>
          <button className="btn btn-primary" onClick={() => setShowNewFolderModal(true)}>📁 新建文件夹</button>
        </div>
      </header>

      <main className="main">
        <div className="breadcrumb">
          <span>位置：</span>
          <a onClick={() => navigateTo('')}>根目录</a>
          {pathParts.map((part, i) => (
            <React.Fragment key={i}>
              <span>/</span>
              <a onClick={() => navigateTo(pathParts.slice(0, i + 1).join('/'))}>{part}</a>
            </React.Fragment>
          ))}
        </div>

        <div className="toolbar">
          {selected && (
            <>
              <button className="btn btn-secondary btn-small" onClick={() => handlePreview(selected)}>👁️ 预览</button>
              <button className="btn btn-secondary btn-small" onClick={() => { setRenameValue(selected.name); setShowRenameModal(true) }}>✏️ 重命名</button>
              <button className="btn btn-secondary btn-small" onClick={() => setShowMoveModal(true)}>📋 移动</button>
              <button className="btn btn-secondary btn-small" onClick={handleCopy}>📄 复制</button>
              <button className="btn btn-secondary btn-small" onClick={handleShare}>🔗 分享</button>
              <button className="btn btn-danger btn-small" onClick={handleDelete}>🗑️ 删除</button>
            </>
          )}
          {!selected && <span style={{ color: '#999', fontSize: '13px' }}>选择文件或文件夹进行操作</span>}
        </div>

        <div className="file-list">
          {loading && <div className="empty-state"><div className="icon">⏳</div>加载中...</div>}
          {!loading && files.length === 0 && (
            <div className="empty-state">
              <div className="icon">📂</div>
              <div>此文件夹为空</div>
            </div>
          )}
          {files.map(item => (
            <div
              key={item.path}
              className={`file-item ${selected?.path === item.path ? 'selected' : ''}`}
              onClick={() => setSelected(item)}
              onDoubleClick={() => handlePreview(item)}
              onContextMenu={(e) => handleContextMenu(e, item)}
            >
              <div className={`icon ${getIconClass(item)}`}>{getIconEmoji(item)}</div>
              <div className="name">{item.name}</div>
              <div className="size">{item.isDir ? '-' : formatSize(item.size)}</div>
              <div className="date">{formatDate(item.modified)}</div>
              <div className="item-actions">
                <button className="btn btn-secondary btn-small" onClick={(e) => { e.stopPropagation(); handlePreview(item) }}>预览</button>
                <button className="btn btn-secondary btn-small" onClick={(e) => { e.stopPropagation(); window.open(api.downloadFile(item.path), '_blank') }}>下载</button>
              </div>
            </div>
          ))}
        </div>
      </main>

      {contextMenu && (
        <div className="context-menu" style={{ left: contextMenu.x, top: contextMenu.y }}>
          <div className="context-menu-item" onClick={() => { handlePreview(selected); setContextMenu(null) }}>👁️ 打开/预览</div>
          <div className="context-menu-item" onClick={() => { setRenameValue(selected?.name || ''); setShowRenameModal(true); setContextMenu(null) }}>✏️ 重命名</div>
          <div className="context-menu-item" onClick={() => { setShowMoveModal(true); setContextMenu(null) }}>📋 移动</div>
          <div className="context-menu-item" onClick={() => { handleCopy(); setContextMenu(null) }}>📄 复制</div>
          <div className="context-menu-item" onClick={() => { window.open(api.downloadFile(selected?.path), '_blank'); setContextMenu(null) }}>⬇️ 下载</div>
          <div className="context-menu-item" onClick={() => { handleShare(); setContextMenu(null) }}>🔗 分享</div>
          <div className="context-menu-divider"></div>
          <div className="context-menu-item" onClick={() => { handleDelete(); setContextMenu(null) }} style={{ color: '#ff5252' }}>🗑️ 删除</div>
        </div>
      )}

      {showUploadModal && (
        <div className="modal-overlay" onClick={() => setShowUploadModal(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <h3>上传文件</h3>
            <input type="file" ref={fileInputRef} onChange={handleUpload} />
            {uploadProgress > 0 && (
              <div className="upload-progress">
                <div className="upload-progress-bar" style={{ width: `${uploadProgress}%` }}></div>
              </div>
            )}
            <div className="modal-actions">
              <button className="btn btn-secondary" onClick={() => setShowUploadModal(false)}>取消</button>
            </div>
          </div>
        </div>
      )}

      {showNewFolderModal && (
        <div className="modal-overlay" onClick={() => setShowNewFolderModal(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <h3>新建文件夹</h3>
            <div className="form-group">
              <label>文件夹名称</label>
              <input value={newFolderName} onChange={e => setNewFolderName(e.target.value)} placeholder="输入文件夹名称" autoFocus />
            </div>
            <div className="modal-actions">
              <button className="btn btn-secondary" onClick={() => setShowNewFolderModal(false)}>取消</button>
              <button className="btn btn-primary" onClick={handleCreateFolder}>创建</button>
            </div>
          </div>
        </div>
      )}

      {showRenameModal && (
        <div className="modal-overlay" onClick={() => setShowRenameModal(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <h3>重命名</h3>
            <div className="form-group">
              <label>新名称</label>
              <input value={renameValue} onChange={e => setRenameValue(e.target.value)} autoFocus />
            </div>
            <div className="modal-actions">
              <button className="btn btn-secondary" onClick={() => setShowRenameModal(false)}>取消</button>
              <button className="btn btn-primary" onClick={handleRename}>确定</button>
            </div>
          </div>
        </div>
      )}

      {showMoveModal && (
        <div className="modal-overlay" onClick={() => setShowMoveModal(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <h3>移动到</h3>
            <div className="form-group">
              <label>目标路径</label>
              <input value={moveTarget} onChange={e => setMoveTarget(e.target.value)} placeholder="例如: folder/subfolder" />
            </div>
            <div className="modal-actions">
              <button className="btn btn-secondary" onClick={() => setShowMoveModal(false)}>取消</button>
              <button className="btn btn-primary" onClick={handleMove}>移动</button>
            </div>
          </div>
        </div>
      )}

      {showShareModal && (
        <div className="modal-overlay" onClick={() => setShowShareModal(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <h3>创建分享链接</h3>
            {!shareResult ? (
              <>
                <div className="form-group">
                  <label>过期时间（小时，留空永不过期）</label>
                  <input type="number" value={shareExpire} onChange={e => setShareExpire(e.target.value)} placeholder="例如: 24" />
                </div>
                <div className="form-group">
                  <label>访问密码（留空无需密码）</label>
                  <input type="text" value={sharePassword} onChange={e => setSharePassword(e.target.value)} placeholder="可选" />
                </div>
                <div className="modal-actions">
                  <button className="btn btn-secondary" onClick={() => setShowShareModal(false)}>取消</button>
                  <button className="btn btn-primary" onClick={createShare}>生成链接</button>
                </div>
              </>
            ) : (
              <>
                <p>分享链接已生成：</p>
                <div className="share-link-box">
                  {window.location.origin}/share/{shareResult.id}
                </div>
                {shareResult.hasPassword && <p style={{ marginTop: '10px', color: '#666', fontSize: '13px' }}>🔒 此链接需要密码访问</p>}
                {shareResult.expireAt && <p style={{ marginTop: '5px', color: '#666', fontSize: '13px' }}>⏰ 过期时间: {formatDate(shareResult.expireAt)}</p>}
                <div className="modal-actions">
                  <button className="btn btn-secondary" onClick={() => setShareResult(null)}>重新生成</button>
                  <button className="btn btn-primary" onClick={copyShareLink}>复制链接</button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

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
              <button className="btn btn-primary" onClick={() => window.open(api.downloadFile(selected?.path), '_blank')}>下载</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default App
