import React, { useState, useEffect, useRef } from 'react'
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
  const navigate = useNavigate()
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
  const [searchQuery, setSearchQuery] = useState('')
  const [searchExt, setSearchExt] = useState('')
  const [searchResults, setSearchResults] = useState([])
  const [isSearching, setIsSearching] = useState(false)
  const [storageUsage, setStorageUsage] = useState(null)
  const fileInputRef = useRef(null)
  const searchTimeoutRef = useRef(null)

  const loadStorageUsage = async () => {
    try {
      const res = await api.getStorageUsage()
      setStorageUsage(res.data.usage)
    } catch (e) {
      setStorageUsage(null)
    }
  }

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
    loadStorageUsage()
  }, [])

  const handleSearch = (query, ext) => {
    if (searchTimeoutRef.current) {
      clearTimeout(searchTimeoutRef.current)
    }
    if (!query.trim()) {
      setIsSearching(false)
      setSearchResults([])
      return
    }
    setIsSearching(true)
    searchTimeoutRef.current = setTimeout(() => {
      api.searchFiles(query.trim(), ext, currentPath).then(res => {
        setSearchResults(res.data.items || [])
      }).catch(() => {
        setSearchResults([])
      })
    }, 300)
  }

  useEffect(() => {
    handleSearch(searchQuery, searchExt)
  }, [searchQuery, searchExt])

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
      loadStorageUsage()
      setUploadProgress(0)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }).catch((e) => {
        if (e.response?.status === 403) {
          alert('存储空间不足，请删除一些文件或清理回收站后再试')
          loadStorageUsage()
        }
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
    if (!confirm(`确定要删除 "${selected.name}" 吗？文件将移到回收站，30天后自动清理。`)) return
    api.deleteItem(selected.path).then(() => {
      setSelected(null)
      loadFiles()
      loadStorageUsage()
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
      loadStorageUsage()
      alert('复制完成')
    }).catch((e) => {
        if (e.response?.status === 403) {
          alert('存储空间不足，无法复制文件')
          loadStorageUsage()
        } else {
          alert('复制失败: ' + (e.response?.data?.error || e.message))
        }
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

  const displayFiles = isSearching ? searchResults : files

  const clearSearch = () => {
    setSearchQuery('')
    setSearchExt('')
  }

  const isQuotaFull = storageUsage && storageUsage.remaining <= 0
  const usagePercent = storageUsage ? Math.min(100, (storageUsage.used / storageUsage.quota) * 100) : 0

  return (
    <div className="app">
      <header className="header">
        <h1>☁️ 私有云文件管理</h1>
        <div className="header-right">
          {storageUsage && (
            <div className="storage-quota">
              <div className="storage-info">
                <span>已用: {formatSize(storageUsage.used)} / {formatSize(storageUsage.quota)}</span>
                {isQuotaFull && <span className="quota-warning"> (空间不足)</span>}
              </div>
              <div className="storage-progress-bar">
                <div
                  className={`storage-progress-fill ${isQuotaFull ? 'full' : ''}`}
                  style={{ width: `${usagePercent}%` }}
                ></div>
              </div>
            </div>
          )}
          <div className="actions">
            <button
              className={`btn btn-primary ${isQuotaFull ? 'btn-disabled' : ''}`}
              onClick={() => !isQuotaFull && setShowUploadModal(true)}
              disabled={isQuotaFull}
              title={isQuotaFull ? '存储空间不足，请先清理文件' : ''}
            >📤 上传文件</button>
            <button className="btn btn-primary" onClick={() => setShowNewFolderModal(true)}>📁 新建文件夹</button>
            <button className="btn btn-secondary" onClick={() => navigate('/trash')}>🗑️ 回收站</button>
            <button className="btn btn-secondary" onClick={() => api.logout()}>🚪 退出</button>
          </div>
        </div>
      </header>

      <main className="main">
        <div className="breadcrumb">
          <span>位置：</span>
          <a onClick={() => { clearSearch(); navigateTo('') }}>根目录</a>
          {!isSearching && pathParts.map((part, i) => (
            <React.Fragment key={i}>
              <span>/</span>
              <a onClick={() => { clearSearch(); navigateTo(pathParts.slice(0, i + 1).join('/')) }}>{part}</a>
            </React.Fragment>
          ))}
          {isSearching && (
            <>
              <span>/</span>
              <span style={{ color: '#666' }}>搜索: "{searchQuery}"</span>
              {searchExt && <span style={{ color: '#666', marginLeft: '8px' }}>(.{searchExt})</span>}
            </>
          )}
        </div>

        <div className="search-bar">
          <div className="search-input-wrapper">
            <input
              type="text"
              className="search-input"
              placeholder="🔍 搜索文件名..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
            {searchQuery && (
              <button className="search-clear" onClick={clearSearch}>✕</button>
            )}
          </div>
          <select
            className="search-ext-select"
            value={searchExt}
            onChange={(e) => setSearchExt(e.target.value)}
          >
            <option value="">所有类型</option>
            <option value="jpg">图片 (jpg)</option>
            <option value="png">图片 (png)</option>
            <option value="pdf">PDF</option>
            <option value="txt">文本</option>
            <option value="md">Markdown</option>
            <option value="doc">文档</option>
            <option value="zip">压缩包</option>
          </select>
        </div>

        <div className="toolbar">
          {selected && !isSearching && (
            <>
              <button className="btn btn-secondary btn-small" onClick={() => handlePreview(selected)}>👁️ 预览</button>
              <button className="btn btn-secondary btn-small" onClick={() => { setRenameValue(selected.name); setShowRenameModal(true) }}>✏️ 重命名</button>
              <button className="btn btn-secondary btn-small" onClick={() => setShowMoveModal(true)}>📋 移动</button>
              <button className="btn btn-secondary btn-small" onClick={handleCopy}>📄 复制</button>
              <button className="btn btn-secondary btn-small" onClick={handleShare}>🔗 分享</button>
              <button className="btn btn-danger btn-small" onClick={handleDelete}>🗑️ 删除</button>
            </>
          )}
          {isSearching && <span style={{ color: '#999', fontSize: '13px' }}>找到 {searchResults.length} 个结果</span>}
          {!selected && !isSearching && <span style={{ color: '#999', fontSize: '13px' }}>选择文件或文件夹进行操作</span>}
        </div>

        <div className="file-list">
          {loading && <div className="empty-state"><div className="icon">⏳</div>加载中...</div>}
          {!loading && isSearching && searchResults.length === 0 && (
            <div className="empty-state">
              <div className="icon">🔍</div>
              <div>未找到匹配的文件</div>
            </div>
          )}
          {!loading && !isSearching && files.length === 0 && (
            <div className="empty-state">
              <div className="icon">📂</div>
              <div>此文件夹为空</div>
            </div>
          )}
          {displayFiles.map(item => (
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
