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

function DirectoryTreeSelector({ excludePaths, onSelect, onCancel }) {
  const [treeData, setTreeData] = useState({})
  const [expandedPaths, setExpandedPaths] = useState(new Set(['']))
  const [selectedPath, setSelectedPath] = useState(null)
  const [loadingPaths, setLoadingPaths] = useState(new Set())

  const loadTree = async (path) => {
    if (treeData[path]) return
    setLoadingPaths(prev => new Set(prev).add(path))
    try {
      const res = await api.getFileTree(path)
      setTreeData(prev => ({ ...prev, [path]: res.data.items || [] }))
    } catch (e) {
      setTreeData(prev => ({ ...prev, [path]: [] }))
    }
    setLoadingPaths(prev => { const next = new Set(prev); next.delete(path); return next })
  }

  useEffect(() => {
    loadTree('')
  }, [])

  const toggleExpand = (path) => {
    setExpandedPaths(prev => {
      const next = new Set(prev)
      if (next.has(path)) {
        next.delete(path)
      } else {
        next.add(path)
        loadTree(path)
      }
      return next
    })
  }

  const isExcluded = (path) => {
    if (!excludePaths || excludePaths.length === 0) return false
    return excludePaths.some(src => {
      if (path === src) return true
      if (path.startsWith(src + '/')) return true
      return false
    })
  }

  const handleConfirm = () => {
    if (selectedPath !== null) {
      onSelect(selectedPath)
    }
  }

  const renderTree = (path, depth = 0) => {
    const items = treeData[path] || []
    const isLoading = loadingPaths.has(path)

    return (
      <div key={path || 'root'}>
        {items.map(item => {
          const excluded = isExcluded(item.path)
          const isSelected = selectedPath === item.path
          const hasChildren = item.hasChildren
          const isItemExpanded = expandedPaths.has(item.path)

          return (
            <div key={item.path}>
              <div
                className={`tree-item ${isSelected ? 'tree-item-selected' : ''} ${excluded ? 'tree-item-disabled' : ''}`}
                style={{ paddingLeft: `${depth * 20 + 12}px` }}
                onClick={() => !excluded && setSelectedPath(item.path)}
              >
                <span
                  className="tree-toggle"
                  onClick={(e) => { e.stopPropagation(); hasChildren && toggleExpand(item.path) }}
                >
                  {hasChildren ? (isItemExpanded ? '▼' : '▶') : ''}
                </span>
                <span className="tree-icon">📁</span>
                <span className="tree-name">{item.name}</span>
                {excluded && <span className="tree-excluded-label">（源路径）</span>}
              </div>
              {isItemExpanded && renderTree(item.path, depth + 1)}
            </div>
          )
        })}
        {isLoading && (
          <div style={{ paddingLeft: `${depth * 20 + 32}px`, color: '#999', fontSize: '13px', padding: '4px 0' }}>
            加载中...
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div className="modal tree-selector-modal" onClick={e => e.stopPropagation()}>
        <h3>选择目标文件夹</h3>
        <div className="tree-selector-body">
          <div
            className={`tree-item ${selectedPath === '' ? 'tree-item-selected' : ''}`}
            style={{ paddingLeft: '12px' }}
            onClick={() => setSelectedPath('')}
          >
            <span className="tree-toggle"></span>
            <span className="tree-icon">🏠</span>
            <span className="tree-name">根目录</span>
          </div>
          {renderTree('', 0)}
        </div>
        {selectedPath !== null && (
          <div className="tree-selected-path">
            已选择: /{selectedPath || '（根目录）'}
          </div>
        )}
        <div className="modal-actions">
          <button className="btn btn-secondary" onClick={onCancel}>取消</button>
          <button className="btn btn-primary" onClick={handleConfirm} disabled={selectedPath === null}>确定</button>
        </div>
      </div>
    </div>
  )
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
  const [showShareModal, setShowShareModal] = useState(false)
  const [showPreview, setShowPreview] = useState(false)
  const [previewData, setPreviewData] = useState(null)
  const [newFolderName, setNewFolderName] = useState('')
  const [renameValue, setRenameValue] = useState('')
  const [shareExpire, setShareExpire] = useState('')
  const [sharePassword, setSharePassword] = useState('')
  const [shareResult, setShareResult] = useState(null)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [chunkProgress, setChunkProgress] = useState({})
  const [uploadingFile, setUploadingFile] = useState(null)
  const [contextMenu, setContextMenu] = useState(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchExt, setSearchExt] = useState('')
  const [searchResults, setSearchResults] = useState([])
  const [isSearching, setIsSearching] = useState(false)
  const [storageUsage, setStorageUsage] = useState(null)
  const [notification, setNotification] = useState(null)
  const [favorites, setFavorites] = useState(new Set())
  const [selectedPaths, setSelectedPaths] = useState(new Set())
  const [batchProgress, setBatchProgress] = useState(null)
  const [showTreeSelector, setShowTreeSelector] = useState(false)
  const [treeSelectorMode, setTreeSelectorMode] = useState('move')
  const [treeSelectorSources, setTreeSelectorSources] = useState([])
  const socketRef = useRef(null)
  const currentPathRef = useRef(currentPath)
  const fileInputRef = useRef(null)
  const searchTimeoutRef = useRef(null)
  const notificationTimeoutRef = useRef(null)

  useEffect(() => {
    currentPathRef.current = currentPath
  }, [currentPath])

  const loadStorageUsage = async () => {
    try {
      const res = await api.getStorageUsage()
      setStorageUsage(res.data.usage)
    } catch (e) {
      setStorageUsage(null)
    }
  }

  const loadFavorites = async () => {
    try {
      const res = await api.listFavorites()
      const paths = new Set((res.data.items || []).map(f => f.path))
      setFavorites(paths)
    } catch (e) {
      setFavorites(new Set())
    }
  }

  const toggleFavorite = async (item, e) => {
    if (e) e.stopPropagation()
    const isFav = favorites.has(item.path)
    try {
      if (isFav) {
        await api.removeFavorite(item.path)
        setFavorites(prev => { const next = new Set(prev); next.delete(item.path); return next })
      } else {
        await api.addFavorite(item.path)
        setFavorites(prev => { const next = new Set(prev); next.add(item.path); return next })
      }
    } catch (err) {
      alert('操作失败: ' + (err.response?.data?.error || err.message))
    }
  }

  const loadFiles = async (path = currentPath) => {
    setLoading(true)
    setSelectedPaths(new Set())
    api.listFiles(path).then(res => {
      setFiles(res.data.items || [])
      setCurrentPath(path)
      setLoading(false)
    }).catch(() => setLoading(false))
  }

  const showNotification = (message, type = 'info') => {
    if (notificationTimeoutRef.current) {
      clearTimeout(notificationTimeoutRef.current)
    }
    setNotification({ message, type })
    notificationTimeoutRef.current = setTimeout(() => {
      setNotification(null)
    }, 3000)
  }

  const getActionMessage = (eventType, data) => {
    const actionNames = {
      upload: '上传了文件',
      delete: '删除了文件',
      rename: '重命名了文件',
      move: '移动了文件',
      copy: '复制了文件',
      create_folder: '创建了文件夹',
      restore_trash: '恢复了文件',
      favorite_change: data?.action === 'add' ? '收藏了文件' : '取消了收藏',
    }
    const itemName = data?.item?.name || data?.path || ''
    return `${actionNames[eventType] || '操作了'}: ${itemName}`
  }

  useEffect(() => {
    loadFiles('')
    loadStorageUsage()
    loadFavorites()

    const socket = createSocket()
    if (socket) {
      socketRef.current = socket

      socket.on('connect', () => {
        console.log('Socket connected')
      })

      socket.on('disconnect', () => {
        console.log('Socket disconnected')
      })

      socket.on('file_event', (event) => {
        const { type, data } = event
        console.log('Received file event:', type, data)
        if (type === 'favorite_change') {
          loadFavorites()
        }
        loadFiles(currentPathRef.current)
        loadStorageUsage()
        const message = getActionMessage(type, data)
        if (message) {
          showNotification(message, 'info')
        }
      })

      socket.on('connect_error', (err) => {
        console.error('Socket connection error:', err)
      })
    }

    return () => {
      if (socketRef.current) {
        socketRef.current.disconnect()
        socketRef.current = null
      }
      if (notificationTimeoutRef.current) {
        clearTimeout(notificationTimeoutRef.current)
      }
    }
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

  const CHUNK_SIZE = 5 * 1024 * 1024
  const MAX_RETRY = 3

  const calculateMD5 = async (blob) => {
    const arrayBuffer = await blob.arrayBuffer()
    const hashBuffer = await crypto.subtle.digest('MD5', arrayBuffer)
    const hashArray = Array.from(new Uint8Array(hashBuffer))
    return hashArray.map(b => b.toString(16).padStart(2, '0')).join('')
  }

  const calculateFileMD5 = async (file, onProgress) => {
    const chunks = Math.ceil(file.size / CHUNK_SIZE)
    if (file.size <= CHUNK_SIZE) {
      onProgress?.(100)
      return await calculateMD5(file)
    }
    let md5 = null
    for (let i = 0; i < chunks; i++) {
      const start = i * CHUNK_SIZE
      const end = Math.min(start + CHUNK_SIZE, file.size)
      const chunk = file.slice(start, end)
      const chunkBuffer = await chunk.arrayBuffer()
      if (i === 0) {
        md5 = new Md5()
      }
      md5.append(chunkBuffer)
      onProgress?.(Math.round(((i + 1) / chunks) * 100))
    }
    return md5.end()
  }

  class Md5 {
    constructor() {
      this.buf = new ArrayBuffer(64)
      this.buf8 = new Uint8Array(this.buf)
      this.buf32 = new Uint32Array(this.buf)
      this.bufLen = 0
      this.bytesLen = 0
      this.h0 = 0x67452301
      this.h1 = 0xefcdab89
      this.h2 = 0x98badcfe
      this.h3 = 0x10325476
    }
    append(data) {
      const view = new Uint8Array(data)
      let pos = 0
      while (pos < view.length) {
        const len = Math.min(64 - this.bufLen, view.length - pos)
        this.buf8.set(view.subarray(pos, pos + len), this.bufLen)
        this.bufLen += len
        pos += len
        this.bytesLen += len
        if (this.bufLen === 64) {
          this._process()
          this.bufLen = 0
        }
      }
      return this
    }
    end() {
      const bitLen = this.bytesLen * 8
      this.buf8[this.bufLen++] = 0x80
      if (this.bufLen > 56) {
        while (this.bufLen < 64) this.buf8[this.bufLen++] = 0
        this._process()
        this.bufLen = 0
      }
      while (this.bufLen < 56) this.buf8[this.bufLen++] = 0
      this.buf32[14] = bitLen & 0xffffffff
      this.buf32[15] = Math.floor(bitLen / 0x100000000)
      this._process()
      const toHex = (n) => {
        let hex = ''
        for (let i = 0; i < 4; i++) {
          hex += ((n >> (i * 8)) & 0xff).toString(16).padStart(2, '0')
        }
        return hex
      }
      return toHex(this.h0) + toHex(this.h1) + toHex(this.h2) + toHex(this.h3)
    }
    _process() {
      const K = [
        0xd76aa478, 0xe8c7b756, 0x242070db, 0xc1bdceee,
        0xf57c0faf, 0x4787c62a, 0xa8304613, 0xfd469501,
        0x698098d8, 0x8b44f7af, 0xffff5bb1, 0x895cd7be,
        0x6b901122, 0xfd987193, 0xa679438e, 0x49b40821,
        0xf61e2562, 0xc040b340, 0x265e5a51, 0xe9b6c7aa,
        0xd62f105d, 0x02441453, 0xd8a1e681, 0xe7d3fbc8,
        0x21e1cde6, 0xc33707d6, 0xf4d50d87, 0x455a14ed,
        0xa9e3e905, 0xfcefa3f8, 0x676f02d9, 0x8d2a4c8a,
        0xfffa3942, 0x8771f681, 0x6d9d6122, 0xfde5380c,
        0xa4beea44, 0x4bdecfa9, 0xf6bb4b60, 0xbebfbc70,
        0x289b7ec6, 0xeaa127fa, 0xd4ef3085, 0x04881d05,
        0xd9d4d039, 0xe6db99e5, 0x1fa27cf8, 0xc4ac5665,
        0xf4292244, 0x432aff97, 0xab9423a7, 0xfc93a039,
        0x655b59c3, 0x8f0ccc92, 0xffeff47d, 0x85845dd1,
        0x6fa87e4f, 0xfe2ce6e0, 0xa3014314, 0x4e0811a1,
        0xf7537e82, 0xbd3af235, 0x2ad7d2bb, 0xeb86d391,
      ]
      const S = [
        7, 12, 17, 22, 7, 12, 17, 22, 7, 12, 17, 22, 7, 12, 17, 22,
        5, 9, 14, 20, 5, 9, 14, 20, 5, 9, 14, 20, 5, 9, 14, 20,
        4, 11, 16, 23, 4, 11, 16, 23, 4, 11, 16, 23, 4, 11, 16, 23,
        6, 10, 15, 21, 6, 10, 15, 21, 6, 10, 15, 21, 6, 10, 15, 21,
      ]
      const M = new Uint32Array(16)
      for (let i = 0; i < 16; i++) {
        M[i] = this.buf32[i]
      }
      let a = this.h0, b = this.h1, c = this.h2, d = this.h3
      const rotl = (x, n) => (x << n) | (x >>> (32 - n))
      for (let i = 0; i < 64; i++) {
        let f, g
        if (i < 16) {
          f = (b & c) | ((~b) & d)
          g = i
        } else if (i < 32) {
          f = (d & b) | ((~d) & c)
          g = (5 * i + 1) % 16
        } else if (i < 48) {
          f = b ^ c ^ d
          g = (3 * i + 5) % 16
        } else {
          f = c ^ (b | (~d))
          g = (7 * i) % 16
        }
        f = (f + a + K[i] + M[g]) & 0xffffffff
        a = d
        d = c
        c = b
        b = (b + rotl(f, S[i])) & 0xffffffff
      }
      this.h0 = (this.h0 + a) & 0xffffffff
      this.h1 = (this.h1 + b) & 0xffffffff
      this.h2 = (this.h2 + c) & 0xffffffff
      this.h3 = (this.h3 + d) & 0xffffffff
    }
  }

  const uploadChunkWithRetry = async (uploadId, chunkIndex, chunk, chunkMD5) => {
    let lastError = null
    for (let attempt = 0; attempt < MAX_RETRY; attempt++) {
      try {
        const res = await api.uploadChunk(uploadId, chunkIndex, chunk, chunkMD5, (idx, p) => {
          setChunkProgress(prev => ({ ...prev, [idx]: p }))
        })
        return res.data
      } catch (e) {
        lastError = e
        if (attempt < MAX_RETRY - 1) {
          await new Promise(r => setTimeout(r, 1000 * (attempt + 1)))
        }
      }
    }
    throw lastError
  }

  const handleChunkedUpload = async (file) => {
    try {
      setUploadingFile(file.name)
      setUploadProgress(0)
      setChunkProgress({})

      const totalChunks = Math.ceil(file.size / CHUNK_SIZE)
      const fileMD5 = await calculateFileMD5(file, (p) => setUploadProgress(Math.round(p * 0.2)))

      const initRes = await api.uploadInit(file.name, file.size, totalChunks, fileMD5)
      const uploadId = initRes.data.uploadId

      const chunkMD5s = []
      for (let i = 0; i < totalChunks; i++) {
        const start = i * CHUNK_SIZE
        const end = Math.min(start + CHUNK_SIZE, file.size)
        const chunk = file.slice(start, end)
        const md5 = await calculateMD5(chunk)
        chunkMD5s.push(md5)
      }

      let uploadedChunks = 0
      const concurrency = 3
      let index = 0
      const workers = []
      for (let w = 0; w < concurrency && index < totalChunks; w++) {
        const worker = (async () => {
          while (index < totalChunks) {
            const currentIndex = index++
            const start = currentIndex * CHUNK_SIZE
            const end = Math.min(start + CHUNK_SIZE, file.size)
            const chunk = file.slice(start, end)
            await uploadChunkWithRetry(uploadId, currentIndex, chunk, chunkMD5s[currentIndex])
            uploadedChunks++
            setUploadProgress(20 + Math.round((uploadedChunks / totalChunks) * 75))
          }
        })()
        workers.push(worker)
      }
      await Promise.all(workers)

      setUploadProgress(95)
      const completeRes = await api.uploadComplete(uploadId, currentPath)
      setUploadProgress(100)

      return completeRes.data
    } catch (e) {
      throw e
    }
  }

  const navigateTo = (path) => {
    loadFiles(path)
    setSelected(null)
    setSelectedPaths(new Set())
  }

  const handleUpload = (e) => {
    const file = e.target.files[0]
    if (!file) return
    setUploadProgress(0)
    setChunkProgress({})
    setUploadingFile(file.name)

    const useChunked = file.size > CHUNK_SIZE

    const uploadPromise = useChunked
      ? handleChunkedUpload(file)
      : api.uploadFile(currentPath, file, (p) => setUploadProgress(p))

    uploadPromise.then(() => {
      setShowUploadModal(false)
      loadFiles()
      loadStorageUsage()
      setUploadProgress(0)
      setChunkProgress({})
      setUploadingFile(null)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }).catch((e) => {
        if (e.response?.status === 403) {
          alert('存储空间不足，请删除一些文件或清理回收站后再试')
          loadStorageUsage()
        } else {
          alert('上传失败: ' + (e.response?.data?.error || e.message))
        }
        setUploadProgress(0)
        setChunkProgress({})
        setUploadingFile(null)
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
      setSelectedPaths(new Set())
      loadFiles()
      loadStorageUsage()
    })
  }

  const handleBatchDelete = async () => {
    const paths = Array.from(selectedPaths)
    if (paths.length === 0) return
    if (!confirm(`确定要删除选中的 ${paths.length} 个项目吗？文件将移到回收站，30天后自动清理。`)) return
    setBatchProgress({ current: 0, total: paths.length, action: '删除' })
    let successCount = 0
    let failCount = 0
    for (let i = 0; i < paths.length; i++) {
      try {
        await api.deleteItem(paths[i])
        successCount++
      } catch (e) {
        failCount++
      }
      setBatchProgress({ current: i + 1, total: paths.length, action: '删除' })
    }
    setBatchProgress(null)
    setSelectedPaths(new Set())
    setSelected(null)
    loadFiles()
    loadStorageUsage()
    showNotification(`批量删除完成: 成功 ${successCount} 个${failCount > 0 ? `，失败 ${failCount} 个` : ''}`, failCount > 0 ? 'error' : 'success')
  }

  const handleMove = () => {
    if (!selected) return
    setTreeSelectorSources([selected.path])
    setTreeSelectorMode('move')
    setShowTreeSelector(true)
  }

  const handleBatchMove = () => {
    const paths = Array.from(selectedPaths)
    if (paths.length === 0) return
    setTreeSelectorSources(paths)
    setTreeSelectorMode('move')
    setShowTreeSelector(true)
  }

  const handleTreeSelect = async (targetPath) => {
    setShowTreeSelector(false)

    if (treeSelectorMode === 'move') {
      if (treeSelectorSources.length === 1) {
        api.moveItem(treeSelectorSources[0], targetPath).then(() => {
          setSelected(null)
          setSelectedPaths(new Set())
          loadFiles()
        }).catch(e => {
          alert('移动失败: ' + (e.response?.data?.error || e.message))
        })
      } else {
        const paths = treeSelectorSources
        setBatchProgress({ current: 0, total: paths.length, action: '移动' })
        let successCount = 0
        let failCount = 0
        for (let i = 0; i < paths.length; i++) {
          try {
            await api.moveItem(paths[i], targetPath)
            successCount++
          } catch (e) {
            failCount++
          }
          setBatchProgress({ current: i + 1, total: paths.length, action: '移动' })
        }
        setBatchProgress(null)
        setSelectedPaths(new Set())
        setSelected(null)
        loadFiles()
        showNotification(`批量移动完成: 成功 ${successCount} 个${failCount > 0 ? `，失败 ${failCount} 个` : ''}`, failCount > 0 ? 'error' : 'success')
      }
    } else {
      if (treeSelectorSources.length === 1) {
        api.copyItem(treeSelectorSources[0], targetPath).then(() => {
          setSelected(null)
          loadFiles()
          loadStorageUsage()
          showNotification('复制完成', 'success')
        }).catch(e => {
          if (e.response?.status === 403) {
            alert('存储空间不足，无法复制文件')
            loadStorageUsage()
          } else {
            alert('复制失败: ' + (e.response?.data?.error || e.message))
          }
        })
      }
    }
  }

  const handleCopy = () => {
    if (!selected) return
    setTreeSelectorSources([selected.path])
    setTreeSelectorMode('copy')
    setShowTreeSelector(true)
  }

  const toggleSelectPath = (path, e) => {
    if (e) e.stopPropagation()
    setSelectedPaths(prev => {
      const next = new Set(prev)
      if (next.has(path)) {
        next.delete(path)
      } else {
        next.add(path)
      }
      return next
    })
  }

  const toggleSelectAll = () => {
    if (selectedPaths.size === displayFiles.length && displayFiles.length > 0) {
      setSelectedPaths(new Set())
    } else {
      setSelectedPaths(new Set(displayFiles.map(f => f.path)))
    }
  }

  const exitBatchMode = () => {
    setSelectedPaths(new Set())
    setSelected(null)
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
            <button className="btn btn-secondary" onClick={() => navigate('/favorites')}>⭐ 收藏夹</button>
            <button className="btn btn-secondary" onClick={() => navigate('/trash')}>🗑️ 回收站</button>
            <button className="btn btn-secondary" onClick={() => navigate('/audit')}>📋 审计日志</button>
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
          {selectedPaths.size > 0 && !isSearching && (
            <>
              <span className="batch-count">已选 {selectedPaths.size} 项</span>
              <button className="btn btn-danger btn-small" onClick={handleBatchDelete}>🗑️ 批量删除</button>
              <button className="btn btn-secondary btn-small" onClick={handleBatchMove}>📋 批量移动</button>
              <button className="btn btn-secondary btn-small" onClick={exitBatchMode}>✕ 取消选择</button>
            </>
          )}
          {selectedPaths.size === 0 && selected && !isSearching && (
            <>
              <button className="btn btn-secondary btn-small" onClick={() => handlePreview(selected)}>👁️ 预览</button>
              <button className="btn btn-secondary btn-small" onClick={() => { setRenameValue(selected.name); setShowRenameModal(true) }}>✏️ 重命名</button>
              <button className="btn btn-secondary btn-small" onClick={handleMove}>📋 移动</button>
              <button className="btn btn-secondary btn-small" onClick={handleCopy}>📄 复制</button>
              <button className="btn btn-secondary btn-small" onClick={handleShare}>🔗 分享</button>
              <button className="btn btn-danger btn-small" onClick={handleDelete}>🗑️ 删除</button>
            </>
          )}
          {isSearching && <span style={{ color: '#999', fontSize: '13px' }}>找到 {searchResults.length} 个结果</span>}
          {!selected && selectedPaths.size === 0 && !isSearching && <span style={{ color: '#999', fontSize: '13px' }}>选择文件或文件夹进行操作</span>}
        </div>

        <div className="file-list">
          {!isSearching && displayFiles.length > 0 && (
            <div className="file-list-header">
              <input
                type="checkbox"
                className="file-checkbox"
                checked={selectedPaths.size === displayFiles.length && displayFiles.length > 0}
                onChange={toggleSelectAll}
              />
              <span className="header-name">名称</span>
              <span className="header-size">大小</span>
              <span className="header-date">修改时间</span>
              <span className="header-actions">操作</span>
            </div>
          )}
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
              className={`file-item ${selected?.path === item.path ? 'selected' : ''} ${selectedPaths.has(item.path) ? 'batch-selected' : ''}`}
              onClick={() => { setSelected(item); setSelectedPaths(new Set()) }}
              onDoubleClick={() => handlePreview(item)}
              onContextMenu={(e) => handleContextMenu(e, item)}
            >
              <input
                type="checkbox"
                className="file-checkbox"
                checked={selectedPaths.has(item.path)}
                onChange={(e) => toggleSelectPath(item.path, e)}
                onClick={(e) => e.stopPropagation()}
              />
              <div className={`icon ${getIconClass(item)}`}>{getIconEmoji(item)}</div>
              <div className="name">{item.name}</div>
              <div className="size">{item.isDir ? '-' : formatSize(item.size)}</div>
              <div className="date">{formatDate(item.modified)}</div>
              <div className="item-actions">
                <button
                  className={`btn btn-small fav-btn ${favorites.has(item.path) ? 'fav-active' : ''}`}
                  onClick={(e) => toggleFavorite(item, e)}
                  title={favorites.has(item.path) ? '取消收藏' : '添加收藏'}
                >{favorites.has(item.path) ? '★' : '☆'}</button>
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
          <div className="context-menu-item" onClick={() => { handleMove(); setContextMenu(null) }}>📋 移动</div>
          <div className="context-menu-item" onClick={() => { handleCopy(); setContextMenu(null) }}>📄 复制</div>
          <div className="context-menu-item" onClick={() => { window.open(api.downloadFile(selected?.path), '_blank'); setContextMenu(null) }}>⬇️ 下载</div>
          <div className="context-menu-item" onClick={() => { handleShare(); setContextMenu(null) }}>🔗 分享</div>
          <div className="context-menu-item" onClick={() => { toggleFavorite(selected); setContextMenu(null) }}>{favorites.has(selected?.path) ? '☆ 取消收藏' : '★ 添加收藏'}</div>
          <div className="context-menu-divider"></div>
          <div className="context-menu-item" onClick={() => { handleDelete(); setContextMenu(null) }} style={{ color: '#ff5252' }}>🗑️ 删除</div>
        </div>
      )}

      {showUploadModal && (
        <div className="modal-overlay" onClick={() => setShowUploadModal(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <h3>上传文件</h3>
            <input type="file" ref={fileInputRef} onChange={handleUpload} />
            {uploadingFile && (
              <div style={{ marginTop: '10px', fontSize: '13px', color: '#666' }}>
                正在上传: {uploadingFile}
              </div>
            )}
            {uploadProgress > 0 && (
              <>
                <div className="upload-progress">
                  <div className="upload-progress-bar" style={{ width: `${uploadProgress}%` }}></div>
                </div>
                <div style={{ textAlign: 'center', fontSize: '12px', color: '#666', marginTop: '5px' }}>
                  {uploadProgress}%
                </div>
              </>
            )}
            {Object.keys(chunkProgress).length > 0 && (
              <div style={{ marginTop: '10px', maxHeight: '150px', overflowY: 'auto' }}>
                <div style={{ fontSize: '12px', color: '#666', marginBottom: '5px' }}>分片进度:</div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                  {Object.entries(chunkProgress).sort((a, b) => parseInt(a[0]) - parseInt(b[0])).map(([idx, p]) => (
                    <div
                      key={idx}
                      style={{
                        width: '20px',
                        height: '20px',
                        borderRadius: '3px',
                        backgroundColor: p === 100 ? '#4caf50' : p > 0 ? '#2196f3' : '#e0e0e0',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontSize: '10px',
                        color: '#fff',
                      }}
                      title={`分片 ${parseInt(idx) + 1}: ${p}%`}
                    >
                      {p === 100 ? '✓' : parseInt(idx) + 1}
                    </div>
                  ))}
                </div>
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

      {showTreeSelector && (
        <DirectoryTreeSelector
          excludePaths={treeSelectorSources}
          onSelect={handleTreeSelect}
          onCancel={() => setShowTreeSelector(false)}
        />
      )}

      {batchProgress && (
        <div className="modal-overlay">
          <div className="modal">
            <h3>批量{batchProgress.action}中</h3>
            <div className="upload-progress">
              <div className="upload-progress-bar" style={{ width: `${(batchProgress.current / batchProgress.total) * 100}%` }}></div>
            </div>
            <div style={{ textAlign: 'center', fontSize: '13px', color: '#666', marginTop: '8px' }}>
              {batchProgress.current} / {batchProgress.total}
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

      {notification && (
        <div className={`notification notification-${notification.type}`}>
          {notification.message}
        </div>
      )}
    </div>
  )
}

export default App
