import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getAssetByTag } from '../api/assets'

export default function AssetScan() {
  const navigate = useNavigate()
  const [tag, setTag] = useState('')
  const [error, setError] = useState('')

  const handleSearch = async (e) => {
    e.preventDefault()
    if (!tag.trim()) return
    setError('')
    try {
      const res = await getAssetByTag(tag.trim())
      navigate(`/assets/${res.data.id}`)
    } catch (err) {
      setError(err.response?.data?.detail || '未找到该资产')
    }
  }

  return (
    <div className="scan-page">
      <div className="card" style={{ width: 480, maxWidth: '100%' }}>
        <h2 style={{ marginBottom: 20, textAlign: 'center' }}>扫码查询资产</h2>
        <p style={{ color: 'var(--text-secondary)', fontSize: 14, marginBottom: 20, textAlign: 'center' }}>
          扫描资产二维码后，将自动跳转至资产详情页面。也可以手动输入资产编号查询。
        </p>
        <form onSubmit={handleSearch}>
          <div className="form-group" style={{ marginBottom: 16 }}>
            <label>资产编号</label>
            <input
              className="scan-input"
              value={tag}
              onChange={(e) => setTag(e.target.value)}
              placeholder="请输入或扫描资产编号（如 AST20260611001）"
              autoFocus
            />
          </div>
          {error && (
            <p style={{ color: 'var(--danger)', fontSize: 14, marginBottom: 12 }}>{error}</p>
          )}
          <button type="submit" className="btn btn-primary" style={{ width: '100%' }}>
            查询
          </button>
        </form>
      </div>
    </div>
  )
}
