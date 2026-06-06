import axios from 'axios'

const API_BASE = '/api'

export const api = {
  listFiles: (path = '') => axios.get(`${API_BASE}/files?path=${encodeURIComponent(path)}`),
  uploadFile: (path, file, onProgress) => {
    const form = new FormData()
    form.append('path', path)
    form.append('file', file)
    return axios.post(`${API_BASE}/files/upload`, form, {
      onUploadProgress: (e) => onProgress?.(Math.round((e.loaded * 100) / e.total))
    })
  },
  createFolder: (path, name) => axios.post(`${API_BASE}/files/folder`, { path, name }),
  deleteItem: (path) => axios.post(`${API_BASE}/files/delete`, { path }),
  renameItem: (path, newName) => axios.post(`${API_BASE}/files/rename`, { path, newName }),
  moveItem: (src, dst) => axios.post(`${API_BASE}/files/move`, { src, dst }),
  copyItem: (src, dst) => axios.post(`${API_BASE}/files/copy`, { src, dst }),
  previewFile: (path) => axios.get(`${API_BASE}/files/preview?path=${encodeURIComponent(path)}`, { responseType: 'blob' }),
  previewText: (path) => axios.get(`${API_BASE}/files/preview?path=${encodeURIComponent(path)}`).then(res => res.data),
  downloadFile: (path) => `${API_BASE}/files/download?path=${encodeURIComponent(path)}`,
  createShare: (path, expireHours, password) => axios.post(`${API_BASE}/share`, { path, expireHours, password }),
  getShare: (shareId, password) => axios.post(`${API_BASE}/share/${shareId}`, { password }),
  shareDownload: (shareId, password, subpath = '') => {
    let url = `${API_BASE}/share/${shareId}/download?password=${encodeURIComponent(password || '')}`
    if (subpath) {
      url += `&subpath=${encodeURIComponent(subpath)}`
    }
    return url
  },
}
