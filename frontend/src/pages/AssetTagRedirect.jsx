import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getAssetByTag } from '../api/assets'

export default function AssetTagRedirect() {
  const { tag } = useParams()
  const navigate = useNavigate()
  const [error, setError] = useState('')

  useEffect(() => {
    const fetchAsset = async () => {
      try {
        const res = await getAssetByTag(tag)
        navigate(`/assets/${res.data.id}`, { replace: true })
      } catch (err) {
        const msg = err.response?.data?.detail || '未找到该资产'
        setError(msg)
      }
    }
    fetchAsset()
  }, [tag, navigate])

  if (error) {
    return (
      <div className="empty-state">
        <p style={{ color: 'var(--danger)' }}>{error}</p>
        <button className="btn btn-primary" onClick={() => navigate('/')}>返回列表</button>
      </div>
    )
  }

  return (
    <div className="empty-state">
      <p>正在加载资产信息...</p>
    </div>
  )
}
