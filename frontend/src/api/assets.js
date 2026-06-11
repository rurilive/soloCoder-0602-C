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
