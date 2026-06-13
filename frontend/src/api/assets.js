import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 10000,
})

export const getAssets = (params) => api.get('/assets', { params })
export const getAsset = (id) => api.get(`/assets/${id}`)
export const getAssetByTag = (tag) => api.get(`/assets/tag/${tag}`)
export const createAsset = (data) => api.post('/assets', data)
export const updateAsset = (id, data) => api.put(`/assets/${id}`, data)
export const allocateAsset = (id, data) => api.post(`/assets/${id}/allocate`, data)
export const returnAsset = (id, data) => api.post(`/assets/${id}/return`, data)
export const scrapAsset = (id, data) => api.post(`/assets/${id}/scrap`, data)
export const getAssetLogs = (id) => api.get(`/assets/${id}/logs`)
export const getAssetQrCode = (id) => api.get(`/assets/${id}/qrcode`)

export const getApprovals = (params) => api.get('/approvals', { params })
export const getApproval = (id) => api.get(`/approvals/${id}`)
export const approveApproval = (id, data) => api.post(`/approvals/${id}/approve`, data)
export const rejectApproval = (id, data) => api.post(`/approvals/${id}/reject`, data)
export const createApproval = (assetId, data) => api.post(`/approvals/asset/${assetId}`, data)

export const getApprovalChains = (params) => api.get('/approvals/chains/list', { params })
export const getApprovalChain = (id) => api.get(`/approvals/chains/${id}`)
export const createApprovalChain = (data) => api.post('/approvals/chains', data)
export const updateApprovalChain = (id, data) => api.put(`/approvals/chains/${id}`, data)
export const deleteApprovalChain = (id) => api.delete(`/approvals/chains/${id}`)
export const reorderChainNodes = (id, nodeIds) => api.put(`/approvals/chains/${id}/reorder`, { node_ids: nodeIds })

export const importAssets = (file, onUploadProgress) => {
  const formData = new FormData()
  formData.append('file', file)
  return api.post('/assets/import', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000,
    onUploadProgress,
  })
}
