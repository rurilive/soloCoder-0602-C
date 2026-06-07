import axios from 'axios'
import { io } from 'socket.io-client'

const API_BASE = '/api'

const TOKEN_KEY = 'cloud_token'

export const getToken = () => localStorage.getItem(TOKEN_KEY)
export const setToken = (token) => localStorage.setItem(TOKEN_KEY, token)
export const removeToken = () => localStorage.removeItem(TOKEN_KEY)
export const isAuthenticated = () => !!getToken()

export const createSocket = () => {
  const token = getToken()
  if (!token) return null
  return io({
    auth: {
      token: token
    },
    query: {
      token: token
    },
    transports: ['websocket', 'polling'],
    reconnection: true,
    reconnectionAttempts: Infinity,
    reconnectionDelay: 1000,
    reconnectionDelayMax: 5000,
  })
}

const apiClient = axios.create({
  baseURL: API_BASE,
})

apiClient.interceptors.request.use(
  (config) => {
    const token = getToken()
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response && error.response.status === 401) {
      removeToken()
      if (!window.location.pathname.startsWith('/login') && !window.location.pathname.startsWith('/register') && !window.location.pathname.startsWith('/share')) {
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)

export const api = {
  register: (username, password) => apiClient.post('/auth/register', { username, password }),
  login: (username, password) => apiClient.post('/auth/login', { username, password }),
  logout: () => {
    removeToken()
    window.location.href = '/login'
  },

  listFiles: (path = '') => apiClient.get(`/files?path=${encodeURIComponent(path)}`),
  searchFiles: (q, ext = '', path = '') => {
    let url = `/files/search?q=${encodeURIComponent(q)}&path=${encodeURIComponent(path)}`
    if (ext) {
      url += `&ext=${encodeURIComponent(ext)}`
    }
    return apiClient.get(url)
  },
  uploadFile: (path, file, onProgress) => {
    const form = new FormData()
    form.append('path', path)
    form.append('file', file)
    return apiClient.post('/files/upload', form, {
      onUploadProgress: (e) => onProgress?.(Math.round((e.loaded * 100) / e.total))
    })
  },

  uploadInit: (filename, totalSize, totalChunks, fileMD5) =>
    apiClient.post('/files/upload/init', { filename, totalSize, totalChunks, fileMD5 }),

  uploadChunk: (uploadId, chunkIndex, chunk, chunkMD5, onProgress) => {
    const form = new FormData()
    form.append('uploadId', uploadId)
    form.append('chunkIndex', chunkIndex)
    form.append('chunkMD5', chunkMD5)
    form.append('chunk', chunk)
    return apiClient.post('/files/upload/chunk', form, {
      onUploadProgress: (e) => onProgress?.(chunkIndex, Math.round((e.loaded * 100) / e.total))
    })
  },

  uploadComplete: (uploadId, path) =>
    apiClient.post('/files/upload/complete', { uploadId, path }),
  createFolder: (path, name) => apiClient.post('/files/folder', { path, name }),
  deleteItem: (path) => apiClient.post('/files/delete', { path }),
  renameItem: (path, newName) => apiClient.post('/files/rename', { path, newName }),
  moveItem: (src, dst) => apiClient.post('/files/move', { src, dst }),
  copyItem: (src, dst) => apiClient.post('/files/copy', { src, dst }),
  previewFile: (path) => apiClient.get(`/files/preview?path=${encodeURIComponent(path)}`, { responseType: 'blob' }),
  previewText: (path) => apiClient.get(`/files/preview?path=${encodeURIComponent(path)}`).then(res => res.data),
  downloadFile: (path) => {
    const token = getToken()
    return `${API_BASE}/files/download?path=${encodeURIComponent(path)}&token=${token}`
  },
  createShare: (path, expireHours, password) => apiClient.post('/share', { path, expireHours, password }),
  getShare: (shareId, password) => axios.post(`${API_BASE}/share/${shareId}`, { password }),
  shareDownload: (shareId, password, subpath = '') => {
    let url = `${API_BASE}/share/${shareId}/download?password=${encodeURIComponent(password || '')}`
    if (subpath) {
      url += `&subpath=${encodeURIComponent(subpath)}`
    }
    return url
  },

  getStorageUsage: () => apiClient.get('/storage/usage'),

  listTrash: () => apiClient.get('/trash'),
  restoreTrashItem: (path) => apiClient.post('/trash/restore', { path }),
  permanentlyDeleteTrashItem: (path) => apiClient.post('/trash/delete', { path }),
  emptyTrash: () => apiClient.post('/trash/empty'),

  getAuditLogs: (page = 1, perPage = 20, actionType = '') => {
    let url = `/audit?page=${page}&perPage=${perPage}`
    if (actionType) {
      url += `&action=${encodeURIComponent(actionType)}`
    }
    return apiClient.get(url)
  },
}

